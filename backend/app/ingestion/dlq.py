"""Dead-Letter Queue (DLQ) for records that fail ingestion.

A batch must never be derailed by one malformed record. When a record fails
mapping or Pydantic validation, we append it — together with the reason and the
*original* raw payload — to an append-only JSON Lines file, then carry on with
the rest of the batch. Operators can later inspect, fix, and replay these.

JSON Lines (one JSON object per line) is used deliberately: it is append-safe
under concurrent writers and trivially streamable, unlike a single JSON array
that would need rewriting on every append.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Override with the DLQ_PATH env var; defaults to a git-ignored backend folder.
DEFAULT_DLQ_PATH = Path(__file__).resolve().parents[2] / "dlq" / "ingest_dlq.jsonl"


def dlq_path() -> Path:
    """Resolve the DLQ file path (env-overridable)."""
    return Path(os.environ.get("DLQ_PATH", str(DEFAULT_DLQ_PATH)))


def dead_letter(
    source_id: str,
    index: int,
    errors: list[str],
    raw_record: Any,
    path: Path | None = None,
) -> Path:
    """Append one failed record to the DLQ file and return the file path.

    Args:
        source_id: The source the record came from.
        index: The record's position in the original batch.
        errors: Human-readable validation/mapping messages.
        raw_record: The untouched raw record, preserved for replay.
        path: Optional override of the DLQ file location.

    Returns:
        The path the record was written to.

    Notes:
        Failure to write the DLQ is logged but never raised: losing the audit
        trail for one record must not crash the ingestion request.
    """
    target = path or dlq_path()
    entry = {
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "index": index,
        "errors": errors,
        "raw_record": raw_record,
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        logger.exception("Failed to write record %d to DLQ at %s", index, target)
    return target


# Default file for the bundle-level gateway DLQ (distinct from the adapter DLQ
# above). Override per-instance via the constructor, or globally with DLQ_PATH.
DEFAULT_DLQ_LOG = Path(__file__).resolve().parents[2] / "dlq" / "dlq_logs.jsonl"


class DeadLetterQueue:
    """Append-only sink for payloads that fail Silver-standard validation.

    One malformed payload must never crash the ingestion pipeline. Each failure
    is recorded — payload, error, and a UTC timestamp — as a single JSON Lines
    row, so operators can inspect, fix, and replay later. Writes are best-effort:
    losing the audit line for one payload is never allowed to raise.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        # Precedence: explicit arg → DLQ_PATH env → packaged default.
        self.path = Path(path or os.environ.get("DLQ_PATH", str(DEFAULT_DLQ_LOG)))

    def log_failure(self, raw_payload: dict[str, Any], error_message: str) -> None:
        """Append one failed payload, its error, and a UTC timestamp to the DLQ."""
        entry = {
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "error": error_message,
            "raw_payload": raw_payload,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            # Never let a DLQ write failure propagate into the ingestion path.
            logger.exception("Failed to write a payload to the DLQ at %s", self.path)
