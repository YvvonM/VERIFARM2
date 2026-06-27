"""
Loads a generated FakeDataset into a real Neo4j instance via the official
driver, using idempotent MERGE-based UNWIND batch writes -- the same
pattern your data-pipeline teammate's neo4j_loader.py already uses for the
Gold layer load, so both loaders behave consistently (safe to re-run,
no duplicate nodes/relationships on repeated execution).

CONNECTION:
Reads NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD from environment variables
(matching the .env convention already established in the project README).

USAGE:
    python3 -m data_generation.neo4j_loader                 # load only
    python3 -m data_generation.neo4j_loader --reset         # wipe fake data first, then load
    python3 -m data_generation.neo4j_loader --dry-run       # validate + print counts, no DB writes

SAFETY:
--reset only deletes nodes that this script itself creates (identified by
the id-prefix convention: farmer_, holding_, cycle_, txn_, claim_, consent_,
org_ used by data_pools.py / farmer_bundle_generator.py). It will NOT touch
real Gold-layer data your teammate has loaded under different id schemes --
but double-check your teammate's actual id conventions before running
--reset against a shared database, in case of an accidental overlap.
"""

import argparse
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

from app.data_generation.generate_dataset import generate
from app.data_generation.graph_model import FakeDataset
from app.data_generation.validate_dataset import validate_dataset

load_dotenv()

# Batch size for UNWIND writes -- large enough to be efficient, small
# enough to avoid one giant transaction. 30 farmers is tiny either way,
# but this keeps the loader correct if the farmer count grows later.
BATCH_SIZE = 500

# id prefixes this generator owns -- used by --reset to scope deletion to
# only the fake data this script created, not real Gold-layer data.
_OWNED_ID_PREFIXES = ("farmer_", "holding_", "cycle_", "txn_", "claim_", "consent_", "org_")


def _get_driver():
    uri = os.environ["NEO4J_URI"]
    username = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    return GraphDatabase.driver(uri, auth=(username, password))


def _ensure_constraints(session) -> None:
    """
    Uniqueness constraints on `id` per label -- required for MERGE-based
    idempotent loading to behave correctly (without a constraint, MERGE on
    a non-indexed property is slow and, more importantly, doesn't protect
    against duplicate creation if two processes race).
    """
    labels = ["Farmer", "FarmHolding", "CropCycle", "Transaction", "Organization",
              "Claim", "Document", "ConsentGrant"]
    for label in labels:
        session.run(
            f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        )


def _load_nodes(session, dataset: FakeDataset) -> None:
    # Group nodes by label so each UNWIND batch is homogeneous -- required
    # since Cypher node labels can't be parameterized.
    nodes_by_label: dict[str, list[dict]] = {}
    for node in dataset.nodes:
        nodes_by_label.setdefault(node.label, []).append(node.properties)

    for label, props_list in nodes_by_label.items():
        for i in range(0, len(props_list), BATCH_SIZE):
            batch = props_list[i:i + BATCH_SIZE]
            session.run(
                f"""
                UNWIND $batch AS props
                MERGE (n:{label} {{id: props.id}})
                SET n += props
                """,
                batch=batch,
            )


def _load_relationships(session, dataset: FakeDataset) -> None:
    # Group by (start_label, rel_type, end_label) for the same reason as
    # nodes -- labels and relationship types can't be parameterized.
    rels_by_triple: dict[tuple[str, str, str], list[dict]] = {}
    for rel in dataset.relationships:
        key = (rel.start_label, rel.rel_type, rel.end_label)
        rels_by_triple.setdefault(key, []).append(
            {"start_id": rel.start_id, "end_id": rel.end_id, "properties": rel.properties}
        )

    for (start_label, rel_type, end_label), rel_list in rels_by_triple.items():
        for i in range(0, len(rel_list), BATCH_SIZE):
            batch = rel_list[i:i + BATCH_SIZE]
            session.run(
                f"""
                UNWIND $batch AS row
                MATCH (a:{start_label} {{id: row.start_id}})
                MATCH (b:{end_label} {{id: row.end_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += row.properties
                """,
                batch=batch,
            )


def _reset_owned_data(session) -> None:
    """
    Deletes only nodes whose id starts with one of this generator's owned
    prefixes. Relationships attached to those nodes are detached
    automatically via DETACH DELETE.
    """
    for prefix in _OWNED_ID_PREFIXES:
        session.run(
            """
            MATCH (n)
            WHERE n.id STARTS WITH $prefix
            DETACH DELETE n
            """,
            prefix=prefix,
        )


def load_to_neo4j(dataset: FakeDataset, reset: bool = False) -> None:
    driver = _get_driver()
    try:
        with driver.session() as session:
            _ensure_constraints(session)

            if reset:
                print("Resetting previously-loaded fake data (owned id prefixes only)...")
                _reset_owned_data(session)

            print(f"Loading {len(dataset.nodes)} nodes...")
            _load_nodes(session, dataset)

            print(f"Loading {len(dataset.relationships)} relationships...")
            _load_relationships(session, dataset)

        print("Load complete.")
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load fake VeriFarm dataset into Neo4j")
    parser.add_argument("--reset", action="store_true", help="Delete previously-loaded fake data first")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print counts only, no DB writes")
    args = parser.parse_args()

    dataset = generate()
    print(dataset.summary())
    print()

    validation = validate_dataset(dataset)
    if not validation.is_valid:
        print("Validation FAILED -- aborting, will not write invalid data to Neo4j.")
        for error in validation.errors:
            print(f"  - {error}")
        return

    print("Validation passed.")
    print()

    if args.dry_run:
        print("Dry run -- no data written to Neo4j.")
        return

    load_to_neo4j(dataset, reset=args.reset)


if __name__ == "__main__":
    main()