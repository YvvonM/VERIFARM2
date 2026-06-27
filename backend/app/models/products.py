"""Financial-product catalog models for the MATCH engine.

A :class:`FinancialProduct` describes a lender's offer *declaratively*: a
reputation bar for the institutions whose attestations it will trust
(``min_trust_score``) plus a dictionary of per-metric eligibility thresholds
(``eligibility_rules``). Nothing about any specific product is hardcoded in
Python — the rules engine (:mod:`app.database.match_engine`) reads these
thresholds and checks them against a farmer's reified claims in Cypher.

Adding a new product for the demo is a new :class:`FinancialProduct` entry in
:mod:`app.services.product_catalog`; no query or endpoint code changes.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EligibilityRule(BaseModel):
    """Thresholds a single reified claim must clear for one metric.

    ``min`` / ``max`` bound the claim's ``value_numeric``; ``min_confidence``
    bounds the claim's own confidence. A rule is satisfied only if *some* claim
    of the matching ``claim_type`` — attested by a sufficiently-trusted
    institution — meets all three.
    """

    min: Optional[float] = Field(default=None, description="Inclusive lower bound on value_numeric.")
    max: Optional[float] = Field(default=None, description="Inclusive upper bound on value_numeric.")
    min_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum acceptable claim confidence."
    )


class FinancialProduct(BaseModel):
    """A lender's offer and the rules that decide who qualifies for it."""

    product_id: str = Field(..., min_length=1, description="Stable catalog key.")
    lender_name: str = Field(..., min_length=1, description="Institution offering the product.")
    min_trust_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Only claims attested by institutions with at least this "
        "reputation are considered when evaluating eligibility.",
    )
    eligibility_rules: dict[str, EligibilityRule] = Field(
        default_factory=dict,
        description="Map of claim_type → thresholds, e.g. "
        '{"land_size_hectares": {"min": 1.0, "min_confidence": 0.8}}.',
    )


# ---------------------------------------------------------------------------
# Match request / response contract.
# ---------------------------------------------------------------------------


class MatchRequest(BaseModel):
    """Optional body for ``POST /match/{farmer_id}``.

    When ``product_ids`` is omitted the farmer is evaluated against the entire
    catalog; otherwise only the named products are checked.
    """

    product_ids: Optional[list[str]] = Field(
        default=None, description="Subset of catalog product ids to evaluate; all if null."
    )


class RuleEvaluation(BaseModel):
    """Per-rule outcome, surfaced so a UI can explain *why* a farmer (in)eligible."""

    claim_type: str
    satisfied: bool
    required_min: Optional[float] = None
    required_max: Optional[float] = None
    required_min_confidence: Optional[float] = None
    matched_value: Optional[float] = Field(
        default=None, description="value_numeric of the best qualifying claim, if any."
    )
    matched_confidence: Optional[float] = Field(
        default=None, description="Confidence of the best qualifying claim, if any."
    )


class ProductMatch(BaseModel):
    """Whether a farmer qualifies for one product, with the rule-by-rule detail."""

    product_id: str
    lender_name: str
    eligible: bool
    rule_breakdown: list[RuleEvaluation] = Field(default_factory=list)


class MatchResponse(BaseModel):
    """Result of evaluating a farmer against one or more products."""

    farmer_id: str
    matches: list[ProductMatch] = Field(default_factory=list)
