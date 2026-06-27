"""Framework-agnostic, thread-safe fixed-window rate limiter.

Kept dependency-free (no FastAPI/Pydantic) so it can be shared by both the REST
layer (:mod:`app.api.security`) and the MCP gateway (:mod:`app.mcp.auth`) without
dragging FastAPI into the MCP import path.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Thread-safe fixed-window rate limiter (per key)."""

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = {}  # key -> (count, window_start)

    def allow(self, key: str) -> bool:
        if self.limit <= 0:  # 0/negative disables limiting
            return True
        now = time.monotonic()
        with self._lock:
            count, start = self._buckets.get(key, (0, now))
            if now - start >= self.window:  # window elapsed → reset
                count, start = 0, now
            count += 1
            self._buckets[key] = (count, start)
            self._evict_stale(now)
            return count <= self.limit

    def _evict_stale(self, now: float) -> None:
        """Drop keys whose window has fully elapsed so the bucket map can't grow
        without bound (one entry per distinct API key / client IP). Caller holds the lock."""
        stale = [k for k, (_, start) in self._buckets.items() if now - start >= self.window]
        for k in stale:
            del self._buckets[k]
