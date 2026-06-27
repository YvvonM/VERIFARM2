"""Micro-batching buffer — flush on size OR age, to cut graph write IOPS.

Rather than writing every sensor tick to the claim_bridge, the worker buffers
items and flushes a batch when it reaches ``max_size`` or when the oldest item
has waited ``max_age_seconds`` (a fixed time window). Pure, broker-agnostic
logic — the worker decides *when* to call :meth:`drain` based on these signals.
"""

from __future__ import annotations

import time
from typing import Any, Optional


class MicroBatcher:
    def __init__(self, max_size: int = 500, max_age_seconds: float = 300.0) -> None:
        self.max_size = max_size
        self.max_age = max_age_seconds
        self._buf: list[Any] = []
        self._first_added: Optional[float] = None

    def add(self, item: Any) -> None:
        if not self._buf:
            self._first_added = time.monotonic()
        self._buf.append(item)

    @property
    def size(self) -> int:
        return len(self._buf)

    def size_full(self) -> bool:
        return len(self._buf) >= self.max_size

    def age_due(self) -> bool:
        return (
            bool(self._buf)
            and self._first_added is not None
            and (time.monotonic() - self._first_added) >= self.max_age
        )

    def should_flush(self) -> bool:
        return self.size_full() or self.age_due()

    def drain(self) -> list[Any]:
        """Return the buffered items and reset (the window restarts on next add)."""
        batch, self._buf, self._first_added = self._buf, [], None
        return batch
