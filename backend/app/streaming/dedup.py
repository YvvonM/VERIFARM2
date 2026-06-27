"""Stateful deduplication for exactly-once-ish telemetry processing.

RabbitMQ delivers at-least-once (a crash before ack ⇒ redelivery). Combining
that with (a) an idempotent reified write (deterministic claim ids) and (b) this
store — which records the message ids already *committed* as bundles — gives
effectively exactly-once semantics: a redelivered, already-committed message is
filtered out before it is reprocessed.

Backends via ``STREAM_DEDUP_BACKEND``: ``memory`` (per-process; loses state on
restart) or ``redis`` (durable/shared — required for true cross-restart EO).
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class DedupStore(Protocol):
    async def filter_new(self, ids: list[str]) -> set[str]: ...
    async def mark_committed(self, ids: list[str]) -> None: ...
    async def seen(self, message_id: str) -> bool: ...


class InMemoryDedupStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def filter_new(self, ids: list[str]) -> set[str]:
        return {i for i in ids if i not in self._seen}

    async def mark_committed(self, ids: list[str]) -> None:
        self._seen.update(ids)

    async def seen(self, message_id: str) -> bool:
        return message_id in self._seen


class RedisDedupStore:
    def __init__(self, url: str, key: str = "verifarms:committed_telemetry") -> None:
        self._url = url
        self._key = key
        self._client = None

    def _redis(self):
        if self._client is None:
            import redis.asyncio as redis  # lazy

            self._client = redis.Redis.from_url(self._url, decode_responses=True)
        return self._client

    async def filter_new(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        flags = await self._redis().smismember(self._key, ids)
        return {i for i, f in zip(ids, flags) if not f}

    async def mark_committed(self, ids: list[str]) -> None:
        if ids:
            await self._redis().sadd(self._key, *ids)

    async def seen(self, message_id: str) -> bool:
        return bool(await self._redis().sismember(self._key, message_id))


def get_dedup_store() -> DedupStore:
    backend = os.environ.get("STREAM_DEDUP_BACKEND", "memory").lower()
    if backend == "redis":
        return RedisDedupStore(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    return InMemoryDedupStore()
