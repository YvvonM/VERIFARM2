"""Base async HTTP client for polling ERPs / FMIS and querying registries.

Built on ``httpx.AsyncClient`` with:
  * **automatic retries** with exponential backoff + jitter on transport errors
    and 5xx responses;
  * **rate-limit handling** — on 429 it honours the ``Retry-After`` header when
    present, else backs off;
  * **auth flows** — a pluggable :class:`AuthStrategy` (bearer / OAuth2 client
    credentials); on a 401 it invalidates and re-authenticates once.
  * GraphQL + REST helpers (``get_json`` / ``post_json`` / ``graphql``).

``httpx`` is imported lazily so the backend boots without it; it is only needed
when a client is actually constructed.
"""

from __future__ import annotations

import asyncio
import logging
import random
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Optional

from app.clients.auth import AuthStrategy

logger = logging.getLogger(__name__)


class APIClientError(RuntimeError):
    """Raised when a request ultimately fails after retries."""


def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date) to seconds."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None


class AsyncAPIClient:
    """Resilient async HTTP client. Use as an async context manager."""

    def __init__(
        self,
        base_url: str = "",
        auth: Optional[AuthStrategy] = None,
        *,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        max_backoff: float = 30.0,
        timeout: float = 30.0,
    ) -> None:
        import httpx

        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._httpx = httpx
        self._auth = auth
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._max_backoff = max_backoff

    async def __aenter__(self) -> "AsyncAPIClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _backoff(self, attempt: int) -> float:
        return min(self._max_backoff, self._backoff_base * (2 ** attempt)) + random.uniform(0, 0.25)

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
    ):
        """Send a request with retries/backoff/429-handling/re-auth. Returns the response."""
        reauthed = False
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            req_headers = dict(headers or {})
            if self._auth is not None:
                req_headers.update(await self._auth.headers(self._client))

            try:
                resp = await self._client.request(
                    method, url, json=json, params=params, data=data, headers=req_headers
                )
            except self._httpx.TransportError as exc:  # connect/read/timeout
                last_exc = exc
                if attempt >= self._max_retries:
                    break
                wait = self._backoff(attempt)
                logger.warning("Transport error (%s); retry %d in %.2fs.", exc, attempt + 1, wait)
                await asyncio.sleep(wait)
                continue

            # 401 → invalidate creds and re-auth once.
            if resp.status_code == 401 and self._auth is not None and not reauthed:
                reauthed = True
                await self._auth.invalidate()
                continue

            # 429 → honour Retry-After, else back off.
            if resp.status_code == 429 and attempt < self._max_retries:
                wait = _retry_after_seconds(resp.headers.get("Retry-After")) or self._backoff(attempt)
                logger.warning("Rate limited (429); waiting %.2fs before retry %d.", wait, attempt + 1)
                await asyncio.sleep(wait)
                continue

            # 5xx → retry with backoff.
            if resp.status_code >= 500 and attempt < self._max_retries:
                wait = self._backoff(attempt)
                logger.warning("Server error %d; retry %d in %.2fs.", resp.status_code, attempt + 1, wait)
                await asyncio.sleep(wait)
                continue

            return resp

        raise APIClientError(
            f"{method} {url} failed after {self._max_retries + 1} attempt(s): {last_exc}"
        )

    async def get_json(self, url: str, *, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
        resp = await self.request("GET", url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def post_json(self, url: str, *, json: Any = None, headers: Optional[dict] = None) -> Any:
        resp = await self.request("POST", url, json=json, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def graphql(self, query: str, variables: Optional[dict] = None, *, url: str = "/graphql") -> dict:
        """Execute a GraphQL query; raise on transport or GraphQL ``errors``."""
        body = await self.post_json(url, json={"query": query, "variables": variables or {}})
        if body.get("errors"):
            raise APIClientError(f"GraphQL errors: {body['errors']}")
        return body.get("data", {})
