"""Multi-tenant auth gate for the remote MCP server.

The flow: a network request hits the ASGI :class:`AuthContextMiddleware`, which
resolves the ``Authorization: Bearer <token>`` header into a :class:`SessionContext`
(``org_id`` + scopes) and stores it in a **request-scoped ContextVar**. The MCP
handler then runs in that same async context, so tools/resources read the tenant
identity via :func:`current_session` — no global state, and the session is reset
when the request completes.

Token resolution is pluggable: a signed JWT (``MCP_JWT_SECRET``, HS256) in
production, or an explicit, clearly-labelled unsigned dev token
(``MCP_AUTH_DEV=true``) for local testing. Missing/invalid ⇒ 401.
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar, Token
from typing import Optional

from pydantic import BaseModel, Field


class SessionContext(BaseModel):
    org_id: str
    scopes: list[str] = Field(default_factory=list)


class AuthError(RuntimeError):
    """Authentication failed (→ 401)."""


_session: ContextVar[Optional[SessionContext]] = ContextVar("verifarms_mcp_session", default=None)


def set_session(session: SessionContext) -> Token:
    return _session.set(session)


def reset_session(token: Token) -> None:
    _session.reset(token)


def current_session() -> SessionContext:
    """Return the authenticated session for the current request (raises if absent)."""
    session = _session.get()
    if session is None:
        raise AuthError("No authenticated session in context.")
    return session


def resolve_bearer(authorization: str) -> SessionContext:
    """Resolve an ``Authorization`` header value into a SessionContext."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing or malformed Authorization: Bearer header.")
    token = authorization.split(" ", 1)[1].strip()

    secret = os.environ.get("MCP_JWT_SECRET")
    if secret:
        try:
            import jwt  # PyJWT
            claims = jwt.decode(token, secret, algorithms=["HS256"])
        except Exception as exc:  # noqa: BLE001 - any decode/verify failure is a 401.
            raise AuthError(f"Invalid JWT: {exc}")
        org_id = claims.get("org_id")
        if not org_id:
            raise AuthError("Token is missing the 'org_id' claim.")
        return SessionContext(org_id=org_id, scopes=claims.get("scopes", []))

    if os.environ.get("MCP_AUTH_DEV", "false").lower() == "true":
        # DEV ONLY — unsigned base64url JSON: {"org_id": "...", "scopes": [...]}
        import base64
        try:
            padded = token + "=" * (-len(token) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded))
        except Exception as exc:  # noqa: BLE001
            raise AuthError(f"Invalid dev token: {exc}")
        if not data.get("org_id"):
            raise AuthError("Dev token is missing 'org_id'.")
        return SessionContext(org_id=data["org_id"], scopes=data.get("scopes", []))

    raise AuthError("Server auth is not configured (set MCP_JWT_SECRET).")


def _mcp_rate_limit() -> int:
    try:
        return int(os.environ.get("MCP_RATE_LIMIT_PER_MIN", "60"))
    except ValueError:
        return 60


# Per-tenant fixed-window limiter (keyed by org_id) shared across MCP requests.
# Same thread-safe limiter as the REST API, from a FastAPI-free module so the
# gateway stays importable standalone. 0/negative disables it.
from app.ratelimit import RateLimiter  # noqa: E402

_mcp_limiter = RateLimiter(_mcp_rate_limit())


class AuthContextMiddleware:
    """Pure-ASGI middleware: authenticate, rate-limit per tenant, inject session."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        try:
            session = resolve_bearer(headers.get("authorization", ""))
        except AuthError as exc:
            await self._unauthorized(send, str(exc))
            return
        # Throttle per tenant so one org's token can't exhaust the read backend.
        if not _mcp_limiter.allow(session.org_id):
            await self._rate_limited(send)
            return
        token = set_session(session)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_session(token)

    @staticmethod
    async def _unauthorized(send, detail: str) -> None:
        body = json.dumps({"error": "unauthorized", "detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _rate_limited(send) -> None:
        body = json.dumps({"error": "rate_limited", "detail": "Tenant rate limit exceeded."}).encode()
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [(b"content-type", b"application/json"), (b"retry-after", b"60")],
        })
        await send({"type": "http.response.body", "body": body})
