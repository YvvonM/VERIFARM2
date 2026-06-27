"""Sync state / high-water marks for Change Data Capture (CDC).

A connector remembers, per source, the maximum ``updated_at`` (or transaction id)
it has already pulled. The next run fetches only rows *at or after* that mark, so
historical data is never reprocessed — the pull stays cheap as the source grows.
(Re-ingesting the boundary row is harmless because writes are idempotent.)

State is persisted in Neo4j as ``(:SyncState {source_id, high_water_mark})`` — the
platform already depends on Neo4j, so this needs no extra datastore. An in-memory
store is provided for tests and ephemeral runs.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)

SYNC_STATE_CONSTRAINT = (
    "CREATE CONSTRAINT sync_state_source IF NOT EXISTS "
    "FOR (s:SyncState) REQUIRE s.source_id IS UNIQUE"
)
_GET = "MATCH (s:SyncState {source_id: $source_id}) RETURN s.high_water_mark AS hwm"
_SET = (
    "MERGE (s:SyncState {source_id: $source_id}) "
    "SET s.high_water_mark = $hwm, s.updated_at = datetime()"
)


class WatermarkStore(Protocol):
    """Persist and retrieve the high-water mark for a source."""

    def get(self, source_id: str) -> Optional[str]: ...
    def set(self, source_id: str, value: str) -> None: ...


class InMemoryWatermarkStore:
    """Non-persistent store (tests / single-process runs)."""

    def __init__(self) -> None:
        self._marks: dict[str, str] = {}

    def get(self, source_id: str) -> Optional[str]:
        return self._marks.get(source_id)

    def set(self, source_id: str, value: str) -> None:
        self._marks[source_id] = value


class Neo4jWatermarkStore:
    """Durable high-water marks in the graph (one ``:SyncState`` node per source)."""

    def __init__(self, driver, database: str = DEFAULT_DATABASE) -> None:
        self._driver = driver
        self._database = database
        with driver.session(database=database) as session:
            session.run(SYNC_STATE_CONSTRAINT)

    def get(self, source_id: str) -> Optional[str]:
        with self._driver.session(database=self._database) as session:
            record = session.run(_GET, source_id=source_id).single()
            return record["hwm"] if record and record["hwm"] is not None else None

    def set(self, source_id: str, value: str) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(_SET, source_id=source_id, hwm=value)
        logger.info("Advanced high-water mark for %s → %s", source_id, value)
