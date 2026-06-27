"""Neo4j client: shared driver lifecycle + legacy-batch-to-reified ingestion.

This module used to own a second, divergent write path: a ``MERGE``-based
``UNWIND`` transaction that wrote ``(:Farmer)-[:VERIFIED_BY]->(:OffTaker|:Cooperative)``.
That shape was invisible to the reified trust layer (see
:mod:`app.database.trust_graph` / :mod:`app.database.graph_ingestion`) and has
been removed. :func:`persist_claims` now reifies each row into a
:class:`~app.models.reified.PayloadBundle` via
:func:`app.verification.claim_bridge.standard_claim_to_bundle` and writes it
through the single canonical writer,
:class:`app.database.graph_ingestion.GraphIngestionService` —
``(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)``.

Run directly for a quick smoke test against a local Neo4j::

    python -m app.database.neo4j_client    # writes one demo claim
"""

from __future__ import annotations

import logging
import os
from typing import Any

from neo4j import Driver, GraphDatabase

logger = logging.getLogger(__name__)

DEFAULT_DATABASE = "neo4j"
DEFAULT_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Driver lifecycle + high-level helpers.
# ---------------------------------------------------------------------------


def _auth() -> tuple[str, str] | None:
    """Return driver auth, or ``None`` for no-auth local dev.

    The local Docker stack runs Neo4j with ``NEO4J_AUTH=none``; when
    ``NEO4J_PASSWORD`` is unset/empty we connect without credentials.
    """
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        return None
    return (os.environ.get("NEO4J_USERNAME", "neo4j"), password)


def get_driver(uri: str | None = None) -> Driver:
    """Create a verified Neo4j driver from the environment (or an explicit URI)."""
    target = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    driver = GraphDatabase.driver(target, auth=_auth())
    driver.verify_connectivity()
    logger.info("Connected to Neo4j at %s.", target)
    return driver


# A process-wide driver for request handlers (the driver is thread-safe and
# pools connections, so long-lived endpoints should share one rather than
# reconnecting per request). Created lazily; closed on app shutdown.
_shared_driver: Driver | None = None


def get_shared_driver() -> Driver:
    """Return a lazily-created, process-wide shared driver."""
    global _shared_driver
    if _shared_driver is None:
        _shared_driver = get_driver()
    return _shared_driver


def close_shared_driver() -> None:
    """Close and clear the shared driver, if one was created."""
    global _shared_driver
    if _shared_driver is not None:
        _shared_driver.close()
        _shared_driver = None
        logger.info("Closed shared Neo4j driver.")


def persist_claims(
    claims: list[dict[str, Any]],
    driver: Driver | None = None,
    database: str = DEFAULT_DATABASE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ensure_constraints: bool = True,
) -> int:
    """Reify validated claim rows and persist them via :class:`GraphIngestionService`.

    Each row (the shape produced by ``StandardFarmerClaim.to_graph_row()``) is
    rebuilt into a :class:`~app.models.claims.StandardFarmerClaim`, converted to
    a reified :class:`~app.models.reified.PayloadBundle` by
    :func:`app.verification.claim_bridge.standard_claim_to_bundle`, and written
    through the single canonical writer — never the legacy ``VERIFIED_BY`` shape.

    Opens (and closes) its own driver when one is not supplied. Returns the
    total claim rows written.
    """
    if not claims:
        return 0

    # Imported here (not at module level) to keep this module importable
    # without pulling in pydantic/graph_ingestion for callers that only need
    # the driver lifecycle helpers below.
    from app.database.graph_ingestion import GraphIngestionService
    from app.models.claims import StandardFarmerClaim
    from app.verification.claim_bridge import standard_claim_to_bundle

    bundles = [
        standard_claim_to_bundle(StandardFarmerClaim(**row)) for row in claims
    ]

    owns_driver = driver is None
    drv = driver or get_driver()
    try:
        svc = GraphIngestionService(driver=drv, database=database)
        if ensure_constraints:
            svc.ensure_constraints()
        written = svc.ingest_payload_bundles(bundles)
        logger.info("Persisted %d reified claim(s) to Neo4j.", written)
        return written
    finally:
        if owns_driver:
            drv.close()


if __name__ == "__main__":  # pragma: no cover - manual smoke test.
    logging.basicConfig(level=logging.INFO)
    demo = [
        {
            "farmer_id": "DEMO-F1",
            "farmer_name": "Demo Farmer",
            "national_id": None,
            "phone": None,
            "region": "Nakuru",
            "country": "Kenya",
            "crop_type": "Maize",
            "land_size_hectares": 2.02,
            "production_volume_kg": 5000.0,
            "verifier_id": "ORG-TEGEMEO",
            "verifier_name": "Tegemeo Cereals Enterprises",
            "verifier_type": "Cooperative",
            "confidence_score": 0.91,
            "source_id": "tegemeo_cereals",
            "claim_timestamp": "2026-06-24T00:00:00+00:00",
        }
    ]
    print("written:", persist_claims(demo))
