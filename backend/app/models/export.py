"""Response models for the outbound export API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExportedClaim(BaseModel):
    """One verified claim, flattened for downstream ETL."""

    claim_id: Optional[str] = None
    farmer_id: str
    claim_type: str
    value_numeric: Optional[float] = None
    value_string: Optional[str] = None
    unit: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: Optional[str] = None
    attested_by_id: Optional[str] = None
    attested_by: Optional[str] = None
    attested_by_trust: float = 0.0
    authoritative: bool = False


class ClaimExportPage(BaseModel):
    """A page of exported claims with the cursor to fetch the next one."""

    count: int = Field(..., description="Number of claims in this page.")
    offset: int
    limit: int
    next_offset: Optional[int] = Field(
        default=None, description="Pass as ?offset= to fetch the next page; null when exhausted."
    )
    claims: list[ExportedClaim]


class FarmerClaimsExport(BaseModel):
    """All verified claims for a single farmer."""

    farmer_id: str
    count: int
    claims: list[ExportedClaim]


class ExportedOrganization(BaseModel):
    """An institution as seen by external consumers."""

    institution_id: str
    name: Optional[str] = None
    type: Optional[str] = None
    trust_score: float = 0.0
    is_authoritative: bool = False
    verified: bool = False


class OrganizationExportPage(BaseModel):
    """A page of organizations with the cursor to fetch the next one."""

    count: int
    offset: int
    limit: int
    next_offset: Optional[int] = None
    organizations: list[ExportedOrganization]
