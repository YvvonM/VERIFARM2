"""
Mock identity verification provider.

Simulates calling an accredited KYC intermediary (Smile Identity,
Youverify, Prembly/QoreID, or similar) that itself holds NIBSS (BVN) /
NIMC (NIN) accreditation in Nigeria, or the equivalent national ID system
check in Kenya. No real lookup is performed -- this returns a
deterministic, plausible-looking response shaped like a real provider's
API response, for demo/testing purposes only.

USAGE:
    result = verify_identity(
        country="Nigeria",
        claimed_name="Chinedu Okafor",
        identifier="22134455667",   # fake BVN-shaped string
        identifier_type="BVN",
    )
"""

import hashlib
from datetime import datetime, timezone

from app.data_generation.synthetic_providers.response_types import IdentityVerificationResult

# Per-country provider label. Naming the real institution being simulated
# (with _mock appended) is what keeps this self-documenting in the graph --
# see Claim.method usage in the data generator.
_PROVIDER_LABEL_BY_COUNTRY: dict[str, str] = {
    "Nigeria": "NIBSS_NIMC_mock_via_accredited_provider",
    "Kenya": "national_ID_mock_via_accredited_provider",
}

_IDENTIFIER_TYPE_BY_COUNTRY: dict[str, str] = {
    "Nigeria": "BVN",
    "Kenya": "national_id",
}


def _deterministic_confidence(identifier: str) -> float:
    """
    Derives a stable, plausible confidence score from the identifier so
    repeated calls with the same fake identifier return the same result
    (useful for reproducible test fixtures) without hardcoding every value.
    Biased toward the high end, per the proposal's "Strong" rating for
    identity checks -- real NIBSS/NIMC-backed verification is reliable when
    it happens at all; the realistic failure mode is "no match," not "low
    confidence match."
    """
    digest = hashlib.sha256(identifier.encode()).hexdigest()
    fractional = int(digest[:4], 16) / 0xFFFF  # 0.0-1.0
    return round(0.85 + fractional * 0.14, 2)  # lands in [0.85, 0.99]


def verify_identity(
    country: str,
    claimed_name: str,
    identifier: str,
    identifier_type: str | None = None,
) -> IdentityVerificationResult:
    """
    Simulate an identity-verification call. Always returns match=True with
    the claimed name echoed back as verified -- this mock is for populating
    plausible demo data, not for testing mismatch/fraud-detection handling.
    If you need mismatch cases for testing, construct an
    IdentityVerificationResult directly with match=False instead of calling
    this function.
    """
    provider = _PROVIDER_LABEL_BY_COUNTRY.get(country, "national_ID_mock_via_accredited_provider")
    resolved_identifier_type = identifier_type or _IDENTIFIER_TYPE_BY_COUNTRY.get(country, "national_id")

    return IdentityVerificationResult(
        provider=provider,
        match=True,
        verified_name=claimed_name,
        submitted_identifier_type=resolved_identifier_type,
        confidence=_deterministic_confidence(identifier),
        checked_at=datetime.now(timezone.utc),
    )