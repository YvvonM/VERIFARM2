"""Tests for the Sprint 3 egress layer: rate limiting, API-key auth, events.

Pure logic, runnable without a server. ``fastapi`` and ``pydantic`` are stubbed
only when not installed.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:  # pragma: no cover
    import fastapi  # noqa: F401
except ModuleNotFoundError:
    fa = types.ModuleType("fastapi")

    def _Header(default=None, **_k):
        return default

    class _HTTPException(Exception):
        def __init__(self, status_code=None, detail=None, headers=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers

    class _Request:  # minimal stand-in
        pass

    fa.Header = _Header
    fa.Query = _Header  # same stub: returns the supplied default
    fa.HTTPException = _HTTPException
    fa.Request = _Request
    sys.modules["fastapi"] = fa

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
            self.__dict__.update(kw)

        def model_dump(self, **_k):
            return dict(self.__dict__)

    pyd.BaseModel = _BaseModel
    pyd.Field = _Field
    sys.modules["pydantic"] = pyd

security = importlib.import_module("app.api.security")
publishers = importlib.import_module("app.events.publishers")
dispatch = importlib.import_module("app.events.dispatch")
from fastapi import HTTPException  # noqa: E402  (real or stubbed)
from types import SimpleNamespace as NS  # noqa: E402


# --- rate limiting ---------------------------------------------------------

def test_rate_limiter_allows_up_to_limit_then_blocks():
    rl = security.RateLimiter(limit=3, window=60)
    assert [rl.allow("k") for _ in range(3)] == [True, True, True]
    assert rl.allow("k") is False                 # 4th over the limit
    assert rl.allow("other-key") is True          # independent per key


def test_rate_limiter_zero_disables():
    rl = security.RateLimiter(limit=0)
    assert all(rl.allow("k") for _ in range(100))


# --- api key ---------------------------------------------------------------

def test_api_key_open_when_unset():
    os.environ.pop("EXPORT_API_KEY", None)
    os.environ.pop("VERIFARMS_API_KEY", None)
    security.require_api_key(None, None)  # no exception


def test_api_key_enforced_when_set():
    os.environ.pop("VERIFARMS_API_KEY", None)
    os.environ["EXPORT_API_KEY"] = "s3cret"  # legacy var still works
    try:
        security.require_api_key("s3cret", None)  # correct header → ok
        try:
            security.require_api_key("wrong", None)
        except HTTPException as exc:
            assert getattr(exc, "status_code", 401) == 401
        else:
            raise AssertionError("wrong key should raise 401")
    finally:
        os.environ.pop("EXPORT_API_KEY", None)


def test_api_key_query_param_path():
    """EventSource can't set headers, so the key may arrive as ?api_key=."""
    os.environ.pop("EXPORT_API_KEY", None)
    os.environ["VERIFARMS_API_KEY"] = "s3cret"
    try:
        security.require_api_key(None, "s3cret")  # correct query param → ok
        try:
            security.require_api_key(None, "wrong")
        except HTTPException as exc:
            assert getattr(exc, "status_code", 401) == 401
        else:
            raise AssertionError("wrong query key should raise 401")
    finally:
        os.environ.pop("VERIFARMS_API_KEY", None)


def test_verifarms_key_takes_precedence_over_legacy():
    os.environ["VERIFARMS_API_KEY"] = "new"
    os.environ["EXPORT_API_KEY"] = "old"
    try:
        security.require_api_key("new", None)  # new var is authoritative
        try:
            security.require_api_key("old", None)  # legacy value no longer valid
        except HTTPException:
            pass
        else:
            raise AssertionError("legacy key must not authenticate when VERIFARMS_API_KEY is set")
    finally:
        os.environ.pop("VERIFARMS_API_KEY", None)
        os.environ.pop("EXPORT_API_KEY", None)


# --- events ----------------------------------------------------------------

def _bundle():
    inst = NS(institution_id="ORG-X", name="X Coop", is_authoritative=False, initial_trust_score=0.6)
    claim = NS(claim_id="c1", claim_type="land_size_hectares", value_numeric=2.0,
               value_string=None, unit="ha", confidence=0.8, timestamp=None)
    return NS(institution=inst, farmer=NS(farmer_id="F-1"), claims=[claim])


def test_build_claim_events_masks_internals():
    events = dispatch.build_claim_events([_bundle()])
    assert len(events) == 1
    e = events[0]
    assert e.claim_type == "land_size_hectares" and e.farmer_id == "F-1"
    assert e.attested_by_id == "ORG-X" and e.authoritative is False
    assert e.event_type == "claim.verified"


def test_publisher_factory_selection():
    os.environ.pop("EVENT_BACKEND", None)
    assert isinstance(publishers.get_event_publisher(), publishers.NullEventPublisher)
    os.environ["EVENT_BACKEND"] = "webhook"
    os.environ["EVENT_WEBHOOK_URLS"] = "http://a, http://b"
    try:
        p = publishers.get_event_publisher()
        assert isinstance(p, publishers.WebhookEventPublisher) and p.urls == ["http://a", "http://b"]
        os.environ["EVENT_WEBHOOK_URLS"] = ""   # webhook but no urls → Null
        assert isinstance(publishers.get_event_publisher(), publishers.NullEventPublisher)
        os.environ["EVENT_BACKEND"] = "bogus"
        assert isinstance(publishers.get_event_publisher(), publishers.NullEventPublisher)
    finally:
        for k in ("EVENT_BACKEND", "EVENT_WEBHOOK_URLS"):
            os.environ.pop(k, None)


def test_publish_claims_merged_best_effort_with_null_backend():
    os.environ.pop("EVENT_BACKEND", None)  # → NullEventPublisher
    assert dispatch.publish_claims_merged([_bundle()]) == 1
    assert dispatch.publish_claims_merged([]) == 0


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
