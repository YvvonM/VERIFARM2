"""Idempotent lookup cache for external registry calls.

During high-volume ingestion many claims resolve to the *same* registry query
(e.g. the same land parcel). Caching the result for a TTL means we hit the
external government/certification API once, not once per claim — protecting both
their rate limits and our latency.

Backends via ``REGISTRY_CACHE_BACKEND``: ``memory`` (default, per-process TTL) or
``redis`` (shared across workers). ``redis`` is lazily imported.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)

DEFAULT_TTL = 86400  # 24h — registry facts change slowly


def cache_key(namespace: str, **params: Any) -> str:
    """Stable key from a namespace + sorted params (identical lookups collide)."""
    blob = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha1(blob.encode("utf-8")).hexdigest()[:20]
    return f"{namespace}:{digest}"


class AsyncCache(Protocol):
    async def get(self, key: str) -> Optional[str]: ...
    async def set(self, key: str, value: str, ttl: int = DEFAULT_TTL) -> None: ...


class TTLCache:
    """Per-process cache with TTL and a bounded size (LRU-ish eviction)."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._store: dict[str, tuple[float, str]] = {}  # key -> (expires_at, value)
        self._max_size = max_size

    async def get(self, key: str) -> Optional[str]:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.time() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl: int = DEFAULT_TTL) -> None:
        if len(self._store) >= self._max_size:
            # Evict the soonest-to-expire entry to stay bounded.
            oldest = min(self._store, key=lambda k: self._store[k][0])
            self._store.pop(oldest, None)
        self._store[key] = (time.time() + ttl, value)


class RedisCache:
    """Shared cache backed by Redis (async client)."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client = None

    def _redis(self):
        if self._client is None:
            import redis.asyncio as redis  # lazy

            self._client = redis.Redis.from_url(self._url, decode_responses=True)
        return self._client

    async def get(self, key: str) -> Optional[str]:
        return await self._redis().get(key)

    async def set(self, key: str, value: str, ttl: int = DEFAULT_TTL) -> None:
        await self._redis().set(key, value, ex=ttl)


_CACHE: Optional[AsyncCache] = None


def get_cache() -> AsyncCache:
    """Return the configured cache (memoized per process)."""
    global _CACHE
    if _CACHE is None:
        backend = os.environ.get("REGISTRY_CACHE_BACKEND", "memory").lower()
        if backend == "redis":
            _CACHE = RedisCache(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        else:
            _CACHE = TTLCache()
        logger.info("Registry cache backend: %s", backend)
    return _CACHE
