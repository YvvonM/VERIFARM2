"""
Synthetic identity and credit-bureau provider fixtures for the data generator.

These live in :mod:`app.data_generation` — **not** :mod:`app.verification` — on
purpose. They fabricate plausible identity/credit responses to populate a
synthetic dataset; fabrication is the data generator's legitimate job. The real
runtime verification path is the provider seam in
:mod:`app.verification.providers` / :class:`app.verification.claim_bridge.ClaimBridge`,
which ships no mock and refuses to invent data (raises ``NotConfigured``). Keep
these two worlds separate: nothing under ``app.verification`` may import this.

Public interface:
    verify_identity(country, claimed_name, identifier, identifier_type=None)
        -> IdentityVerificationResult
    check_credit_history(country, identifier)
        -> CreditHistoryResult

See response_types.py for the returned dataclass shapes, identity_mock.py
and credit_mock.py for the per-claim-type simulation logic.
"""

from app.data_generation.synthetic_providers.credit_mock import check_credit_history
from app.data_generation.synthetic_providers.identity_mock import verify_identity
from app.data_generation.synthetic_providers.response_types import (
    CreditHistoryResult,
    IdentityVerificationResult,
)

__all__ = [
    "verify_identity",
    "check_credit_history",
    "IdentityVerificationResult",
    "CreditHistoryResult",
]