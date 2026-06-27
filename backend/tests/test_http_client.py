"""Tests for the resilient async HTTP client + FMIS mapper.

Uses httpx.MockTransport to drive retries/backoff/429/re-auth deterministically
(no network, no sleeps of consequence — backoff_base=0). Skipped where httpx /
pydantic aren't installed.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("pydantic")

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.clients.http_client import APIClientError, AsyncAPIClient  # noqa: E402
from app.clients.fmis import FmisFarmer, fmis_farmer_to_bundle  # noqa: E402


def _client(handler, **kw):
    c = AsyncAPIClient(base_url="http://test", backoff_base=0.0, **kw)
    c._client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
    return c


def test_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})

    c = _client(handler, max_retries=3)
    assert asyncio.run(c.get_json("/x")) == {"ok": True}
    assert calls["n"] == 3
    asyncio.run(c.aclose())


def test_honours_429_retry_after():
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": 1})

    c = _client(handler, max_retries=3)
    assert asyncio.run(c.get_json("/x")) == {"ok": 1}
    assert calls["n"] == 2
    asyncio.run(c.aclose())


def test_reauth_once_on_401():
    class FakeAuth:
        def __init__(self):
            self.invalidated = 0

        async def headers(self, _http):
            return {"Authorization": "Bearer t"}

        async def invalidate(self):
            self.invalidated += 1

    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return httpx.Response(401) if calls["n"] == 1 else httpx.Response(200, json={"ok": 1})

    auth = FakeAuth()
    c = _client(handler, max_retries=3)
    c._auth = auth
    assert asyncio.run(c.get_json("/x")) == {"ok": 1}
    assert auth.invalidated == 1 and calls["n"] == 2
    asyncio.run(c.aclose())


def test_transport_errors_exhaust_to_api_error():
    def handler(_req):
        raise httpx.ConnectError("boom")

    c = _client(handler, max_retries=2)
    try:
        asyncio.run(c.get_json("/x"))
    except APIClientError:
        pass
    else:
        raise AssertionError("expected APIClientError after exhausting retries")
    asyncio.run(c.aclose())


def test_graphql_raises_on_errors():
    def handler(_req):
        return httpx.Response(200, json={"errors": [{"message": "bad"}]})

    c = _client(handler)
    try:
        asyncio.run(c.graphql("query{x}"))
    except APIClientError:
        pass
    else:
        raise AssertionError("GraphQL errors should raise")
    asyncio.run(c.aclose())


def test_fmis_strict_mapping_drops_extras_and_builds_bundle():
    f = FmisFarmer.model_validate(
        {"id": "F-1", "landSizeHectares": 2.5, "cropType": "maize",
         "productionVolumeKg": 500, "junkField": "ignored"}
    )
    assert f.farmer_id == "F-1" and f.land_size_hectares == 2.5 and f.crop_type == "maize"
    assert not hasattr(f, "junkField")

    bundle = fmis_farmer_to_bundle(f, "ORG-FMIS", "Acme FMIS")
    assert {c.claim_type for c in bundle.claims} == {
        "land_size_hectares", "production_volume_kg", "crop_type"
    }
    assert bundle.institution.type == "FMIS" and bundle.institution.is_authoritative is False
