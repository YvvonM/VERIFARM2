"""Authentication strategies for the async API client.

A strategy supplies the auth headers for each request and can invalidate cached
credentials on a 401. Two are provided:

  * :class:`BearerAuth` — a static bearer token.
  * :class:`OAuth2ClientCredentials` — the OAuth2 client-credentials grant: fetch
    an access token from the token endpoint, cache it until shortly before expiry,
    and transparently refresh (also on a 401).

``httpx`` is imported lazily by the client, not here, so this module stays import-
light.
"""

from __future__ import annotations

import time
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class AuthStrategy(Protocol):
    async def headers(self, http) -> dict[str, str]: ...
    async def invalidate(self) -> None: ...


class BearerAuth:
    """Static bearer token."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def headers(self, http) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def invalidate(self) -> None:
        pass  # static token — nothing to refresh


class OAuth2ClientCredentials:
    """OAuth2 client-credentials grant with token caching + refresh."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: Optional[str] = None,
        leeway_seconds: int = 30,
    ) -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.leeway = leeway_seconds
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    async def headers(self, http) -> dict[str, str]:
        if not self._token or time.time() >= self._expires_at - self.leeway:
            await self._fetch(http)
        return {"Authorization": f"Bearer {self._token}"}

    async def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0

    async def _fetch(self, http) -> None:
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if self.scope:
            data["scope"] = self.scope
        resp = await http.post(self.token_url, data=data)
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + float(body.get("expires_in", 3600))
