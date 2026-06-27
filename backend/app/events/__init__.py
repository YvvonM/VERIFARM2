"""Event publishing seam — push verified claims to downstream consumers.

    from app.events import publish_claims_merged
    publish_claims_merged(bundles)   # emits one claim.verified event per claim

Backends (``EVENT_BACKEND``): none (default), webhook, redis. Best-effort — never
breaks the ingestion that produced the events.
"""

from app.events.dispatch import build_claim_events, publish_claims_merged
from app.events.models import ClaimVerifiedEvent
from app.events.publishers import EventPublisher, get_event_publisher

__all__ = [
    "publish_claims_merged",
    "build_claim_events",
    "ClaimVerifiedEvent",
    "EventPublisher",
    "get_event_publisher",
]
