"""Turn merged reified bundles into ``claim.verified`` events and publish them.

Called from the reified publish boundary (``ingestion.reified_guard``) right
after a successful gold-layer merge, so a downstream system learns about a
verified claim without polling. Strictly best-effort — any failure is logged and
swallowed so it can never break the ingestion that produced the claim.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from app.events.models import ClaimVerifiedEvent
from app.events.publishers import get_event_publisher

logger = logging.getLogger(__name__)


def build_claim_events(bundles: Iterable[Any]) -> list[ClaimVerifiedEvent]:
    """Flatten reified ``PayloadBundle`` objects into per-claim events."""
    events: list[ClaimVerifiedEvent] = []
    for bundle in bundles:
        inst = bundle.institution
        farmer = bundle.farmer
        for claim in bundle.claims:
            ts = getattr(claim, "timestamp", None)
            events.append(ClaimVerifiedEvent(
                claim_id=claim.claim_id,
                farmer_id=farmer.farmer_id,
                claim_type=claim.claim_type,
                value_numeric=claim.value_numeric,
                value_string=claim.value_string,
                unit=getattr(claim, "unit", None),
                confidence=claim.confidence,
                observed_at=ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts else None),
                attested_by_id=inst.institution_id,
                attested_by=inst.name,
                attested_by_trust=float(getattr(inst, "initial_trust_score", None) or 0.0),
                authoritative=bool(getattr(inst, "is_authoritative", False)),
            ))
    return events


def publish_claims_merged(bundles: Iterable[Any]) -> int:
    """Publish a ``claim.verified`` event per claim in ``bundles``. Returns count.

    Best-effort: exceptions are logged, never raised — distribution must not
    jeopardize the merge that already succeeded.
    """
    try:
        events = build_claim_events(bundles)
        if not events:
            return 0
        publisher = get_event_publisher()
        for event in events:
            publisher.publish(event.model_dump())
        logger.info("Published %d claim.verified event(s).", len(events))
        return len(events)
    except Exception:  # noqa: BLE001 - distribution is best-effort.
        logger.warning("Event publishing failed (ignored).", exc_info=True)
        return 0
