"""Tests for the OCR -> reified bundle convergence (claim_bridge).

Locks the behavior that makes OCR claims visible to the trust layer, the Loan
Officer Copilot, and the DLQ Investigator: an extracted ``land_size_ha`` field
must become a numeric ``land_size_hectares`` claim under a non-authoritative
institution. ``pydantic`` is stubbed only when not installed (the reified models
are exercised as plain field containers; validators are no-ops here).
"""

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:  # pragma: no cover - prefer real pydantic when present.
    import pydantic  # noqa: F401
except ModuleNotFoundError:
    pyd = types.ModuleType("pydantic")

    def _Field(default=..., **kw):
        if "default_factory" in kw:
            return kw["default_factory"]()
        return None if default is ... else default

    def _ConfigDict(**kw):
        return dict(kw)

    def _model_validator(*_a, **_k):
        def _wrap(fn):
            return fn
        return _wrap

    class _BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    pyd.BaseModel = _BaseModel
    pyd.Field = _Field
    pyd.ConfigDict = _ConfigDict
    pyd.model_validator = _model_validator
    sys.modules["pydantic"] = pyd

bridge = importlib.import_module("app.verification.claim_bridge")


class _FakeOCRClaim:
    """Duck-typed stand-in matching app.verification.ocr.models.OCRClaim."""

    def __init__(self, extracted_fields):
        self.extracted_fields = extracted_fields
        self.confidence = 0.8
        self.document_ref = "doc_register_001"
        self.processed_at = datetime(2026, 6, 25, tzinfo=timezone.utc)


def _bundle():
    claim = _FakeOCRClaim({
        "land_size_ha": {"value": "2.5", "confidence": 0.85, "raw_match": "2.5 ha"},
        "crop_type": {"value": "maize", "confidence": 0.75, "raw_match": "maize"},
        "farmer_name": {"value": "Jane Wanjiru", "confidence": 0.7, "raw_match": "Jane"},
    })
    return bridge.ocr_claim_to_bundle(
        farmer_id="F-1",
        claim=claim,
        institution_id="coop_kirinyaga_001",
        institution_name="Kirinyaga Farmers Cooperative",
    )


def test_land_size_field_becomes_numeric_reified_claim():
    bundle = _bundle()
    by_type = {c.claim_type: c for c in bundle.claims}
    assert "land_size_hectares" in by_type  # mapped from 'land_size_ha'
    land = by_type["land_size_hectares"]
    assert land.value_numeric == 2.5 and land.unit == "ha" and land.value_string is None


def test_categorical_fields_become_string_claims():
    by_type = {c.claim_type: c for c in _bundle().claims}
    assert by_type["crop_type"].value_string == "maize"
    assert by_type["crop_type"].value_numeric is None
    # An unmapped field passes through under its own name as categorical.
    assert by_type["farmer_name"].value_string == "Jane Wanjiru"


def test_register_is_non_authoritative_with_collection_consent():
    inst = _bundle().institution
    assert inst.is_authoritative is False
    assert inst.consent_at_source is True
    assert inst.type == "Cooperative"


def test_no_structured_fields_yields_no_bundle():
    assert bridge.ocr_claim_to_bundle("F-1", _FakeOCRClaim({}), "org", "Org") is None


# --- provider integration seam (credit + identity) -------------------------

import asyncio  # noqa: E402

from app.verification.providers import factory  # noqa: E402
from app.verification.providers.types import (  # noqa: E402
    CreditHistoryResult,
    IdentityVerificationResult,
)

_NOW = datetime(2026, 6, 25, tzinfo=timezone.utc)


class _FakeCreditProvider:
    async def check_credit_history(self, *, country, identifier):
        return CreditHistoryResult(
            provider="TransUnion Kenya", credit_score=720, has_default_flag=False,
            repayment_history_summary="ok", confidence=0.92, checked_at=_NOW,
        )


class _FakeIdentityProvider:
    def __init__(self, match=True):
        self._match = match

    async def verify_identity(self, *, country, claimed_name, identifier, identifier_type=None):
        return IdentityVerificationResult(
            provider="Smile Identity (BVN)", match=self._match,
            verified_name="Chinedu Okafor" if self._match else None,
            submitted_identifier_type="BVN", confidence=0.95, checked_at=_NOW,
        )


def test_factory_raises_not_configured_when_env_absent():
    # No CREDIT_PROVIDER/IDENTITY_PROVIDER env in the test environment.
    for getter in (factory.get_credit_provider, factory.get_identity_provider):
        try:
            getter()
        except factory.NotConfigured:
            continue
        raise AssertionError(f"{getter.__name__} should raise NotConfigured")


def test_bridge_builds_reified_credit_claim():
    br = bridge.ClaimBridge(credit_provider=_FakeCreditProvider())
    vc = asyncio.run(br.build_credit_claim(farmer_id="F-1", country="Kenya", identifier="+254700"))
    assert vc.credit_score == 720 and vc.provider == "TransUnion Kenya"
    by_type = {c.claim_type: c for c in vc.to_payload_bundle().claims}
    assert by_type["credit_history"].value_numeric == 720.0
    assert by_type["credit_default_flag"].value_string == "false"


def test_bridge_builds_reified_identity_claim_on_match():
    br = bridge.ClaimBridge(identity_provider=_FakeIdentityProvider(match=True))
    vi = asyncio.run(br.build_identity_claim(
        farmer_id="F-1", country="Nigeria", claimed_name="Chinedu Okafor", identifier="221"))
    assert vi is not None and vi.verified_name == "Chinedu Okafor"
    claim = vi.to_payload_bundle().claims[0]
    assert claim.claim_type == "identity_verified" and claim.value_string == "Chinedu Okafor"


def test_bridge_identity_non_match_returns_none():
    br = bridge.ClaimBridge(identity_provider=_FakeIdentityProvider(match=False))
    vi = asyncio.run(br.build_identity_claim(
        farmer_id="F-1", country="Nigeria", claimed_name="X", identifier="221"))
    assert vi is None


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
