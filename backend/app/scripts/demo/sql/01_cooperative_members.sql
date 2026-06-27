-- Cooperative member registry — the external Postgres source the inbound
-- connector (app.ingestion.connectors.cooperative_sync) pulls from.
--
-- These are exactly the columns the connector's incremental query selects:
--     SELECT member_uuid, farm_acres, harvest_delivered_kg, updated_at FROM cooperative_members
-- (see app/ingestion/connectors/cooperative_sync.py::_build_query). The CDC pull
-- is incremental on updated_at, so that column is mandatory and indexed.
--
-- Mounted into the postgres image's /docker-entrypoint-initdb.d, so it runs once
-- when the data volume is first created. The row data is seeded separately and
-- idempotently by app.scripts.demo.seed_cooperative_pg (roster-aligned), which
-- also CREATE TABLE IF NOT EXISTS, so the seeder works even without this mount.

CREATE TABLE IF NOT EXISTS cooperative_members (
    member_uuid          TEXT PRIMARY KEY,
    farm_acres           NUMERIC,
    harvest_delivered_kg NUMERIC,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The connector filters `WHERE updated_at >= :since` every pass (high-water mark).
CREATE INDEX IF NOT EXISTS idx_cooperative_members_updated_at
    ON cooperative_members (updated_at);
