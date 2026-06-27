"""Normalize heterogeneous IoT payloads into :class:`TelemetryReading`.

Different gateways speak different dialects (key names, timestamp formats). This
maps the common aliases onto the standard model and parses timestamps (epoch
seconds/millis or ISO-8601). It tolerates late-arriving events (event time is
preserved as-is, never rejected for being old) and duplicate timestamps (when no
message id is supplied, a deterministic one is synthesized from the reading's
natural key, so an identical re-send dedupes rather than double-counts).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.streaming.models import TelemetryReading

# alias → canonical field (first present wins)
_ALIASES = {
    "message_id": ("message_id", "messageId", "id", "msg_id"),
    "sensor_id": ("sensor_id", "sensorId", "device_id", "deviceId", "sensor"),
    "farmer_id": ("farmer_id", "farmerId", "farmer", "subject_id"),
    "metric": ("metric", "measurement", "type", "channel"),
    "value": ("value", "reading", "val", "v"),
    "unit": ("unit", "units", "uom"),
    "observed_at": ("observed_at", "timestamp", "ts", "time", "eventTime"),
}


class TelemetryFormatError(ValueError):
    """Raised when a raw payload can't be normalized (missing essentials)."""


def _first(raw: dict, keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in raw and raw[k] is not None:
            return raw[k]
    return None


def _parse_ts(value: Any) -> datetime:
    """Parse epoch seconds/millis or an ISO-8601 string into a UTC datetime."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        # Heuristic: > 1e12 ⇒ milliseconds.
        seconds = value / 1000.0 if value > 1e12 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise TelemetryFormatError(f"Unparseable timestamp: {value!r}") from exc


def normalize(raw: dict) -> TelemetryReading:
    """Map one raw payload onto a :class:`TelemetryReading` (raises on bad input)."""
    sensor_id = _first(raw, _ALIASES["sensor_id"])
    farmer_id = _first(raw, _ALIASES["farmer_id"])
    metric = _first(raw, _ALIASES["metric"])
    value = _first(raw, _ALIASES["value"])
    if sensor_id is None or farmer_id is None or metric is None or value is None:
        raise TelemetryFormatError(
            f"Missing required field(s) in payload (need sensor/farmer/metric/value): {raw!r}"
        )

    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise TelemetryFormatError(f"Non-numeric value: {value!r}") from exc

    observed_at = _parse_ts(_first(raw, _ALIASES["observed_at"]))

    message_id = _first(raw, _ALIASES["message_id"])
    if not message_id:
        # Deterministic natural key → identical re-sends dedupe; same-timestamp
        # readings from different sensors/metrics stay distinct.
        nk = f"{sensor_id}|{farmer_id}|{metric}|{observed_at.isoformat()}"
        message_id = "tel_" + hashlib.sha1(nk.encode("utf-8")).hexdigest()[:20]

    return TelemetryReading(
        message_id=str(message_id),
        sensor_id=str(sensor_id),
        farmer_id=str(farmer_id),
        metric=str(metric),
        value=value,
        unit=_first(raw, _ALIASES["unit"]),
        observed_at=observed_at,
        source=str(raw.get("source", "iot")),
    )
