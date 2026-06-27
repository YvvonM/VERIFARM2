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
