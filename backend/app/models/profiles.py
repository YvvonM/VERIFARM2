"""Response models for the Loan Officer Dashboard read API.

The payload the frontend renders into a verification dashboard: a farmer, and
their verified history as a map of ``claim_type`` → the list of attestations for
that metric. Each :class:`ClaimDetail` flattens the attesting institution into
``source_name`` / ``is_authoritative`` / ``reputation_score`` so the UI can
highlight ground-truth sources and rank by reputation without extra nesting.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ClaimDetail(BaseModel):
    """A single attestation of a metric, flattened for the dashboard."""

    value_numeric: Optional[float] = Field(
        default=None, description="Quantitative value (None for categorical claims)."
    )
    confidence: float = Field(..., description="The source's confidence in this claim, [0, 1].")
    source_name: str = Field(..., description="Name of the attesting institution.")
    is_authoritative: bool = Field(
        default=False, description="True for ground-truth sources — the UI highlights these."
    )
    reputation_score: Optional[float] = Field(
        default=None, description="Attesting institution's global reputation (trust_score)."
    )


class FarmerProfileResponse(BaseModel):
    """The full verified history for one farmer — the dashboard payload."""

    farmer_id: str
    phone_number: Optional[str] = None
    verified_history: dict[str, list[ClaimDetail]] = Field(
        default_factory=dict,
        description="Map of claim_type → attestations, each list sorted "
        "authoritative-first then by descending reputation.",
    )
