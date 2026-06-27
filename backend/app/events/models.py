"""Consumer-facing event schema.

A ``claim.verified`` event is what downstream systems receive when a claim is
merged into the gold (reified) layer. It mirrors the export schema — flat,
provenance-stamped, and free of internal graph structure (no node ids beyond a
stable ``claim_id`` dedupe key, no Cypher, no labels/relationships).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ClaimVerifiedEvent(BaseModel):
    """Emitted when a verified claim is merged into the gold layer."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = "claim.verified"
    emitted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    claim_id: str = Field(..., description="Stable id; idempotency/dedupe key for consumers.")
    farmer_id: str
    claim_type: str
    value_numeric: Optional[float] = None
    value_string: Optional[str] = None
    unit: Optional[str] = None
    confidence: Optional[float] = None
    observed_at: Optional[str] = None

    attested_by_id: Optional[str] = None
    attested_by: Optional[str] = None
    attested_by_trust: float = 0.0
    authoritative: bool = False
