"""Gold-layer consumer response models.

Each consumer sees the same Silver graph through a different, purpose-shaped
lens:

  * the **loan officer** reuses :class:`app.models.profiles.FarmerProfileResponse`;
  * the **farmer** (data owner) sees plain-language statuses, never decimals;
  * the **macro** consumer sees anonymized portfolio aggregates only.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Route 2 — Data Owner (Farmer View).
# ---------------------------------------------------------------------------


class DataShare(BaseModel):
    """One institution the farmer has granted access to."""

    institution: str = Field(..., description="Who can currently view the data.")
    basis: str = Field(..., description="How access was granted: EXPLICIT or COLLECTION.")
    since: Optional[str] = Field(default=None, description="When the grant was made (ISO-8601).")


class ClaimStatus(BaseModel):
    """A metric reduced to a plain-language verification status (no decimals)."""

    claim_type: str
    status: str = Field(..., description="'Verified' (ground-truth backed) or 'Unverified'.")


class MyDataResponse(BaseModel):
    """The data owner's own view: what's verified and who is looking."""

    farmer_id: str
    phone_number: Optional[str] = None
    shared_with: list[DataShare] = Field(default_factory=list)
    claims: list[ClaimStatus] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Route 3 — Macro Consumer (Analytics View). Anonymized aggregates only.
# ---------------------------------------------------------------------------


class CooperativeStatsResponse(BaseModel):
    """Portfolio metrics for one institution. Contains NO per-farmer identifiers."""

    institution_id: str
    total_members: int = Field(..., description="Distinct farmers this institution attests about.")
    total_verified_hectares: float = Field(
        ..., description="Sum of ground-truth-verified land across the portfolio."
    )
    unverified_members: int = Field(
        ..., description="Members with no authoritative (ground-truth) attestation."
    )
    missing_credit_history_count: int = Field(
        ..., description="Members with no credit_history claim of any kind."
    )
