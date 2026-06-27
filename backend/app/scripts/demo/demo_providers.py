"""Demo credit/identity providers — concrete integrations against the stub bureau.

These satisfy the verification seam's Protocols (``CreditBureauProvider`` /
``IdentityProvider``) by making *real HTTP calls* to :mod:`app.scripts.demo.stub_bureau`
and parsing the response into the seam's validation types. They register
themselves with the factory under the name ``"demo"`` on import, so selecting
``CREDIT_PROVIDER=demo`` / ``IDENTITY_PROVIDER=demo`` wires them in.

Importing this module is what makes the providers available — the factory ships
none itself. The runtime enrichment flow
(:mod:`app.scripts.demo.enrich_via_bridge`) imports it before resolving the
factory, so the demo provider is registered exactly when (and only when) the demo
asks for it. Production registers a real vendor client the same way.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.verification.providers.factory import (
    register_credit_provider,
    register_identity_provider,
)
from app.verification.providers.types import (
    CreditHistoryResult,
    IdentityVerificationResult,
)

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0)


@register_credit_provider("demo")
class DemoCreditProvider:
    """Calls the stub bureau's ``/credit`` endpoint."""

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def check_credit_history(self, *, country: str, identifier: str) -> CreditHistoryResult:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base_url}/credit",
                params={"country": country, "identifier": identifier},
                headers=self._headers,
            )
            resp.raise_for_status()
            # Pydantic validates the external payload at the boundary.
            return CreditHistoryResult.model_validate(resp.json())


@register_identity_provider("demo")
class DemoIdentityProvider:
    """Calls the stub bureau's ``/identity`` endpoint."""

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def verify_identity(
        self,
        *,
        country: str,
        claimed_name: str,
        identifier: str,
        identifier_type: Optional[str] = None,
    ) -> IdentityVerificationResult:
        params = {"country": country, "claimed_name": claimed_name, "identifier": identifier}
        if identifier_type:
            params["identifier_type"] = identifier_type
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self._base_url}/identity", params=params, headers=self._headers
            )
            resp.raise_for_status()
            return IdentityVerificationResult.model_validate(resp.json())
