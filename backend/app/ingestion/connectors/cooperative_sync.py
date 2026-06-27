"""Cooperative registry sync — CDC pull with state + alerting.

Pipeline for one stakeholder (Tegemeo by default):

    high-water mark ─► Postgres (pooled async, incremental)
                         └─► sql_adapters (strict Pydantic, map)
                               └─► reified_guard.publish_reified
                                     └─► advance high-water mark

State & idempotency (CDC): a :class:`Neo4jWatermarkStore` remembers the max
``updated_at`` pulled per source; each run fetches only rows at/after it, so
history is never reprocessed (and re-doing the boundary row is harmless — writes
are idempotent). Failures (connection/timeout, schema-mapping, write) are routed
to :mod:`app.ingestion.observability` instead of failing silently.

    python -m app.ingestion.connectors.cooperative_sync --once
    python -m app.ingestion.connectors.cooperative_sync --interval 900
    python -m app.ingestion.connectors.cooperative_sync --once --full      # ignore watermark
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from app.ingestion import observability
from app.ingestion.connectors.postgres import SourceNotConfigured, dispose_engines, fetch_all
from app.ingestion.reified_guard import publish_reified
from app.ingestion.sql_adapters import map_registry_rows
from app.ingestion.watermark import Neo4jWatermarkStore, WatermarkStore

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_ID = "tegemeo"


def _build_query(table: str, since: Optional[str]) -> tuple[str, dict]:
    """Select registry columns (+ updated_at for the watermark); incremental on ``since``.

    The table name is the only interpolated token (trusted config); the watermark
    is bound as a real ``datetime`` (asyncpg type-checks bind params, so a stored
    ISO string is parsed back to a datetime rather than passed as text).
    """
    cols = "member_uuid, farm_acres, harvest_delivered_kg, updated_at"
    if since:
        since_dt = datetime.fromisoformat(since) if isinstance(since, str) else since
        return (
            f"SELECT {cols} FROM {table} WHERE updated_at >= :since",
            {"since": since_dt},
        )
    return f"SELECT {cols} FROM {table}", {}


def _max_watermark(rows: list[dict]) -> Optional[str]:
    """Return the maximum ``updated_at`` across rows as an ISO string, or None."""
    marks = []
    for row in rows:
        v = row.get("updated_at")
        if v is None:
            continue
        marks.append(v.isoformat() if hasattr(v, "isoformat") else str(v))
    return max(marks) if marks else None


async def sync_once(
    source_id: str = DEFAULT_SOURCE_ID,
    dsn: Optional[str] = None,
    table: Optional[str] = None,
    since_override: Optional[str] = None,
    full: bool = False,
    neo4j_driver=None,
    watermark_store: Optional[WatermarkStore] = None,
) -> dict:
    """Run one CDC sync pass; return a summary. Raises SourceNotConfigured if no DSN."""
    from app.database.neo4j_client import get_driver

    table = table or os.environ.get("COOP_PG_TABLE", "members")
    owns_driver = neo4j_driver is None
    driver = neo4j_driver or get_driver()
    try:
        store = watermark_store or Neo4jWatermarkStore(driver)
        since = None if full else (since_override or await asyncio.to_thread(store.get, source_id))

        query, params = _build_query(table, since)

        # --- read (connection/timeout failures → alert) ---
        try:
            rows = await fetch_all(query, params, dsn)
        except SourceNotConfigured:
            raise
        except Exception as exc:  # noqa: BLE001
            observability.alert_failure("fetch", exc, source_id=source_id)
            raise

        # --- map (strict Pydantic; rejections → alert) ---
        mapping = map_registry_rows(rows)
        if mapping.rejected:
            observability.notify(
                "Schema mapping rejections",
                f"{len(mapping.rejected)} row(s) failed validation for source {source_id!r}.",
                level="warning",
                category=observability.FailureCategory.MAPPING.value,
                context={"source_id": source_id, "examples": mapping.rejected[:3]},
            )

        # --- write (graph/schema-split failures → alert) ---
        try:
            written = await asyncio.to_thread(publish_reified, driver, mapping.bundles)
        except Exception as exc:  # noqa: BLE001
            observability.alert_failure("publish", exc, source_id=source_id)
            raise

        # --- advance the high-water mark (CDC state) ---
        new_hwm = _max_watermark(rows)
        if new_hwm and new_hwm != since:
            await asyncio.to_thread(store.set, source_id, new_hwm)

        summary = {
            "source_id": source_id,
            "since": since,
            "rows_fetched": len(rows),
            "bundles": len(mapping.bundles),
            "rejected": len(mapping.rejected),
            "claims_written": written,
            "high_water_mark": new_hwm or since,
        }
        logger.info("Cooperative sync: %s", summary)
        return summary
    finally:
        if owns_driver:
            driver.close()


async def _run_loop(interval: float, args) -> None:
    logger.info("Cooperative sync loop every %.0fs (Ctrl-C to stop).", interval)
    try:
        while True:
            try:
                await sync_once(since_override=args.since, full=args.full, table=args.table)
            except SourceNotConfigured as exc:
                logger.error("Not configured: %s", exc)
                return
            except Exception:  # noqa: BLE001 - already alerted; keep the loop alive.
                logger.exception("Sync pass failed; retrying next interval.")
            await asyncio.sleep(interval)
    finally:
        await dispose_engines()


async def _amain(args: argparse.Namespace) -> int:
    if args.interval and not args.once:
        await _run_loop(args.interval, args)
        return 0
    try:
        summary = await sync_once(since_override=args.since, full=args.full, table=args.table)
        import json
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except SourceNotConfigured as exc:
        logger.error("Not configured: %s", exc)
        return 2
    finally:
        await dispose_engines()


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

    parser = argparse.ArgumentParser(description="CDC sync of an external cooperative Postgres registry into Neo4j.")
    parser.add_argument("--once", action="store_true", help="Run a single pass (default).")
    parser.add_argument("--interval", type=float, default=0.0, help="Seconds between passes (loop mode).")
    parser.add_argument("--since", type=str, default=None, help="Override the stored watermark for this run.")
    parser.add_argument("--full", action="store_true", help="Ignore the watermark and pull everything.")
    parser.add_argument("--table", type=str, default=None, help="Source table (default 'members' / COOP_PG_TABLE).")
    args = parser.parse_args()

    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(_main())
