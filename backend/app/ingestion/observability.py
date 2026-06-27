"""Failure routing for the ingestion pipeline — alert instead of failing silently.

Two responsibilities:
  * :func:`classify` — bucket an exception into a failure category (connection /
    timeout, schema-mapping, write, unknown), so alerts are actionable.
  * :func:`notify` — route an alert to a webhook (Slack-compatible) when
    ``ALERT_WEBHOOK_URL`` is set, and always log it. :func:`alert_failure`
    composes the two for an exception.

Connection timeouts and schema-mapping failures in the connector/``sql_adapters``
therefore surface as notifications, not silent no-ops.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    CONNECTION = "connection"   # timeouts, dropped/unreachable DB
    MAPPING = "mapping"         # schema/validation failures in sql_adapters
    WRITE = "write"             # graph write / schema-split violations
    UNKNOWN = "unknown"


_CONNECTION_NAMES = {
    "OperationalError", "InterfaceError", "DBAPIError", "TimeoutError",
    "ConnectionError", "ConnectTimeout", "ServiceUnavailable", "OSError",
}
_MAPPING_NAMES = {"ValidationError", "MappingError"}
_WRITE_NAMES = {"GoldLayerWriteError", "Neo4jError", "SessionError", "ClientError"}


def classify(exc: BaseException) -> FailureCategory:
    """Bucket an exception into a failure category (heuristic, name + message)."""
    name = type(exc).__name__
    msg = str(exc).lower()
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError)):
        return FailureCategory.CONNECTION
    if name in _CONNECTION_NAMES or "timeout" in msg or "connection refused" in msg:
        return FailureCategory.CONNECTION
    if name in _MAPPING_NAMES or "validation" in msg:
        return FailureCategory.MAPPING
    if name in _WRITE_NAMES or "gold-layer" in msg:
        return FailureCategory.WRITE
    return FailureCategory.UNKNOWN


def notify(
    subject: str,
    message: str,
    *,
    level: str = "error",
    category: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """Always log the alert; POST it to ``ALERT_WEBHOOK_URL`` when configured."""
    payload = {
        "level": level,
        "category": category,
        "subject": subject,
        "message": message,
        "context": context or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.error("ALERT [%s/%s] %s — %s | %s", level, category, subject, message, context or {})

    url = os.environ.get("ALERT_WEBHOOK_URL")
    if url:
        try:
            import requests

            requests.post(
                url,
                json={"text": f"[{level.upper()}/{category}] {subject}: {message}", **payload},
                timeout=10,
            )
        except Exception:  # noqa: BLE001 - a broken alert channel must not crash the pipeline.
            logger.exception("Alert webhook POST failed.")


def alert_failure(stage: str, exc: BaseException, *, source_id: Optional[str] = None) -> FailureCategory:
    """Classify + notify for a pipeline-stage failure; returns the category."""
    category = classify(exc)
    notify(
        f"Ingestion failure: {stage}",
        f"{type(exc).__name__}: {exc}",
        level="error",
        category=category.value,
        context={"source_id": source_id, "stage": stage},
    )
    return category
