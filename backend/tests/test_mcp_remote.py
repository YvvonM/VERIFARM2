"""Tests for the remote MCP auth gate + tenant isolation (no MCP SDK needed)."""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:  # pragma: no cover
    import pydantic  # noqa: F401
except ModuleNotFoundError:
    pyd = types.ModuleType("pydantic")

    def _Field(default=..., **kw):
        if "default_factory" in kw:
            return kw["default_factory"]()
        return None if default is ... else default

    class _BaseModel:
        def __init__(self, **kw):
            for f in type(self).__annotations__:        # apply declared defaults
                if f not in kw and hasattr(type(self), f):
                    kw.setdefault(f, getattr(type(self), f))
            self.__dict__.update(kw)

    pyd.BaseModel = _BaseModel
    pyd.Field = _Field
    sys.modules["pydantic"] = pyd

auth = importlib.import_module("app.mcp.auth")
tenancy = importlib.import_module("app.mcp.tenancy")
SessionContext = auth.SessionContext


def _dev_token(org_id, scopes):
    raw = base64.urlsafe_b64encode(json.dumps({"org_id": org_id, "scopes": scopes}).encode())
    return raw.decode().rstrip("=")


# --- auth gate -------------------------------------------------------------

def test_resolve_bearer_dev_mode():
    os.environ["MCP_AUTH_DEV"] = "true"
    os.environ.pop("MCP_JWT_SECRET", None)
    try:
        s = auth.resolve_bearer(f"Bearer {_dev_token('ORG-A', ['claims:read'])}")
        assert s.org_id == "ORG-A" and "claims:read" in s.scopes
    finally:
        os.environ.pop("MCP_AUTH_DEV", None)


def test_resolve_bearer_rejects_missing_and_bad():
    for bad in ("", "Token xyz", "Bearer"):
        try:
            auth.resolve_bearer(bad)
        except auth.AuthError:
            continue
        raise AssertionError(f"should reject {bad!r}")


def test_session_contextvar_roundtrip():
    try:
        auth.current_session()
    except auth.AuthError:
        pass
    else:
        raise AssertionError("no session should raise")
    tok = auth.set_session(SessionContext(org_id="ORG-A", scopes=[]))
    try:
        assert auth.current_session().org_id == "ORG-A"
    finally:
        auth.reset_session(tok)


# --- tenant isolation ------------------------------------------------------

def test_claims_access_same_org_ok_cross_denied():
    s = SessionContext(org_id="ORG-A", scopes=["claims:read"])
    assert tenancy.check_claims_access(s, "ORG-A") is None
    denied = tenancy.check_claims_access(s, "ORG-B")
    assert denied is not None and denied.error == "access_denied"
    assert denied.requested_org == "ORG-B" and denied.authorized_org == "ORG-A"


def test_claims_access_requires_scope():
    s = SessionContext(org_id="ORG-A", scopes=[])
    denied = tenancy.check_claims_access(s, "ORG-A")
    assert denied is not None and denied.error == "insufficient_scope"


def test_authorize_resource_rejects_cross_tenant():
    s = SessionContext(org_id="ORG-A", scopes=["org:read"])
    tenancy.authorize_resource(s, "ORG-A")  # ok, no raise
    try:
        tenancy.authorize_resource(s, "ORG-B")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-tenant resource must raise")


# --- ASGI auth gate (the actual 401 enforcement, no MCP SDK needed) ---------

def _run_gate(authorization, downstream_marker):
    """Drive AuthContextMiddleware once and capture the ASGI response messages."""
    import asyncio

    sent: list = []
    called = {"downstream": False, "session_org": None}

    async def downstream(scope, receive, send):
        called["downstream"] = True
        called["session_org"] = auth.current_session().org_id  # session must be set here
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": downstream_marker})

    mw = auth.AuthContextMiddleware(downstream)
    headers = [(b"authorization", authorization.encode())] if authorization else []
    scope = {"type": "http", "headers": headers}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    asyncio.run(mw(scope, receive, send))
    return sent, called


def test_auth_gate_401_without_token():
    os.environ["MCP_AUTH_DEV"] = "true"
    os.environ.pop("MCP_JWT_SECRET", None)
    try:
        sent, called = _run_gate("", b"DATA")
        assert sent[0]["status"] == 401
        assert not called["downstream"], "downstream must not run on 401"
        # The session ContextVar must be clean again after the request.
        try:
            auth.current_session()
        except auth.AuthError:
            pass
        else:
            raise AssertionError("session must be reset after request")
    finally:
        os.environ.pop("MCP_AUTH_DEV", None)


def test_auth_gate_passes_authenticated_request():
    os.environ["MCP_AUTH_DEV"] = "true"
    os.environ.pop("MCP_JWT_SECRET", None)
    try:
        token = _dev_token("ORG-A", ["claims:read"])
        sent, called = _run_gate(f"Bearer {token}", b"DATA")
        assert sent[0]["status"] == 200 and called["downstream"]
        assert called["session_org"] == "ORG-A"
    finally:
        os.environ.pop("MCP_AUTH_DEV", None)


def test_auth_gate_rate_limits_per_tenant():
    """Once a tenant exceeds its window, the gate returns 429 (not data)."""
    os.environ["MCP_AUTH_DEV"] = "true"
    os.environ.pop("MCP_JWT_SECRET", None)
    from app.ratelimit import RateLimiter

    original = auth._mcp_limiter
    auth._mcp_limiter = RateLimiter(limit=2, window=60)
    try:
        token = _dev_token("ORG-A", ["claims:read"])
        statuses = [_run_gate(f"Bearer {token}", b"DATA")[0][0]["status"] for _ in range(3)]
        assert statuses[:2] == [200, 200], statuses
        assert statuses[2] == 429, statuses
        # A different tenant has its own bucket and is unaffected.
        other = _dev_token("ORG-B", ["claims:read"])
        assert _run_gate(f"Bearer {other}", b"DATA")[0][0]["status"] == 200
    finally:
        auth._mcp_limiter = original
        os.environ.pop("MCP_AUTH_DEV", None)


def test_auth_gate_passes_through_non_http_scope():
    import asyncio

    seen = {"called": False}

    async def downstream(scope, receive, send):
        seen["called"] = True

    mw = auth.AuthContextMiddleware(downstream)
    asyncio.run(mw({"type": "lifespan"}, None, None))
    assert seen["called"], "non-http scopes must bypass the auth gate"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {fn.__name__}: {exc}")
            failures.append(fn.__name__)
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILURE(S): {failures}"))
    sys.exit(1 if failures else 0)
