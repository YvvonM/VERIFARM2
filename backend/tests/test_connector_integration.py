"""Integration tests for the pooled async Postgres connector.

Runs against a real, ephemeral Postgres in a container (testcontainers). Verifies:
  * correct reified bundle generation from live rows (incl. skip of invalid rows),
  * idempotency (deterministic claim ids),
  * pool resiliency to a full pool dispose, and
  * pool_pre_ping recovery after the DB drops the connection underneath us.

Skipped automatically when the optional deps (sqlalchemy/asyncpg/testcontainers)
or Docker are unavailable, so it never breaks a lightweight environment.

    pip install -r requirements.txt -r requirements-dev.txt
    pytest tests/test_connector_integration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Needs a live Postgres (testcontainers/Docker) — excluded from the default CI
# run via `-m "not integration"`.
pytestmark = pytest.mark.integration

# Optional deps — skip the whole module if any are missing.
pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")
pytest.importorskip("testcontainers.postgres")

from sqlalchemy import create_engine, text  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ingestion.connectors import postgres as pg  # noqa: E402
from app.ingestion.sql_adapters import ACRES_TO_HECTARES, extract_and_map_tegemeo_data  # noqa: E402

_DDL = """
CREATE TABLE members (
    member_uuid          text,
    farm_acres           numeric,
    harvest_delivered_kg numeric,
    updated_at           timestamptz DEFAULT now()
);
"""
_SEED = """
INSERT INTO members (member_uuid, farm_acres, harvest_delivered_kg) VALUES
  ('M-1', 2.0, 500),     -- two claims
  ('M-2', 1.0, NULL),    -- one claim
  (NULL,  9.9, 100),     -- invalid: no member_uuid -> skipped
  ('M-3', NULL, NULL);   -- no usable metric -> skipped
"""

_ALL = "SELECT member_uuid, farm_acres, harvest_delivered_kg FROM members"


@pytest.fixture(scope="module")
def dsn():
    """A seeded throwaway Postgres; yields a plain DSN for the async connector."""
    try:
        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception as exc:  # noqa: BLE001 - Docker not available here.
        pytest.skip(f"Docker/Postgres unavailable: {exc}")

    try:
        url = container.get_connection_url()  # postgresql+psycopg2://...
        sync_engine = create_engine(url)
        with sync_engine.begin() as conn:
            conn.execute(text(_DDL))
            conn.execute(text(_SEED))
        sync_engine.dispose()
        # Our connector adds the asyncpg driver itself, so hand it a plain DSN.
        yield url.replace("postgresql+psycopg2://", "postgresql://")
    finally:
        container.stop()


@pytest.fixture(autouse=True)
async def _dispose_pools():
    yield
    await pg.dispose_engines()


async def test_pooled_fetch_generates_correct_reified_bundles(dsn):
    rows = await pg.fetch_all(_ALL, {}, dsn)
    assert len(rows) == 4

    bundles = extract_and_map_tegemeo_data(rows)
    by_farmer = {b.farmer.farmer_id: b for b in bundles}
    # Invalid (no uuid) and metric-less rows are dropped at the strict boundary.
    assert set(by_farmer) == {"M-1", "M-2"}

    m1 = by_farmer["M-1"]
    assert {c.claim_type for c in m1.claims} == {"land_size_hectares", "production_volume_kg"}
    land = next(c for c in m1.claims if c.claim_type == "land_size_hectares")
    assert round(land.value_numeric, 4) == round(2.0 * ACRES_TO_HECTARES, 4)
    assert m1.institution.institution_id == "ORG-TEGEMEO" and m1.institution.is_authoritative is False


async def test_claim_ids_are_deterministic_for_idempotent_resync(dsn):
    rows = await pg.fetch_all(_ALL, {}, dsn)
    ids1 = sorted(c.claim_id for b in extract_and_map_tegemeo_data(rows) for c in b.claims)
    ids2 = sorted(c.claim_id for b in extract_and_map_tegemeo_data(rows) for c in b.claims)
    assert ids1 == ids2 and len(ids1) == 3  # M-1 (2) + M-2 (1)


async def test_pool_survives_full_dispose(dsn):
    r1 = await pg.fetch_all("SELECT count(*) AS n FROM members", {}, dsn)
    assert r1[0]["n"] == 4
    await pg.dispose_engines()                                   # drop the entire pool
    r2 = await pg.fetch_all("SELECT count(*) AS n FROM members", {}, dsn)
    assert r2[0]["n"] == 4                                       # engine transparently rebuilt


async def test_pre_ping_recovers_a_dropped_connection(dsn):
    assert (await pg.fetch_all("SELECT 1 AS one", {}, dsn))[0]["one"] == 1
    # Simulate the DB killing connections out from under the pool.
    await pg.fetch_all(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE pid <> pg_backend_pid() AND datname = current_database()",
        {}, dsn,
    )
    # pool_pre_ping detects the dead connection and reconnects rather than raising.
    assert (await pg.fetch_all("SELECT 1 AS one", {}, dsn))[0]["one"] == 1
