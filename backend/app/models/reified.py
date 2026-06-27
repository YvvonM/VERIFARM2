"""Reified-graph Pydantic schema — the bronze→silver contract.

This is the gateway every external payload must pass through before it is
allowed near Neo4j. The defining principle is **reification**: we separate the
*Fact* from the *Actor*. A metric is never a property hanging off an edge; it is
a first-class :class:`Claim` node that an :class:`Institution` *attests to* and
that *belongs to* a :class:`Farmer`::

    (Institution)-[:ATTESTS_TO]->(Claim)<-[:BELONGS_TO]-(Farmer)

That topology (and the constraint/index names) matches
:mod:`app.database.trust_graph`, so claims written through this contract are
queryable by the existing traversal and reputation logic.

The :class:`PayloadBundle` is the unit of ingestion: exactly one Institution,
one Farmer, and the list of Claims that institution makes about that farmer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A claim from an authoritative (ground-truth) source is, by definition,
# maximally trusted — its self-reported confidence is pinned to this value.
AUTHORITATIVE_CONFIDENCE = 1.0

# Approved provenance for a verified Claim. Deliberately has no "self_reported"
# member: a figure with no qualifying external source never enters the graph
# as a Claim at all -- it stays a PendingClaim (status "unverified") and is
# invisible to trust traversal (see app.database.trust_graph.VERIFY_CLAIM_QUERY).
SourceCategory = Literal[
    "cooperative", "off_taker", "government", "remote_sensing", "field_officer"
]


class Institution(BaseModel):
    """An *Actor* that attests to facts (a cooperative, off-taker, satellite, ...).

    ``is_authoritative`` marks a ground-truth source (e.g. satellite imagery or a
    government registry). Authoritative attestations are treated as the baseline
    that everyone else is measured against.
    """

    institution_id: str = Field(..., min_length=1, description="Stable unique key (MERGE key).")
    name: str = Field(..., min_length=1, description="Human-readable institution name.")
    is_authoritative: bool = Field(
        default=False, description="True for ground-truth sources (satellite, registry, ...)."
    )
    type: Optional[str] = Field(
        default=None, description="Optional category, e.g. 'Cooperative', 'OffTaker', 'Satellite'."
    )
    consent_at_source: bool = Field(
        default=False,
        description="True when the farmer already consented to this institution at data "
        "collection time. Ingestion then provisions a standing [:GRANTED_ACCESS] edge, so "
        "this institution needs no separate consent request to read the farmer's data.",
    )
    initial_trust_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Seed reputation on first sight; reputation scoring updates it thereafter.",
    )
    can_originate_claims: bool = Field(
        default=True,
        description="True for cooperatives, off-takers, government registries, and "
        "remote-sensing sources -- the institution types allowed to attest to Claims at all. "
        "Defaults true because every Institution built via a PayloadBundle is, by "
        "construction, attesting to at least one Claim. Lenders never build a bundle at all "
        "(they only query) -- app.database.consent merges their Institution node directly "
        "and never sets this flag, so it is false for them.",
    )
    minimum_onboarding_trust: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Trust ceiling for a newly-onboarded institution until its claims are "
        "corroborated by an authoritative source (satellite/government). Prevents a freshly "
        "registered, fake cooperative from onboarding and immediately self-verifying farmers.",
    )


class Farmer(BaseModel):
    """The subject a :class:`Claim` is about."""

    farmer_id: str = Field(..., min_length=1, description="Stable unique key (MERGE key).")
    phone_number: Optional[str] = Field(default=None, description="Contact number, if known.")


class Claim(BaseModel):
    """A reified *Fact*: a single typed assertion about a farmer.

    Exactly one of ``value_numeric`` / ``value_string`` carries the payload —
    numeric for quantitative metrics (``land_size_hectares``), string for
    categorical ones (``crop_type``). ``claim_type`` is a *value*, not a schema
    key, so new metrics are new data rather than a migration.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    claim_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Deterministic-or-random unique id; the graph MERGE key.",
    )
    claim_type: str = Field(
        ..., min_length=1, description="Metric name, e.g. 'land_size_hectares' or 'yield_kg'."
    )
    source_category: SourceCategory = Field(
        ...,
        description="Required provenance category. No 'self_reported' member -- an "
        "unsourced figure is a PendingClaim, never a Claim.",
    )
    value_numeric: Optional[float] = Field(
        default=None, description="Quantitative value (None for categorical claims)."
    )
    value_string: Optional[str] = Field(
        default=None, description="Categorical value (None for numeric claims)."
    )
    unit: Optional[str] = Field(
        default=None, description="Unit of a numeric value, e.g. 'ha' or 'kg'."
    )
    source_id: Optional[str] = Field(
        default=None, description="Provenance of the observation, e.g. 'sentinel2:<scene>'."
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Source-reported confidence in [0, 1]."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the fact was observed/ingested (UTC).",
    )

    @model_validator(mode="after")
    def _require_a_value(self) -> "Claim":
        """A claim with neither a numeric nor a string value carries no fact."""
        if self.value_numeric is None and self.value_string is None:
            raise ValueError(
                f"Claim {self.claim_type!r} must set value_numeric or value_string."
            )
        return self


class PayloadBundle(BaseModel):
    """One Institution's batch of Claims about one Farmer — the ingestion unit.

    Enforces the authoritative-confidence rule: when the attesting institution is
    authoritative, every linked claim's confidence is pinned to
    :data:`AUTHORITATIVE_CONFIDENCE` (1.0), regardless of what the source sent.
    """

    institution: Institution
    farmer: Farmer
    claims: list[Claim] = Field(..., min_length=1, description="Claims by this institution.")

    @model_validator(mode="after")
    def _pin_authoritative_confidence(self) -> "PayloadBundle":
        """Ground-truth sources override per-claim confidence to 1.0."""
        if self.institution.is_authoritative:
            for claim in self.claims:
                claim.confidence = AUTHORITATIVE_CONFIDENCE
        return self
