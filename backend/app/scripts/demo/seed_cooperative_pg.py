"""Seed the demo cooperative Postgres source (Phase 1).

Populates the ``cooperative_members`` table the inbound connector
(:mod:`app.ingestion.connectors.cooperative_sync`) pulls from, using the shared
roster (:mod:`app.scripts.demo.roster`) so the rows share the ``F-0001 … F-NNNN``
id space with the reified trust layer. Idempotent: ``CREATE TABLE IF NOT EXISTS``
+ ``INSERT … ON CONFLICT (member_uuid) DO UPDATE``, so re-running just refreshes.

Typical demo flow (see scripts/demo_phase1.sh for the full sequence):

    # 1. seed the source DB
    python -m app.scripts.demo.seed_cooperative_pg --farmers 60
    # 2. pull it into the graph
    python -m app.ingestion.connectors.cooperative_sync --once
    # 3. flag the conflicts the live pull introduced
    #    GET /api/v1/investigator/run     (or chat: "investigate land size conflicts")

Demonstrating CDC incrementality (only changed rows re-pulled):

    # bump one member's value + updated_at, then re-run the connector --once;
    # the Neo4j high-water mark means only this row is fetched.
    python -m app.scripts.demo.seed_cooperative_pg --touch F-0005

DSN resolution: ``--dsn`` > ``COOP_PG_DSN`` env > local default
(``postgresql+asyncpg://verifarms:verifarms@localhost:5433/coop``, the port the
demo ``coop-postgres`` compose service publishes).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone

from app.ingestion.connectors.postgres import _normalize_dsn
from app.scripts.demo.roster import (
    DEFAULT_CONFLICT_EVERY,
    DEFAULT_FARMERS,
    cooperative_member_row,
    demo_roster,
    is_conflict,
)

logger = logging.getLogger(__name__)

DEFAULT_TABLE = "cooperative_members"
LOCAL_DEFAULT_DSN = "postgresql+asyncpg://verifarms:verifarms@localhost:5433/coop"

# Fixed base timestamp for the initial seed so the high-water mark is
# deterministic across runs (a later --touch advances past it).
_SEED_TIME = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _resolve_dsn(cli_dsn: str | None) -> str:
    return _normalize_dsn(cli_dsn or os.environ.get("COOP_PG_DSN") or LOCAL_DEFAULT_DSN)


def _create_table_sql(table: str) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {table} ("
        " member_uuid TEXT PRIMARY KEY,"
        " farm_acres NUMERIC,"
        " harvest_delivered_kg NUMERIC,"
        " updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def _upsert_sql(table: str) -> str:
    return (
        f"INSERT INTO {table} (member_uuid, farm_acres, harvest_delivered_kg, updated_at)"
        " VALUES (:member_uuid, :farm_acres, :harvest_delivered_kg, :updated_at)"
        " ON CONFLICT (member_uuid) DO UPDATE SET"
        " farm_acres = EXCLUDED.farm_acres,"
        " harvest_delivered_kg = EXCLUDED.harvest_delivered_kg,"
        " updated_at = EXCLUDED.updated_at"
    )


async def seed(
    *,
    farmers: int,
    dsn: str,
    table: str,
    conflict_every: int,
) -> dict:
    """Create the table (if needed) and UPSERT the whole roster."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    roster = demo_roster(farmers)
    rows = [
        cooperative_member_row(f, updated_at=_SEED_TIME, conflict_every=conflict_every)
        for f in roster
    ]
    conflicts = [f.member_uuid for f in roster if is_conflict(f.index, conflict_every)]

    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_create_table_sql(table)))
            await conn.execute(text(_upsert_sql(table)), rows)
    finally:
        await engine.dispose()

    return {"table": table, "rows_upserted": len(rows), "conflict_members": conflicts}


async def touch(*, member_uuid: str, dsn: str, table: str, factor: float) -> dict:
    """Bump one member's ``updated_at`` to now and scale its land size.

    The value change + fresh timestamp is what a real CDC source would emit; the
    connector's high-water mark then re-pulls *only* this row on the next pass.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    now = datetime.now(timezone.utc)
    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    f"UPDATE {table} SET farm_acres = ROUND(farm_acres * :factor, 2),"
                    " updated_at = :now WHERE member_uuid = :uuid"
                    " RETURNING farm_acres"
                ),
                {"factor": factor, "now": now, "uuid": member_uuid},
            )
            row = result.first()
    finally:
        await engine.dispose()

    if row is None:
        raise SystemExit(f"No such member {member_uuid!r} in {table}; seed first.")
    return {"member_uuid": member_uuid, "new_farm_acres": float(row[0]), "updated_at": now.isoformat()}


def _main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="Seed the demo cooperative Postgres source.")
    p.add_argument("--farmers", type=int, default=DEFAULT_FARMERS, help="Roster size (F-0001..F-N).")
    p.add_argument("--dsn", type=str, default=None, help="Override COOP_PG_DSN / local default.")
    p.add_argument("--table", type=str, default=DEFAULT_TABLE, help="Target table name.")
    p.add_argument("--conflict-every", type=int, default=DEFAULT_CONFLICT_EVERY,
                   help="Every Kth farmer reports an inflated land size (0 = none).")
    p.add_argument("--touch", type=str, default=None, metavar="MEMBER_UUID",
                   help="CDC demo: bump one member's value + updated_at instead of reseeding.")
    p.add_argument("--touch-factor", type=float, default=1.5,
                   help="Multiplier applied to farm_acres by --touch (default 1.5).")
    args = p.parse_args()

    dsn = _resolve_dsn(args.dsn)
    import json

    if args.touch:
        summary = asyncio.run(touch(member_uuid=args.touch, dsn=dsn, table=args.table, factor=args.touch_factor))
        print(json.dumps(summary, indent=2, default=str))
        print(f"\nNow re-pull just this row:  python -m app.ingestion.connectors.cooperative_sync --once")
        return 0

    summary = asyncio.run(
        seed(farmers=args.farmers, dsn=dsn, table=args.table, conflict_every=args.conflict_every)
    )
    print(json.dumps(summary, indent=2, default=str))
    n_conf = len(summary["conflict_members"])
    print(
        f"\nSeeded {summary['rows_upserted']} members into {summary['table']}; "
        f"{n_conf} report an inflated land size (e.g. {', '.join(summary['conflict_members'][:5]) or '—'})."
    )
    print("Next:  python -m app.ingestion.connectors.cooperative_sync --once   "
          "then GET /api/v1/investigator/run")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
