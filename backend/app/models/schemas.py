"""
VeriFarm — Pydantic Schemas
============================

Request and response models for onboarding and verification APIs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class FarmerRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Farmer's full name")
    phone: str = Field(..., min_length=8, max_length=20, description="Primary phone number (used as farmer ID)")
    country: str = Field(..., min_length=2, max_length=50, description="Country of residence")
    location: str | None = Field(None, description="Town/village or GPS description")
    consent: bool = Field(..., description="Farmer consents to data sharing with VeriFarm partners")


class IdentityVerifyRequest(BaseModel):
    national_id: str = Field(..., min_length=5, max_length=30, description="National ID, BVN, or NIN")


class LandVerifyRequest(BaseModel):
    self_reported_hectares: float = Field(..., gt=0, le=10000, description="Self-reported farm size in hectares")
    latitude: float | None = Field(None, ge=-90, le=90, description="GPS latitude")
    longitude: float | None = Field(None, ge=-180, le=180, description="GPS longitude")
    use_satellite: bool = Field(True, description="Whether to cross-check with Sentinel-2 satellite data")


class ProductionVerifyRequest(BaseModel):
    estimated_tons: float = Field(..., gt=0, le=10000, description="Estimated production in tons")
    season: str = Field(..., min_length=1, max_length=50, description="Growing season (e.g. '2024 Long Rains')")
    crop_type: str = Field(..., min_length=1, max_length=50, description="Primary crop (e.g. 'Maize', 'Cassava')")


class CreditVerifyRequest(BaseModel):
    consent_for_credit_check: bool = Field(..., description="Explicit consent to query credit bureau")


class ConflictResolveRequest(BaseModel):
    keep_claim_id: str = Field(..., description="Claim ID to keep as authoritative")
    archive_claim_ids: list[str] = Field(default_factory=list, description="Claim IDs to archive/demote")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class Offer(BaseModel):
    product: str
    provider: str
    max_amount: float | None = None
    interest_rate: str | None = None
    premium: str | None = None
    tenor: str | None = None
    eligibility: str


class OnboardingStatusResponse(BaseModel):
    farmer_id: str
    name: str
    current_step: str
    completed_steps: list[str]
    pending_steps: list[str]
    has_conflicts: bool
    risk_score: int
    completeness: int
    status: str
    status_reason: str
    offers: list[Offer]


class VerificationStepResponse(BaseModel):
    step: str
    status: str
    claim_id: str | None = None
    next_step: str | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)