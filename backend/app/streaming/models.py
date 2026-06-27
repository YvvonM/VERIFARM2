"""Standardized time-series model for IoT/telemetry ingestion.

Diverse sensor payloads (MQTT bridges, vendor gateways) are normalized into this
one shape before anything downstream touches them. ``message_id`` is the
dedup/exactly-once key; ``observed_at`` is the event time (used for ordering /
late-arrival handling), distinct from arrival time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TelemetryReading(BaseModel):
    """One normalized sensor reading."""

    model_config = ConfigDict(extra="ignore")

    message_id: str = Field(..., min_length=1, description="Broker message id — dedup key.")
    sensor_id: str
    farmer_id: str = Field(..., description="Subject the reading is about.")
    metric: str = Field(..., description="e.g. 'soil_moisture_pct', 'air_temperature_c'.")
    value: float
    unit: Optional[str] = None
    observed_at: datetime = Field(..., description="Event time (UTC).")
    source: str = "iot"
