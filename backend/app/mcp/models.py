"""Strict Pydantic output models for the MCP tools.

Every tool returns one of these — FastMCP serializes the model's JSON Schema into
the tool's ``outputSchema`` and emits the instance as a clean structured-content
block, so the calling LLM receives well-typed JSON rather than free text.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class VerifiedClaim(BaseModel):
    """One verified claim, flattened for an agent (no graph internals)."""

    claim_id: Optional[str] = None
    claim_type: str
    value_numeric: Optional[float] = None
    value_string: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = 0.0
    attested_by_id: str
    attested_by: Optional[str] = None
    attested_by_trust: float = 0.0
    authoritative: bool = False
    observed_at: Optional[str] = None


class VerifiedClaimsBundle(BaseModel):
    """All verified claims an organization attests to."""

    org_id: str
    count: int
    claims: list[VerifiedClaim]


class ProvenanceStep(BaseModel):
    stage: str = Field(..., description="e.g. 'source_system', 'attestation', 'subject'.")
    actor: str
    detail: str


class ProvenanceTrace(BaseModel):
    """Lineage of a claim back to the originating source system."""

    claim_id: str
    claim_type: str
    attested_by_id: str
    attested_by: Optional[str] = None
    source_system: Optional[str] = Field(default=None, description="Original provenance, e.g. 'sentinel2:<scene>'.")
    observed_at: Optional[str] = None
    authoritative: bool = False
    lineage: list[ProvenanceStep]


class ComplianceStatus(BaseModel):
    """Aggregated safety / trust-tier lookup for an entity."""

    entity_name: str
    entity_id: Optional[str] = None
    found: bool = True
    tier: str = Field(..., description="authoritative | trusted | provisional | unverified")
    trust_score: float = 0.0
    verified: bool = False
    notes: str = ""


class OrgSummary(BaseModel):
    """Concise organization profile for context injection."""

    org_id: str
    name: Optional[str] = None
    type: Optional[str] = None
    trust_score: float = 0.0
    authoritative: bool = False
    tier: str = "unverified"
    claim_count: int = 0


# ---------------------------------------------------------------------------
# Farmer / portfolio / eligibility tools (direct app.database.* call-through —
# see app.mcp.server's second tool group). These never carry phone_number or
# any farmer_id+phone_number pairing, and never carry gender/ethnicity.
# ---------------------------------------------------------------------------


class EligibleFarmerSummary(BaseModel):
    """One farmer row for the lender-facing eligibility search. No phone_number
    field exists on this model at all -- farmer_id and phone are never paired."""

    farmer_id: str
    cooperative_name: Optional[str] = None
    crop_types: list[str] = Field(default_factory=list)
    verified_land_hectares: Optional[float] = None
    trust_score: Optional[float] = Field(
        default=None, description="Highest attesting institution trust_score backing this farmer's claims."
    )
    matched_products: list[str] = Field(
        default_factory=list, description="product_id values this farmer is currently eligible for."
    )


class EligibleFarmersResult(BaseModel):
    total: int
    farmers: list[EligibleFarmerSummary]


class VerifiedHistoryResult(BaseModel):
    """Consent-gated farmer history. ``consent_granted=False`` means NO data was
    read at all -- this is never populated with an empty/zeroed history."""

    farmer_id: str
    consent_granted: bool
    message: str = ""
    verified_history: Optional[dict] = None


class CooperativePortfolio(BaseModel):
    """Anonymized aggregate only -- no farmer_id, no phone_number, ever."""

    institution_id: str
    found: bool = True
    total_members: int = 0
    total_verified_hectares: float = 0.0
    unverified_members: int = 0
    missing_credit_history_count: int = 0


class EligibilityRuleOutcome(BaseModel):
    claim_type: str
    satisfied: bool
    required_min: Optional[float] = None
    required_max: Optional[float] = None
    required_min_confidence: Optional[float] = None
    matched_value: Optional[float] = None
    matched_confidence: Optional[float] = None


class FarmerEligibilityResult(BaseModel):
    farmer_id: str
    product_id: str
    farmer_found: bool
    eligible: bool = False
    rule_breakdown: list[EligibilityRuleOutcome] = Field(default_factory=list)


class VerificationSource(BaseModel):
    claim_type: str
    value: Optional[str] = None
    value_numeric: Optional[float] = None
    attested_by: Optional[str] = None
    institution_trust: float = 0.0
    authoritative: bool = False
    corroborated: bool = False
    observed_at: Optional[str] = None


class VerificationSourcesResult(BaseModel):
    farmer_id: str
    sources: list[VerificationSource] = Field(default_factory=list)
