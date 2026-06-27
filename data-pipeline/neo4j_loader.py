"""Milestone 1 — Neo4j Batch Ingestion.

Loads the synthetic farmer registry graph into Neo4j using clean Cypher
transaction functions (no ORM/wrapper frameworks).

Key properties of this loader:
  * Reads credentials from environment variables (NEO4J_URI, NEO4J_USERNAME,
    NEO4J_PASSWORD); supports a local ``.env`` file via python-dotenv.
  * Establishes the driver with an explicit connection health check and
    bounded retry/back-off (transient failures only; auth failures fail fast).
  * Applies uniqueness constraints on every node id *before* ingestion so the
    MERGE-based loads are fully idempotent across repeated demo runs.
  * Ingests nodes and relationships in batched ``UNWIND $rows`` transactions.

Run directly to generate fresh synthetic data and ingest it:

    python data-pipeline/neo4j_loader.py --farmers 1000 --reset
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from neo4j import Driver, GraphDatabase, ManagedTransaction
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

# Ensure sibling-module imports work regardless of the current working dir.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_synthetic import SyntheticDataset, generate_dataset  # noqa: E402

try:  # Optional: load NEO4J_* from a local .env file if present.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a convenience, not required.
    pass

logger = logging.getLogger(__name__)

DEFAULT_DATABASE = "neo4j"
DEFAULT_BATCH_SIZE = 500

# ---------------------------------------------------------------------------
# Schema: uniqueness constraints (also create the backing index for MATCH/MERGE).
# ---------------------------------------------------------------------------

CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT farmer_id IF NOT EXISTS "
    "FOR (f:Farmer) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT farmholding_id IF NOT EXISTS "
    "FOR (h:FarmHolding) REQUIRE h.id IS UNIQUE",
    "CREATE CONSTRAINT cropcycle_id IF NOT EXISTS "
    "FOR (c:CropCycle) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT transaction_id IF NOT EXISTS "
    "FOR (t:Transaction) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT organization_id IF NOT EXISTS "
    "FOR (o:Organization) REQUIRE o.id IS UNIQUE",
]

# ---------------------------------------------------------------------------
# Cypher: idempotent node upserts (MERGE on id, SET remaining properties).
# ---------------------------------------------------------------------------

UPSERT_ORGANIZATIONS = """
UNWIND $rows AS row
MERGE (o:Organization {id: row.id})
SET o.name = row.name,
    o.type = row.type
"""

UPSERT_FARMERS = """
UNWIND $rows AS row
MERGE (f:Farmer {id: row.id})
SET f.name = row.name,
    f.phone = row.phone,
    f.location = row.location,
    f.country = row.country,
    f.verified = row.verified,
    f.consent_signed = row.consent_signed
"""

UPSERT_HOLDINGS = """
UNWIND $rows AS row
MERGE (h:FarmHolding {id: row.id})
SET h.size_hectares = row.size_hectares,
    h.latitude = row.latitude,
    h.longitude = row.longitude,
    h.soil_type = row.soil_type
"""

UPSERT_CROP_CYCLES = """
UNWIND $rows AS row
MERGE (c:CropCycle {id: row.id})
SET c.crop_type = row.crop_type,
    c.season = row.season,
    c.planted_at = date(row.planted_at),
    c.harvest_estimate_tons = row.harvest_estimate_tons,
    c.status = row.status
"""

UPSERT_TRANSACTIONS = """
UNWIND $rows AS row
MERGE (t:Transaction {id: row.id})
SET t.type = row.type,
    t.amount = row.amount,
    t.date = date(row.date),
    t.status = row.status
"""

# ---------------------------------------------------------------------------
# Cypher: idempotent relationship upserts.
# ---------------------------------------------------------------------------

UPSERT_OWNS = """
UNWIND $rows AS row
MATCH (f:Farmer {id: row.farmer_id})
MATCH (h:FarmHolding {id: row.holding_id})
MERGE (f)-[:OWNS]->(h)
"""

UPSERT_HAS_CYCLE = """
UNWIND $rows AS row
MATCH (h:FarmHolding {id: row.holding_id})
MATCH (c:CropCycle {id: row.cycle_id})
MERGE (h)-[:HAS_CYCLE]->(c)
"""

UPSERT_EXECUTED = """
UNWIND $rows AS row
MATCH (f:Farmer {id: row.farmer_id})
MATCH (t:Transaction {id: row.txn_id})
MERGE (f)-[:EXECUTED]->(t)
"""

UPSERT_BELONGS_TO = """
UNWIND $rows AS row
MATCH (t:Transaction {id: row.txn_id})
MATCH (o:Organization {id: row.org_id})
MERGE (t)-[:BELONGS_TO]->(o)
"""

UPSERT_MEMBER_OF = """
UNWIND $rows AS row
MATCH (f:Farmer {id: row.farmer_id})
MATCH (o:Organization {id: row.org_id})
MERGE (f)-[:MEMBER_OF]->(o)
"""


# ---------------------------------------------------------------------------
# Driver lifecycle.
# ---------------------------------------------------------------------------


def create_driver(
    uri: str,
    username: str,
    password: str,
    max_retries: int = 5,
    backoff_seconds: float = 2.0,
) -> Driver:
    """Create a Neo4j driver, verifying connectivity with bounded retries.

    Transient connection failures (server still starting, network hiccup) are
    retried with linear back-off. Authentication failures are not retried.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        driver = GraphDatabase.driver(uri, auth=(username, password))
        try:
            driver.verify_connectivity()
            logger.info("Connected to Neo4j at %s (attempt %d).", uri, attempt)
            return driver
        except AuthError:
            driver.close()
            logger.error("Authentication failed for user '%s'.", username)
            raise
        except (ServiceUnavailable, OSError) as exc:
            last_error = exc
            driver.close()
            wait = backoff_seconds * attempt
            logger.warning(
                "Connection attempt %d/%d failed (%s). Retrying in %.1fs.",
                attempt,
                max_retries,
                exc.__class__.__name__,
                wait,
            )
            time.sleep(wait)

    raise ConnectionError(
        f"Could not connect to Neo4j at {uri} after {max_retries} attempts"
    ) from last_error


def _write_batch(tx: ManagedTransaction, query: str, batch: list[dict]) -> None:
    tx.run(query, rows=batch)


def ingest(
    driver: Driver,
    label: str,
    query: str,
    rows: list[dict],
    database: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Ingest ``rows`` via batched, managed write transactions.

    Returns the number of rows submitted.
    """
    if not rows:
        logger.info("[%s] nothing to ingest.", label)
        return 0

    total = len(rows)
    with driver.session(database=database) as session:
        for start in range(0, total, batch_size):
            batch = rows[start : start + batch_size]
            session.execute_write(_write_batch, query, batch)
            done = min(start + batch_size, total)
            logger.info("[%s] ingested %d/%d", label, done, total)
    return total


# ---------------------------------------------------------------------------
# Schema + maintenance helpers.
# ---------------------------------------------------------------------------


def apply_constraints(driver: Driver, database: str) -> None:
    """Apply all uniqueness constraints (idempotent via IF NOT EXISTS)."""
    with driver.session(database=database) as session:
        for statement in CONSTRAINTS:
            session.run(statement)
    logger.info("Applied %d uniqueness constraints.", len(CONSTRAINTS))


def reset_graph(driver: Driver, database: str, batch_size: int = 10_000) -> None:
    """Delete all nodes and relationships in batches (optional clean slate)."""
    logger.warning("Resetting graph: deleting all nodes and relationships.")
    deleted = 1
    with driver.session(database=database) as session:
        while deleted:
            result = session.run(
                """
                MATCH (n)
                WITH n LIMIT $limit
                DETACH DELETE n
                RETURN count(n) AS deleted
                """,
                limit=batch_size,
            )
            deleted = result.single()["deleted"]
            if deleted:
                logger.info("Deleted %d nodes.", deleted)
    logger.info("Graph reset complete.")


def report_counts(driver: Driver, database: str) -> dict[str, int]:
    """Return and log node counts per label for post-ingestion verification."""
    labels = ["Farmer", "FarmHolding", "CropCycle", "Transaction", "Organization"]
    counts: dict[str, int] = {}
    with driver.session(database=database) as session:
        for label in labels:
            record = session.run(
                f"MATCH (n:{label}) RETURN count(n) AS c"
            ).single()
            counts[label] = record["c"]
    logger.info("Verification node counts: %s", counts)
    return counts


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------


def load_dataset(
    driver: Driver,
    dataset: SyntheticDataset,
    database: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Apply constraints then ingest all nodes and relationships."""
    apply_constraints(driver, database)

    # Nodes first so relationship MATCHes always resolve.
    node_jobs = [
        ("Organization", UPSERT_ORGANIZATIONS, dataset.organizations),
        ("Farmer", UPSERT_FARMERS, dataset.farmers),
        ("FarmHolding", UPSERT_HOLDINGS, dataset.holdings),
        ("CropCycle", UPSERT_CROP_CYCLES, dataset.crop_cycles),
        ("Transaction", UPSERT_TRANSACTIONS, dataset.transactions),
    ]
    relationship_jobs = [
        ("MEMBER_OF", UPSERT_MEMBER_OF, dataset.member_of),
        ("OWNS", UPSERT_OWNS, dataset.owns),
        ("HAS_CYCLE", UPSERT_HAS_CYCLE, dataset.has_cycle),
        ("EXECUTED", UPSERT_EXECUTED, dataset.executed),
        ("BELONGS_TO", UPSERT_BELONGS_TO, dataset.belongs_to),
    ]

    logger.info("--- Ingesting nodes ---")
    for label, query, rows in node_jobs:
        ingest(driver, label, query, rows, database, batch_size)

    logger.info("--- Ingesting relationships ---")
    for label, query, rows in relationship_jobs:
        ingest(driver, label, query, rows, database, batch_size)


def _read_credentials() -> tuple[str, str, str, str]:
    uri = os.environ.get("NEO4J_URI")
    username = os.environ.get("NEO4J_USERNAME")
    password = os.environ.get("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE", DEFAULT_DATABASE)

    missing = [
        name
        for name, value in (
            ("NEO4J_URI", uri),
            ("NEO4J_USERNAME", username),
            ("NEO4J_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise EnvironmentError(
            "Missing required environment variables: " + ", ".join(missing)
        )
    return uri, username, password, database  # type: ignore[return-value]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic data and batch-ingest it into Neo4j."
    )
    parser.add_argument("--farmers", type=int, default=1_000, help="Farmers to create.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--kenya-ratio", type=float, default=0.5, help="Kenya/Tegemeo fraction."
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="UNWIND batch size."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing nodes/relationships before ingesting.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _parse_args()

    try:
        uri, username, password, database = _read_credentials()
    except EnvironmentError as exc:
        logger.error("%s", exc)
        return 1

    dataset = generate_dataset(
        num_farmers=args.farmers, seed=args.seed, kenya_ratio=args.kenya_ratio
    )

    driver = None
    try:
        driver = create_driver(uri, username, password)
        if args.reset:
            reset_graph(driver, database)
        start = time.perf_counter()
        load_dataset(driver, dataset, database, batch_size=args.batch_size)
        elapsed = time.perf_counter() - start
        report_counts(driver, database)
        logger.info("Ingestion finished in %.1fs.", elapsed)
    except (Neo4jError, ConnectionError) as exc:
        logger.error("Ingestion failed: %s", exc)
        return 1
    finally:
        if driver is not None:
            driver.close()
            logger.info("Driver closed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
