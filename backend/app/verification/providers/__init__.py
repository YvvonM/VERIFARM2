"""External provider integration seam (KYC identity + credit bureau).

Public surface:

    types     — raw Pydantic API contracts (CreditHistoryResult, IdentityVerificationResult)
    base      — async Protocol interfaces (CreditBureauProvider, IdentityProvider)
    factory   — env-driven instantiation; raises NotConfigured (never mocks)

The reification of these into graph claims lives in app.verification.claim_bridge.
"""

from app.verification.providers.base import CreditBureauProvider, IdentityProvider
from app.verification.providers.factory import (
    NotConfigured,
    get_credit_provider,
    get_identity_provider,
    register_credit_provider,
    register_identity_provider,
)
from app.verification.providers.types import (
    CreditHistoryResult,
    IdentityVerificationResult,
)

__all__ = [
    "CreditHistoryResult",
    "IdentityVerificationResult",
    "CreditBureauProvider",
    "IdentityProvider",
    "NotConfigured",
    "get_credit_provider",
    "get_identity_provider",
    "register_credit_provider",
    "register_identity_provider",
]
