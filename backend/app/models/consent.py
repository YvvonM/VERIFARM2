"""Models for the Farmer Consent / data-access-control flow.

The farmer is the data owner: an institution must request access and the farmer
must explicitly approve before any claim data is readable. These models describe
that handshake — the request a lender raises and the decision a farmer returns
(in the demo, via a simulated USSD/SMS interface).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ConsentStatus(str, Enum):
    """Lifecycle of a (:DataAccessRequest)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class ConsentScope(str, Enum):
    """Structured replacement for a freetext ``scope`` string on a grant.

    * ``SINGLE_INSTITUTION`` — only the requesting/granted institution may read.
    * ``CATEGORY`` — any institution of the granting institution's category may
      read (the cooperative-onboarding default — see
      ``POST /api/v1/cooperative/onboard``: any lender can see a cooperative's
      attested farmers unless the farmer later narrows this).
    * ``UNIVERSAL`` — any institution may read (used for the platform's own
      onboarding flow in ``app.api.onboarding``).
    """

    SINGLE_INSTITUTION = "single_institution"
    CATEGORY = "category"
    UNIVERSAL = "universal"


class ResolutionStatus(str, Enum):
    """The only states a farmer can move a request *to*."""

    APPROVED = "APPROVED"
    DENIED = "DENIED"


# ---------------------------------------------------------------------------
# Part 1 — request / resolution payloads.
# ---------------------------------------------------------------------------


class AccessRequestPayload(BaseModel):
    """A lender asking to view a farmer's profile."""

    institution_id: str = Field(
        ..., min_length=1, description="Requesting institution (lender, NGO, agency, ...)."
    )
    farmer_id: str = Field(..., min_length=1, description="Farmer whose data is requested.")
    scope: ConsentScope = Field(
        default=ConsentScope.SINGLE_INSTITUTION,
        description="How widely this grant applies once approved.",
    )
    purpose: Optional[str] = Field(
        default=None, description="Human-readable reason shown to the farmer."
    )


class ConsentResolutionPayload(BaseModel):
    """A farmer's decision on a pending request (from the USSD/SMS interface)."""

    request_id: UUID = Field(..., description="The request being resolved.")
    status: ResolutionStatus = Field(..., description="APPROVED or DENIED.")
    farmer_id: Optional[str] = Field(
        default=None,
        description="If given, the request is only resolved when it targets this "
        "farmer — guards against resolving someone else's request.",
    )


# ---------------------------------------------------------------------------
# Responses.
# ---------------------------------------------------------------------------


class AccessRequestResponse(BaseModel):
    """The pending request handed back to the lender (and shown to the farmer)."""

    request_id: str
    institution_id: str
    farmer_id: str
    status: ConsentStatus
    scope: ConsentScope
    requested_at: Optional[str] = None


class ConsentResolutionResponse(BaseModel):
    """Outcome of a resolution, including whether access is now active."""

    request_id: str
    institution_id: str
    farmer_id: str
    status: ConsentStatus
    resolved_at: Optional[str] = None
    access_granted: bool = Field(
        ..., description="True only when an active [:GRANTED_ACCESS] edge now exists."
    )


# ---------------------------------------------------------------------------
# Collection-time consent (no request/resolve handshake needed).
# ---------------------------------------------------------------------------


class SourceConsentPayload(BaseModel):
    """Register standing consent obtained when an institution collected the data.

    For sources (registries, partner databases) where the farmer already consented
    at collection, this provisions the access grant directly — the institution
    never has to raise a request.
    """

    institution_id: str = Field(..., min_length=1, description="Institution holding source consent.")
    institution_name: Optional[str] = Field(default=None, description="Display name if new.")
    farmer_ids: list[str] = Field(
        ..., min_length=1, description="Farmers who consented to this institution at collection."
    )
    scope: ConsentScope = Field(
        default=ConsentScope.CATEGORY,
        description="Collection-time grants default to CATEGORY (e.g. any lender may read a "
        "cooperative-onboarded farmer's profile) -- the farmer can later narrow this to "
        "SINGLE_INSTITUTION via the request/resolve handshake.",
    )


class SourceConsentResponse(BaseModel):
    """How many of the supplied farmers were granted (existing nodes only)."""

    institution_id: str
    granted: int = Field(..., description="Number of matched farmers now granted standing access.")
    requested: int = Field(..., description="Number of farmer ids submitted.")
