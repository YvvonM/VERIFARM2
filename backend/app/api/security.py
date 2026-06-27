"""Access control + rate limiting for the HTTP API.

Two FastAPI dependencies protect the API from unauthenticated use and heavy
downstream load. They are intentionally *opt-in*: when no key is configured the
gate is open (local/dev), so wiring them onto a router is always safe by default.

  * :func:`require_api_key` — when an API key is configured (``VERIFARMS_API_KEY``,
    or the legacy ``EXPORT_API_KEY``), requests must present a matching key via the
    ``X-API-Key`` header **or** the ``api_key`` query parameter (401 otherwise).
    The query-param path exists for the SSE endpoint: a browser ``EventSource``
    cannot set custom headers, so it authenticates via the URL.
  * :func:`rate_limit` — a fixed-window limiter keyed by API key (or client IP),
    ``EXPORT_RATE_LIMIT_PER_MIN`` requests/min (429 on exceed; 0 disables).

The limiter is in-process (fine for a single instance / demo). For a multi-replica
deployment, back it with Redis so the window is shared — the dependency shape
stays the same.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, Query, Request

# RateLimiter lives in a FastAPI-free module so the MCP gateway can share it;
# re-exported here so existing `from app.api.security import RateLimiter` works.
from app.ratelimit import RateLimiter

__all__ = ["RateLimiter", "require_api_key", "rate_limit", "export_limiter"]


def _default_limit() -> int:
    try:
        return int(os.environ.get("EXPORT_RATE_LIMIT_PER_MIN", "120"))
    except ValueError:
        return 120


# Module-level limiter shared across export requests.
export_limiter = RateLimiter(_default_limit())


def _expected_key() -> Optional[str]:
    """The configured API key, preferring ``VERIFARMS_API_KEY`` over legacy ``EXPORT_API_KEY``."""
    return os.environ.get("VERIFARMS_API_KEY") or os.environ.get("EXPORT_API_KEY")


def require_api_key(
    x_api_key: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> None:
    """Enforce the API key (header or ``?api_key=``) only when one is configured."""
    expected = _expected_key()
    if expected and x_api_key != expected and api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def rate_limit(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None),
) -> None:
    """Fixed-window rate limit keyed by API key, falling back to client IP."""
    key = x_api_key or api_key or (request.client.host if request.client else "anonymous")
    if not export_limiter.allow(key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Slow down.",
            headers={"Retry-After": str(int(export_limiter.window))},
        )
