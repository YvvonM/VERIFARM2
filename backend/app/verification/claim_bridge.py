"""Bridge: verification facts → canonical :class:`PayloadBundle` objects.

The verification modules each produce a *fact* in their own shape:

  * :mod:`app.verification.ndvi_crosscheck` returns a ``SatelliteAreaEstimate``
    (a cultivated-area proxy derived from Sentinel-2).
  * :mod:`app.verification.ocr_preprocessor` returns an ``OCRClaim`` extracted
    from a paper register photo.
  * the ingestion path validates a
    :class:`~app.models.claims.StandardFarmerClaim` from an off-taker / coop.

This module normalizes each into the *one* ingestion contract,
:class:`~app.models.reified.PayloadBundle`, so they all flow through the single
writer :class:`app.database.graph_ingestion.GraphIngestionService`. There is no
longer a separate row-dict format or a second write path.

The satellite is marked ``is_authoritative=True`` — making it the ground truth
that :func:`app.database.trust_graph.recalculate_reputation` scores every other
institution against, and (per the :class:`PayloadBundle` contract) pinning its
claims' confidence to 1.0.

Claim ids are deterministic (a hash of institution, farmer, metric and the
observation's natural key — scene id, document ref, or claim timestamp), so
re-ingesting the same observation is idempotent while a genuinely new
observation produces a new ``:Claim`` node and preserves temporal history.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

from app.models.reified import Claim, Farmer, Institution, PayloadBundle
from app.verification.providers.base import CreditBureauProvider, IdentityProvider
from app.verification.providers.factory import (
    get_credit_provider,
    get_identity_provider,
)
from app.verification.providers.types import (
    CreditHistoryResult,
    IdentityVerificationResult,
)

if TYPE_CHECKING:  # type-only imports — keep the bridge runtime-decoupled.
    # Avoid importing earthengine (`ee`) or the OCR/vision stack (`requests`)
    # just to use the bridge; these are only duck-typed annotations here.
    from app.verification.ndvi_crosscheck import SatelliteAreaEstimate
    from app.verification.ocr.models import OCRClaim

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Institutions. The satellite is the authoritative ground-truth observer that
# reputation scoring measures every other institution against.
# ---------------------------------------------------------------------------

SATELLITE_INSTITUTION = Institution(
    institution_id="SAT-SENTINEL2",
    name="Sentinel-2 NDVI Cross-Check",
    type="Satellite",
    is_authoritative=True,
    initial_trust_score=1.0,
)

# The OCR pipeline reads a cooperative's field register; the register is the
# attesting institution unless the caller names a more specific one.
DEFAULT_OCR_INSTITUTION_TYPE = "Cooperative"

# Institution.type (free-text label) -> required Claim.source_category.
# Unrecognized types default to "field_officer" (a human attestation that
# isn't one of the other structured categories).
_INSTITUTION_TYPE_TO_SOURCE_CATEGORY: dict[str, str] = {
    "Cooperative": "cooperative",
    "OffTaker": "off_taker",
    "Satellite": "remote_sensing",
    "GovernmentRegistry": "government",
    "CreditBureau": "government",
    "IdentityProvider": "government",
}


def _source_category_for(institution_type: Optional[str]) -> str:
    return _INSTITUTION_TYPE_TO_SOURCE_CATEGORY.get(institution_type or "", "field_officer")

# Maps an extracted OCR field name onto a canonical (claim_type, unit) pair.
# Anything not listed is passed through as a categorical claim under its own
# field name (value_numeric stays None).
_OCR_FIELD_MAP: dict[str, tuple[str, Optional[str]]] = {
    "land_size_ha": ("land_size_hectares", "ha"),
    "crop_type": ("crop_type", None),
}


def _claim_id(institution_id: str, farmer_id: str, claim_type: str, nonce: str) -> str:
    """Deterministic, idempotent claim id.

    ``nonce`` is the observation's natural key (scene id, document ref, claim
    timestamp). Same observation → same id (idempotent re-ingestion); a new
    observation → a new id (temporal history preserved).
    """
    raw = "|".join((institution_id, farmer_id, claim_type, nonce))
    return "claim_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _as_numeric(value: Any) -> Optional[float]:
    """Best-effort float coercion; returns ``None`` for categorical values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Satellite → authoritative bundle.
# ---------------------------------------------------------------------------


def satellite_estimate_to_bundle(
    farmer_id: str,
    estimate: "SatelliteAreaEstimate",
    claim_type: str = "land_size_hectares",
) -> PayloadBundle:
    """Convert a ``SatelliteAreaEstimate`` into an authoritative reified bundle.

    The detected vegetated area becomes a numeric ``land_size_hectares`` claim
    attested by the authoritative satellite institution, so reputation scoring
    can compare it against cooperative / off-taker attestations of the same
    metric for the same farmer. Per the bundle contract, the claim's confidence
    is pinned to 1.0 (the scene already cleared the cloud-cover gate upstream).
    """
    detected = float(estimate.detected_vegetated_area_ha)
    scene = str(estimate.scene_date)

    claim = Claim(
        claim_id=_claim_id(
            SATELLITE_INSTITUTION.institution_id, farmer_id, claim_type, scene
        ),
        claim_type=claim_type,
        value_numeric=detected,
        unit="ha",
        source_id=f"sentinel2:{scene}",
        source_category="remote_sensing",
        confidence=1.0,  # authoritative; PayloadBundle would pin this anyway.
    )
    return PayloadBundle(
        institution=SATELLITE_INSTITUTION,
        farmer=Farmer(farmer_id=farmer_id),
        claims=[claim],
    )


# ---------------------------------------------------------------------------
# OCR → non-authoritative bundle (one claim per extracted field).
# ---------------------------------------------------------------------------


def ocr_claim_to_bundle(
    farmer_id: str,
    claim: OCRClaim,
    institution_id: str,
    institution_name: str,
    institution_type: str = DEFAULT_OCR_INSTITUTION_TYPE,
) -> Optional[PayloadBundle]:
    """Convert an ``OCRClaim`` into a bundle with one claim per extracted field.

    The paper register is a (non-authoritative) institutional attestation: its
    claims are scored *against* ground truth, not treated as ground truth.
    Returns ``None`` when no structured field was extracted (nothing to ingest).
    """
    observed_at = claim.processed_at
    nonce = claim.document_ref
    source_category = _source_category_for(institution_type)
    claims: list[Claim] = []

    for field_name, field in claim.extracted_fields.items():
        # field is the dict form of ExtractedField: {value, confidence, raw_match}.
        value = field.get("value")
        confidence = field.get("confidence", claim.confidence)
        claim_type, unit = _OCR_FIELD_MAP.get(field_name, (field_name, None))
        numeric = _as_numeric(value)

        claims.append(
            Claim(
                claim_id=_claim_id(institution_id, farmer_id, claim_type, nonce),
                claim_type=claim_type,
                value_numeric=numeric,
                value_string=None if numeric is not None else str(value),
                unit=unit,
                source_id=f"ocr:{claim.document_ref}",
                source_category=source_category,
                confidence=confidence,
                timestamp=observed_at,
            )
        )

    if not claims:
        logger.warning(
            "OCRClaim for document %r yielded no structured fields; nothing to reify.",
            claim.document_ref,
        )
        return None

    return PayloadBundle(
        institution=Institution(
            institution_id=institution_id,
            name=institution_name,
            type=institution_type,
            is_authoritative=False,
            # The register was collected by this institution with the farmer's
            # consent, so it carries standing access — no fresh request needed.
            consent_at_source=True,
        ),
        farmer=Farmer(farmer_id=farmer_id),
        claims=claims,
    )


# ---------------------------------------------------------------------------
# StandardFarmerClaim → non-authoritative bundle.
#
# Reifies the off-taker/cooperative's numeric metrics as Claims attested by
# their Institution, so e.g. a cooperative's land_size can be compared
# against the satellite ground truth above via app.database.trust_graph.
# ---------------------------------------------------------------------------

# Numeric StandardFarmerClaim attributes worth cross-checking: attr → (type, unit).
_STANDARD_NUMERIC_METRICS: dict[str, tuple[str, str]] = {
    "land_size_hectares": ("land_size_hectares", "ha"),
    "production_volume_kg": ("production_volume_kg", "kg"),
}


def standard_claim_to_bundle(claim: Any) -> PayloadBundle:
    """Reify a :class:`StandardFarmerClaim`'s numeric metrics for cross-checking.

    Accepts the model (or any object exposing the same attributes). The verifier
    becomes a non-authoritative institution; ``confidence_score`` is carried onto
    each reified claim.
    """
    observed_at = claim.claim_timestamp
    nonce = observed_at.isoformat()  # one attestation per (verifier, farmer, metric, time).
    source_category = _source_category_for(claim.verifier_type)
    claims: list[Claim] = []

    for attr, (claim_type, unit) in _STANDARD_NUMERIC_METRICS.items():
        value = getattr(claim, attr)
        claims.append(
            Claim(
                claim_id=_claim_id(claim.verifier_id, claim.farmer_id, claim_type, nonce),
                claim_type=claim_type,
                value_numeric=float(value),
                unit=unit,
                source_id=claim.source_id,
                source_category=source_category,
                confidence=claim.confidence_score,
                timestamp=observed_at,
            )
        )

    return PayloadBundle(
        institution=Institution(
            institution_id=claim.verifier_id,
            name=claim.verifier_name,
            type=claim.verifier_type,
            is_authoritative=False,
            # The verifier collected this claim from the farmer with consent at
            # registration, so it holds standing access to the farmer's data.
            consent_at_source=True,
        ),
        farmer=Farmer(farmer_id=claim.farmer_id),
        claims=claims,
    )


# ===========================================================================
# Provider integration seam — external credit & identity → reified domain bundles.
#
# The two models below are the *reified domain bundles*: strongly-typed, farmer-
# linked, provenance-stamped representations of a verified fact. They sit between
# the raw provider contract (providers.types) and the canonical graph write
# contract (PayloadBundle): ``from_result`` translates a raw API result into the
# domain bundle, and ``to_payload_bundle`` projects it onto the reified graph
# shape so it flows through GraphIngestionService and becomes visible to the
# Copilot / Investigator / reputation queries.
# ===========================================================================

# A credit bureau / KYC provider is a non-authoritative source whose pull happens
# with the farmer's consent — so it carries standing access (no fresh request).
_CREDIT_INSTITUTION_TYPE = "CreditBureau"
_IDENTITY_INSTITUTION_TYPE = "IdentityProvider"


class VerifiedCreditClaim(BaseModel):
    """Reified domain bundle for a verified credit report."""

    farmer_id: str
    provider: str
    credit_score: int
    has_default_flag: bool
    repayment_history_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    verified_at: datetime

    @classmethod
    def from_result(cls, farmer_id: str, result: CreditHistoryResult) -> "VerifiedCreditClaim":
        return cls(
            farmer_id=farmer_id,
            provider=result.provider,
            credit_score=result.credit_score,
            has_default_flag=result.has_default_flag,
            repayment_history_summary=result.repayment_history_summary,
            confidence=result.confidence,
            verified_at=result.checked_at,
        )

    def to_payload_bundle(self) -> PayloadBundle:
        """Project onto the canonical reified graph contract.

        ``credit_history`` carries the bureau score as ``value_numeric`` (the
        claim_type the portfolio/macro queries already look for); the default
        flag is a separate categorical claim.
        """
        nonce = self.verified_at.isoformat()
        claims = [
            Claim(
                claim_id=_claim_id(self.provider, self.farmer_id, "credit_history", nonce),
                claim_type="credit_history",
                value_numeric=float(self.credit_score),
                source_id=self.provider,
                source_category="government",
                confidence=self.confidence,
                timestamp=self.verified_at,
            ),
            Claim(
                claim_id=_claim_id(self.provider, self.farmer_id, "credit_default_flag", nonce),
                claim_type="credit_default_flag",
                value_string=str(bool(self.has_default_flag)).lower(),
                source_id=self.provider,
                source_category="government",
                confidence=self.confidence,
                timestamp=self.verified_at,
            ),
        ]
        return PayloadBundle(
            institution=Institution(
                institution_id=self.provider,
                name=self.provider,
                type=_CREDIT_INSTITUTION_TYPE,
                is_authoritative=False,
                consent_at_source=True,
            ),
            farmer=Farmer(farmer_id=self.farmer_id),
            claims=claims,
        )


class VerifiedIdentityClaim(BaseModel):
    """Reified domain bundle for a verified identity (only built on a match)."""

    farmer_id: str
    provider: str
    verified_name: Optional[str]
    identifier_type: str
    confidence: float = Field(ge=0.0, le=1.0)
    verified_at: datetime

    @classmethod
    def from_result(
        cls, farmer_id: str, result: IdentityVerificationResult
    ) -> Optional["VerifiedIdentityClaim"]:
        """Build the bundle, or ``None`` on a non-match (nothing to attest)."""
        if not result.match:
            return None
        return cls(
            farmer_id=farmer_id,
            provider=result.provider,
            verified_name=result.verified_name,
            identifier_type=result.submitted_identifier_type,
            confidence=result.confidence,
            verified_at=result.checked_at,
        )

    def to_payload_bundle(self) -> PayloadBundle:
        """Project onto the canonical reified graph contract."""
        nonce = self.verified_at.isoformat()
        claim = Claim(
            claim_id=_claim_id(self.provider, self.farmer_id, "identity_verified", nonce),
            claim_type="identity_verified",
            value_string=self.verified_name or "true",
            source_id=f"{self.provider}:{self.identifier_type}",
            source_category="government",
            confidence=self.confidence,
            timestamp=self.verified_at,
        )
        return PayloadBundle(
            institution=Institution(
                institution_id=self.provider,
                name=self.provider,
                type=_IDENTITY_INSTITUTION_TYPE,
                is_authoritative=False,
                consent_at_source=True,
            ),
            farmer=Farmer(farmer_id=self.farmer_id),
            claims=[claim],
        )


class ClaimBridge:
    """Orchestrates external verification → reified domain bundles.

    Providers are injected for testability; when omitted they are resolved from
    the environment-driven factory, which raises
    :class:`~app.verification.providers.factory.NotConfigured` if no real provider
    is configured (the system never falls back to fabricated data). Provider calls
    are ``async`` so a slow vendor round-trip never blocks the event loop.
    """

    def __init__(
        self,
        credit_provider: Optional[CreditBureauProvider] = None,
        identity_provider: Optional[IdentityProvider] = None,
    ) -> None:
        self._credit = credit_provider
        self._identity = identity_provider

    def _credit_provider(self) -> CreditBureauProvider:
        if self._credit is None:
            self._credit = get_credit_provider()  # raises NotConfigured
        return self._credit

    def _identity_provider(self) -> IdentityProvider:
        if self._identity is None:
            self._identity = get_identity_provider()  # raises NotConfigured
        return self._identity

    async def build_credit_claim(
        self, *, farmer_id: str, country: str, identifier: str
    ) -> VerifiedCreditClaim:
        """Fetch + reify a farmer's credit history into a domain bundle."""
        result = await self._credit_provider().check_credit_history(
            country=country, identifier=identifier
        )
        logger.info("Built verified credit claim for %s via %s.", farmer_id, result.provider)
        return VerifiedCreditClaim.from_result(farmer_id, result)

    async def build_identity_claim(
        self,
        *,
        farmer_id: str,
        country: str,
        claimed_name: str,
        identifier: str,
        identifier_type: Optional[str] = None,
    ) -> Optional[VerifiedIdentityClaim]:
        """Fetch + reify a farmer's identity verification; ``None`` on non-match."""
        result = await self._identity_provider().verify_identity(
            country=country,
            claimed_name=claimed_name,
            identifier=identifier,
            identifier_type=identifier_type,
        )
        return VerifiedIdentityClaim.from_result(farmer_id, result)

    @staticmethod
    def persist(bundle: PayloadBundle, driver=None) -> int:
        """Write a reified bundle to Neo4j via the single canonical write surface."""
        from app.database.graph_ingestion import GraphIngestionService

        svc = GraphIngestionService(driver=driver)
        try:
            svc.ensure_constraints()
            return svc.ingest_payload_bundles([bundle])
        finally:
            svc.close()
