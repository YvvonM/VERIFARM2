"""Raw provider response contracts (Pydantic).

These model the *exact data shape returned by an external API* — a licensed
credit bureau or an accredited KYC intermediary. They are validation contracts,
not mocks: a concrete provider parses its real HTTP response into one of these,
and Pydantic rejects anything malformed at the boundary before it can reach the
domain layer.

Domain boundary: these types belong to the *integration* layer. They are
deliberately dumb data — no graph concepts, no farmer linkage. Translating them
into reified domain claims is the job of :mod:`app.verification.claim_bridge`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreditHistoryResult(BaseModel):
    """A credit report as returned by a licensed bureau."""

    provider: str = Field(..., min_length=1, description="Bureau the report came from, e.g. 'TransUnion Kenya'.")
    credit_score: int = Field(..., ge=0, description="Bureau-style score; scale documented by the provider.")
    has_default_flag: bool = Field(..., description="Whether any past default is on record.")
    repayment_history_summary: str = Field(..., description="Human-readable repayment summary.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Provider-reported confidence in [0, 1].")
    checked_at: datetime = Field(..., description="When the bureau performed the lookup (UTC).")


class IdentityVerificationResult(BaseModel):
    """The result of a KYC identity lookup by an accredited provider."""

    provider: str = Field(..., min_length=1, description="Provider/intermediary, e.g. 'Smile Identity (BVN)'.")
    match: bool = Field(..., description="Whether the identity matched the submitted record.")
    verified_name: str | None = Field(default=None, description="Canonical name on file (None if no match).")
    submitted_identifier_type: str = Field(..., description="'BVN' | 'NIN' | 'national_id' | 'phone'.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Provider-reported confidence in [0, 1].")
    checked_at: datetime = Field(..., description="When the provider performed the lookup (UTC).")
