"""Audit logging for bulk ingestion jobs.

Every bulk job records how many rows succeeded, failed Pydantic validation, or
were rejected at the claim_bridge — written to a dedicated metadata "table"
(`(:BulkJobAudit)` nodes in Neo4j, queryable like everything else). An in-memory
store is provided for tests.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)


class BulkJobAudit(BaseModel):
    """One bulk job's outcome counters."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    object_key: str
    total_rows: int = 0
    succeeded: int = 0
    failed_validation: int = 0
    rejected: int = 0
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None

    def finish(self) -> "BulkJobAudit":
        self.finished_at = datetime.now(timezone.utc).isoformat()
        return self


_WRITE_AUDIT = """
MERGE (a:BulkJobAudit {job_id: $job_id})
SET a += {source: $source, object_key: $object_key, total_rows: $total_rows,
          succeeded: $succeeded, failed_validation: $failed_validation,
          rejected: $rejected, started_at: $started_at, finished_at: $finished_at}
"""


class InMemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[BulkJobAudit] = []

    def record(self, audit: BulkJobAudit) -> None:
        self.records.append(audit)


class Neo4jAuditStore:
    def __init__(self, driver, database: str = DEFAULT_DATABASE) -> None:
        self._driver = driver
        self._database = database

    def record(self, audit: BulkJobAudit) -> None:
        with self._driver.session(database=self._database) as session:
            session.run(_WRITE_AUDIT, **audit.model_dump())
        logger.info(
            "Bulk job %s [%s]: %d rows — %d ok, %d invalid, %d rejected.",
            audit.job_id, audit.object_key, audit.total_rows,
            audit.succeeded, audit.failed_validation, audit.rejected,
        )
