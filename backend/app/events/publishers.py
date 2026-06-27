"""Event publisher backends, chosen by ``EVENT_BACKEND`` (none | webhook | redis).

  * none     — default; no-op (debug log). Nothing is emitted until configured.
  * webhook  — HTTP POST the event JSON to each URL in ``EVENT_WEBHOOK_URLS``
               (comma-separated). For consumers that prefer push over polling.
  * redis    — PUBLISH to ``EVENT_REDIS_CHANNEL`` on ``REDIS_URL`` (Pub/Sub), for
               fan-out to many subscribers / a message bus.

Publishing is always **best-effort**: a broken sink must never fail the
ingestion that produced the event.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class EventPublisher(Protocol):
    def publish(self, event: dict[str, Any]) -> None: ...


class NullEventPublisher:
    """Default sink: emits nothing (debug log only)."""

    def publish(self, event: dict[str, Any]) -> None:
        logger.debug("event (no backend configured): %s %s", event.get("event_type"), event.get("claim_id"))


class WebhookEventPublisher:
    """POST the event to one or more subscriber URLs."""

    def __init__(self, urls: list[str]) -> None:
        self.urls = urls

    def publish(self, event: dict[str, Any]) -> None:
        import requests

        for url in self.urls:
            try:
                requests.post(url, json=event, timeout=5)
            except Exception:  # noqa: BLE001 - a dead subscriber must not break ingestion.
                logger.warning("Webhook POST to %s failed.", url, exc_info=True)


class RedisEventPublisher:
    """PUBLISH the event to a Redis Pub/Sub channel."""

    def __init__(self, url: str, channel: str) -> None:
        self.url = url
        self.channel = channel

    def publish(self, event: dict[str, Any]) -> None:
        try:
            import redis

            client = redis.Redis.from_url(self.url)
            client.publish(self.channel, json.dumps(event, default=str))
        except Exception:  # noqa: BLE001 - broker hiccup must not break ingestion.
            logger.warning("Redis publish to %s failed.", self.channel, exc_info=True)


def get_event_publisher() -> EventPublisher:
    """Return the configured publisher (constructed per call; cheap)."""
    backend = os.environ.get("EVENT_BACKEND", "none").lower()
    if backend in ("none", "", "null"):
        return NullEventPublisher()
    if backend == "webhook":
        urls = [u.strip() for u in os.environ.get("EVENT_WEBHOOK_URLS", "").split(",") if u.strip()]
        if not urls:
            logger.warning("EVENT_BACKEND=webhook but EVENT_WEBHOOK_URLS is empty; emitting nothing.")
            return NullEventPublisher()
        return WebhookEventPublisher(urls)
    if backend == "redis":
        return RedisEventPublisher(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            os.environ.get("EVENT_REDIS_CHANNEL", "verifarms.claims"),
        )
    logger.warning("Unknown EVENT_BACKEND %r; emitting nothing.", backend)
    return NullEventPublisher()
