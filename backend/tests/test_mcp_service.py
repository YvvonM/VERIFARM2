"""Tests for the MCP read-only service + models (no MCP SDK needed)."""

from __future__ import annotations

import asyncio
import importlib
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
            self.__dict__.update(kw)

        def model_dump(self, **_k):
            return dict(self.__dict__)

    pyd.BaseModel = _BaseModel
    pyd.Field = _Field
    pyd.ConfigDict = lambda **k: dict(k)
    sys.modules["pydantic"] = pyd

service = importlib.import_module("app.mcp.service")
svc = service.MockReadService()


def test_get_verified_claims():
    bundle = asyncio.run(svc.get_verified_claims("ORG-TEGEMEO"))
    assert bundle.org_id == "ORG-TEGEMEO" and bundle.count == 2
    assert {c.claim_type for c in bundle.claims} == {"land_size_hectares", "credit_history"}


def test_trace_provenance():
    trace = asyncio.run(svc.trace_provenance("claim_demo_1"))
    assert trace is not None and trace.source_system == "tegemeo_cereals:registry"
    assert [s.stage for s in trace.lineage] == ["source_system", "attestation", "subject"]
    assert asyncio.run(svc.trace_provenance("does-not-exist")) is None


def test_check_compliance_tiers():
    sat = asyncio.run(svc.check_compliance("SAT-SENTINEL2"))
    assert sat.tier == "authoritative" and sat.verified is True
    teg = asyncio.run(svc.check_compliance("Tegemeo Cereals"))
    assert teg.tier == "provisional" and teg.verified is False  # 0.65 < 0.7
    unknown = asyncio.run(svc.check_compliance("Nope Inc"))
    assert unknown.found is False and unknown.tier == "unverified"


def test_org_summary():
    s = asyncio.run(svc.org_summary("ORG-TEGEMEO"))
    assert s.tier == "provisional" and s.claim_count == 2
    assert asyncio.run(svc.org_summary("ORG-MISSING")) is None


def test_read_only_boundary_has_no_write_methods():
    # The service interface must expose ONLY read methods — no write surface.
    methods = {m for m in dir(svc) if not m.startswith("_") and callable(getattr(svc, m))}
    forbidden = {"create", "write", "delete", "update", "ingest", "merge", "publish", "set"}
    assert not any(any(f in m.lower() for f in forbidden) for m in methods), methods
    assert methods == {"get_verified_claims", "trace_provenance", "check_compliance", "org_summary"}


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
