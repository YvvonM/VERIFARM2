"""Publish demo IoT telemetry to RabbitMQ (Phase 2).

The producer side of the streaming pipeline. It emits sensor readings for the
shared demo roster (:mod:`app.scripts.demo.roster`) onto the queue the consumer
(:mod:`app.streaming.consumer`) drains, so the IoT claims attach to the same
``F-0001 … F-NNNN`` farmers as every other source.

What it demonstrates, by construction:

  * **Windowed-mean aggregation** — several ticks per (farmer, metric) within a
    short window collapse to ONE averaged claim per (farmer, metric).
  * **Exactly-once dedup** — a fraction of messages are re-sent verbatim (same
    ``message_id``); the consumer logs them as duplicates skipped.
  * **Heterogeneous normalization** — a slice of farmers emit a "vendor dialect"
    (aliased keys + epoch-millis timestamps) that ``normalize`` maps onto the
    canonical model, proving the pipeline tolerates mixed gateways.

Every payload is run through the project's own :func:`app.streaming.normalize.normalize`
locally before publishing, so the demo can never silently emit something the
consumer would drop.

    python -m app.scripts.demo.publish_telemetry --farmers 60
    RABBITMQ_URL=amqp://guest:guest@localhost:5672/ python -m app.scripts.demo.publish_telemetry
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone

from app.scripts.demo.roster import DEFAULT_FARMERS, demo_roster
from app.streaming.normalize import normalize

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "telemetry.readings"
LOCAL_DEFAULT_AMQP = "amqp://guest:guest@localhost:5672/"

# (metric, unit, mean, spread) — plausible agronomic ranges.
_METRICS = [
    ("soil_moisture_pct", "%", 32.0, 6.0),
    ("air_temperature_c", "C", 25.0, 4.0),
]


def _canonical(reading: dict) -> dict:
    """A canonical-shape telemetry payload."""
    return reading


def _vendor_dialect(reading: dict) -> dict:
    """Re-key a canonical payload into a 'vendor gateway' dialect.

    Exercises the normalizer's aliasing + epoch-millis timestamp parsing.
    """
    ts = datetime.fromisoformat(reading["observed_at"])
    return {
        "id": reading["message_id"],
        "deviceId": reading["sensor_id"],
        "farmer": reading["farmer_id"],
        "measurement": reading["metric"],
        "reading": reading["value"],
        "uom": reading["unit"],
        "ts": int(ts.timestamp() * 1000),  # epoch millis
        "source": "vendor-gw",
    }


def build_payloads(
    *,
    farmers: int,
    ticks_per_metric: int,
    dup_rate: float,
    vendor_every: int,
    seed: int,
) -> tuple[list[dict], int, int]:
    """Build the list of raw payloads to publish.

    Returns ``(payloads, unique_count, duplicate_count)``. Duplicates are exact
    re-sends (same ``message_id`` and body) appended after the uniques.
    """
    rng = random.Random(seed)
    base = datetime.now(timezone.utc) - timedelta(minutes=4)

    uniques: list[dict] = []
    for f in demo_roster(farmers):
        use_vendor = vendor_every > 0 and f.index % vendor_every == 0
        for metric, unit, mu, spread in _METRICS:
            sensor_id = f"sensor-{f.member_uuid}-{metric.split('_')[0]}"
            for k in range(ticks_per_metric):
                observed = base + timedelta(seconds=30 * k)
                value = round(rng.gauss(mu, spread), 2)
                payload = {
                    "message_id": f"tel-{f.member_uuid}-{metric}-{k}",
                    "sensor_id": sensor_id,
                    "farmer_id": f.member_uuid,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "observed_at": observed.isoformat(),
                    "source": "iot",
                }
                uniques.append(_vendor_dialect(payload) if use_vendor else _canonical(payload))

    # Validate every unique payload through the consumer's own parser so the demo
    # never publishes something that would be dropped downstream.
    for p in uniques:
        normalize(p)

    # Duplicates: re-send a deterministic fraction verbatim (same message_id).
    dups: list[dict] = []
    if dup_rate > 0:
        step = max(1, int(round(1 / dup_rate)))
        dups = [dict(uniques[i]) for i in range(0, len(uniques), step)]

    return uniques + dups, len(uniques), len(dups)


async def publish(payloads: list[dict], *, amqp_url: str, queue: str) -> None:
    import aio_pika

    connection = await aio_pika.connect_robust(amqp_url)
    async with connection:
        channel = await connection.channel()
        # Match the consumer's declaration (durable) so ordering doesn't matter.
        await channel.declare_queue(queue, durable=True)
        for p in payloads:
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(p).encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=queue,
            )


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

    p = argparse.ArgumentParser(description="Publish demo IoT telemetry to RabbitMQ.")
    p.add_argument("--farmers", type=int, default=DEFAULT_FARMERS, help="Roster size (F-0001..F-N).")
    p.add_argument("--amqp-url", type=str, default=None, help="Override RABBITMQ_URL / local default.")
    p.add_argument("--queue", type=str, default=DEFAULT_QUEUE, help="Target queue.")
    p.add_argument("--ticks-per-metric", type=int, default=6,
                   help="Readings per (farmer, metric) to average into one claim.")
    p.add_argument("--dup-rate", type=float, default=0.1,
                   help="Fraction of messages re-sent verbatim to exercise dedup (0 = none).")
    p.add_argument("--vendor-every", type=int, default=10,
                   help="Every Kth farmer emits the vendor dialect (0 = all canonical).")
    p.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible values.")
    args = p.parse_args()

    amqp_url = args.amqp_url or os.environ.get("RABBITMQ_URL") or LOCAL_DEFAULT_AMQP

    payloads, n_unique, n_dup = build_payloads(
        farmers=args.farmers,
        ticks_per_metric=args.ticks_per_metric,
        dup_rate=args.dup_rate,
        vendor_every=args.vendor_every,
        seed=args.seed,
    )
    asyncio.run(publish(payloads, amqp_url=amqp_url, queue=args.queue))

    metrics = ", ".join(m[0] for m in _METRICS)
    print(json.dumps({
        "queue": args.queue,
        "published": len(payloads),
        "unique": n_unique,
        "duplicates": n_dup,
        "farmers": args.farmers,
        "metrics": metrics,
        "expected_claims": f"{args.farmers} farmers × {len(_METRICS)} metrics (one mean claim each)",
    }, indent=2))
    print(
        f"\nPublished {len(payloads)} message(s) ({n_unique} unique + {n_dup} duplicate) "
        f"for {args.farmers} farmers. The consumer should log "
        f"'{n_dup} duplicate(s) skipped' and write ~{args.farmers * len(_METRICS)} averaged claim(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
