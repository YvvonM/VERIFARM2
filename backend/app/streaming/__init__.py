"""High-throughput streaming ingestion (Sprint 2 — IoT & telemetry).

  models / normalize — standardized TelemetryReading + diverse-payload normalizer
  microbatch         — size/age windowed buffering (cuts write IOPS)
  dedup              — stateful exactly-once dedup (memory / Redis)
  aggregate          — window → reified bundles (one claim per farmer+metric)
  consumer           — aio_pika RabbitMQ worker tying it together
"""

from app.streaming.aggregate import aggregate_readings
from app.streaming.microbatch import MicroBatcher
from app.streaming.models import TelemetryReading
from app.streaming.normalize import TelemetryFormatError, normalize

__all__ = [
    "TelemetryReading",
    "normalize",
    "TelemetryFormatError",
    "MicroBatcher",
    "aggregate_readings",
]
