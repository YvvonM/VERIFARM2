"""RabbitMQ telemetry consumer (aio_pika) — the streaming ingestion worker.

Wires the Sprint 2 pieces together:

    RabbitMQ queue ──► normalize ──► MicroBatcher (size/age window)
                                          │ flush
                                          ▼
                     dedup.filter_new ─► aggregate_readings ─► publish_reified
                                          │
                                          ▼  ack messages AFTER commit
                              (exactly-once with the dedup store)

Isolating the worker behind a RabbitMQ queue (fed from the MQTT sensor network)
decouples ingestion from the raw firehose. Messages are acked only *after* the
batch is committed as reified bundles, so a crash mid-flight redelivers — and the
dedup store skips anything already committed.

``aio_pika`` is imported lazily; the broker is configured via ``RABBITMQ_URL``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from app.streaming.aggregate import aggregate_readings
from app.streaming.dedup import get_dedup_store
from app.streaming.microbatch import MicroBatcher
from app.streaming.normalize import TelemetryFormatError, normalize

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "telemetry.readings"
FLUSH_CHECK_INTERVAL = 1.0  # seconds between age-based flush checks


class TelemetryConsumer:
    def __init__(
        self,
        amqp_url: Optional[str] = None,
        queue_name: str = DEFAULT_QUEUE,
        *,
        prefetch: int = 200,
        max_batch: int = 500,
        max_age_seconds: float = 300.0,
        neo4j_driver=None,
    ) -> None:
        self.amqp_url = amqp_url or os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.queue_name = queue_name
        self.prefetch = prefetch
        self.batcher = MicroBatcher(max_batch, max_age_seconds)
        self.dedup = get_dedup_store()
        self._driver = neo4j_driver
        self._lock = asyncio.Lock()
        self.committed = 0  # observability counter

    def _driver_or_default(self):
        if self._driver is None:
            from app.database.neo4j_client import get_driver
            self._driver = get_driver()
        return self._driver

    async def flush(self) -> int:
        """Commit the buffered window: dedup → aggregate → write → ack. Returns claims."""
        async with self._lock:
            items = self.batcher.drain()
            if not items:
                return 0
            readings = [r for r, _msg in items]
            messages = [m for _r, m in items]

            # Exactly-once = collapse within-batch duplicates (same message_id),
            # then drop ids already committed in a previous batch.
            seen_in_batch: set[str] = set()
            unique = []
            for r in readings:
                if r.message_id in seen_in_batch:
                    continue
                seen_in_batch.add(r.message_id)
                unique.append(r)
            new_ids = await self.dedup.filter_new(list(seen_in_batch))
            fresh = [r for r in unique if r.message_id in new_ids]
            duplicates = len(readings) - len(fresh)

            written = 0
            if fresh:
                from app.ingestion.reified_guard import publish_reified

                bundles = aggregate_readings(fresh)
                written = await asyncio.to_thread(publish_reified, self._driver_or_default(), bundles)
                await self.dedup.mark_committed(list(new_ids))
                self.committed += written

            # Ack everything (committed or already-seen duplicate) only now.
            for m in messages:
                await m.ack()
            logger.info(
                "Flushed %d msg(s): %d new, %d duplicate(s) skipped, %d claim(s) written.",
                len(items), len(fresh), duplicates, written,
            )
            return written

    async def run(self, run_seconds: Optional[float] = None) -> None:
        """Consume until cancelled (or ``run_seconds`` elapses — handy for tests)."""
        import aio_pika

        connection = await aio_pika.connect_robust(self.amqp_url)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=self.prefetch)
            queue = await channel.declare_queue(self.queue_name, durable=True)

            stop = asyncio.Event()

            async def _age_flusher():
                while not stop.is_set():
                    await asyncio.sleep(FLUSH_CHECK_INTERVAL)
                    if self.batcher.age_due():
                        await self.flush()

            flusher = asyncio.create_task(_age_flusher())
            logger.info("Telemetry consumer listening on %r.", self.queue_name)

            try:
                async with queue.iterator() as it:
                    async for message in it:
                        try:
                            reading = normalize(json.loads(message.body))
                        except (TelemetryFormatError, json.JSONDecodeError) as exc:
                            logger.warning("Dropping malformed telemetry: %s", exc)
                            await message.ack()  # drop poison (could route to a DLQ instead)
                            continue
                        self.batcher.add((reading, message))
                        if self.batcher.size_full():
                            await self.flush()
                        if run_seconds is not None and run_seconds <= 0:
                            break
            finally:
                stop.set()
                flusher.cancel()
                await self.flush()  # commit whatever's buffered before exiting

    async def run_for(self, run_seconds: float) -> None:
        """Run the consumer for a bounded time (smoke tests / one-shot drains)."""
        try:
            await asyncio.wait_for(self.run(), timeout=run_seconds)
        except asyncio.TimeoutError:
            await self.flush()


def _main() -> int:
    import argparse

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Consume IoT telemetry from RabbitMQ into the reified graph.")
    parser.add_argument("--queue", default=DEFAULT_QUEUE)
    parser.add_argument("--max-batch", type=int, default=500)
    parser.add_argument("--max-age", type=float, default=300.0)
    parser.add_argument("--run-seconds", type=float, default=None, help="Stop after N seconds (smoke test).")
    args = parser.parse_args()

    consumer = TelemetryConsumer(
        queue_name=args.queue, max_batch=args.max_batch, max_age_seconds=args.max_age
    )
    if args.run_seconds:
        asyncio.run(consumer.run_for(args.run_seconds))
    else:
        asyncio.run(consumer.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
