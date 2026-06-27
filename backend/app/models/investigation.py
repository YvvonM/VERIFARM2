"""Models for the Autonomous DLQ Investigator (data-quality agent).

A :class:`ConflictInvestigation` is the agent's verdict on one
ground-truth-vs-reported discrepancy: the numbers in conflict, the attesting
source's reputation and track record, and a *calculated* recommendation for how
a data steward should resolve it. The recommendation (action / severity /
confidence) is computed deterministically by :mod:`app.investigator.policy`, so
every flag is auditable rather than a black-box guess.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResolutionAction(str, Enum):
    """The recommended way to resolve a flagged conflict."""

    #: Adopt the authoritative value into the gold layer; the reported claim is
    #: demoted but the source is reliable enough not to penalize automatically.
    TRUST_GROUND_TRUTH = "TRUST_GROUND_TRUTH"
    #: Adopt ground truth *and* recommend a reputation penalty for the source
    #: (low trust and/or a repeated pattern of disagreement).
    PENALIZE_SOURCE = "PENALIZE_SOURCE"
    #: A normally-reliable source disagrees in isolation — surprising enough to
    #: warrant a human look rather than an automatic decision.
    FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"
    #: Not enough history/signal to recommend confidently; hold for a steward.
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ConflictSeverity(str, Enum):
    """How far the reported value strays from ground truth."""

    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SourceHistory(BaseModel):
    """The attesting institution's reputation + ground-truth track record."""

    institution_id: str
    institution_name: Optional[str] = None
    trust_score: float = Field(..., ge=0.0, le=1.0)
    comparisons: int = Field(
        default=0, ge=0, description="Ground-truth comparisons from the last reputation pass."
    )
    agreements: int = Field(
        default=0, ge=0, description="Of those comparisons, how many agreed."
    )
    prior_conflicts: int = Field(
        default=0, ge=0,
        description="Distinct claims by this source currently conflicting with ground truth.",
    )

    @property
    def agreement_rate(self) -> Optional[float]:
        """Fraction of past comparisons that agreed, or None if never compared."""
        return self.agreements / self.comparisons if self.comparisons else None


class Recommendation(BaseModel):
    """The calculated resolution recommendation for one conflict."""

    action: ResolutionAction
    severity: ConflictSeverity
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="How sure the policy is about this action."
    )
    rationale: str = Field(..., description="Human-readable justification for the action.")


class ConflictInvestigation(BaseModel):
    """A fully-investigated conflict: the discrepancy, the source, the verdict."""

    farmer_id: str
    claim_type: str

    authoritative_claim_id: str
    authoritative_value: float
    authoritative_source: Optional[str] = None

    reported_claim_id: str
    reported_value: float
    variance: float = Field(..., description="Relative deviation from ground truth (0.20 == 20%).")

    source: SourceHistory
    recommendation: Recommendation

    investigated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
