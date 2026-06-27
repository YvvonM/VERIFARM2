"""Provider interfaces (structural typing via ``typing.Protocol``).

A concrete integration (a real bureau / KYC vendor SDK or HTTP client) satisfies
these contracts simply by implementing the methods — no base class to inherit,
no import coupling from the vendor code back into our core. That is the whole
point of the *seam*: the domain layer depends on these abstractions, never on a
specific vendor.

Methods are ``async`` because real integrations are network I/O bound; defining
the contract as async keeps a slow vendor call off the event loop in the API.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.verification.providers.types import (
    CreditHistoryResult,
    IdentityVerificationResult,
)


@runtime_checkable
class CreditBureauProvider(Protocol):
    """Fetches a farmer's credit report from a licensed bureau."""

    async def check_credit_history(
        self, *, country: str, identifier: str
    ) -> CreditHistoryResult:
        """Return a validated credit report for ``identifier`` (e.g. phone/BVN)."""
        ...


@runtime_checkable
class IdentityProvider(Protocol):
    """Performs a KYC identity verification via an accredited intermediary."""

    async def verify_identity(
        self,
        *,
        country: str,
        claimed_name: str,
        identifier: str,
        identifier_type: Optional[str] = None,
    ) -> IdentityVerificationResult:
        """Return a validated identity-verification result for the submitted record."""
        ...
