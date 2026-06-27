"""Tests for the DLQ Investigator's deterministic resolution policy.

The policy is the agent's decision core, so it must be predictable: the same
conflict + source history always yields the same action/severity/confidence.
Backend is resolved relative to this file; ``pydantic`` is stubbed only when not
installed (the models are plain field containers for this test).
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:  # pragma: no cover - prefer real pydantic when present.
    import pydantic  # noqa: F401
except ModuleNotFoundError:
    pyd = types.ModuleType("pydantic")

    def _Field(default=..., **_kw):
        return None if default is ... else default

    class _BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

        def model_dump(self, **_kw):
            return dict(self.__dict__)

        def model_copy(self, update=None):
            obj = self.__class__(**{**self.__dict__, **(update or {})})
            return obj

    pyd.BaseModel = _BaseModel
    pyd.Field = _Field
    sys.modules["pydantic"] = pyd

policy = importlib.import_module("app.investigator.policy")
inv = importlib.import_module("app.models.investigation")

ResolutionAction = inv.ResolutionAction
ConflictSeverity = inv.ConflictSeverity
SourceHistory = inv.SourceHistory


def _source(trust, comparisons=0, agreements=0, prior=0, name="Tegemeo Coop"):
    return SourceHistory(
        institution_id="ORG-X", institution_name=name, trust_score=trust,
        comparisons=comparisons, agreements=agreements, prior_conflicts=prior,
    )


def _rec(variance, source, auth=2.0, reported=5.0, claim_type="land_size_hectares"):
    return policy.recommend(variance, source, auth, reported, claim_type)


# ---- action selection -----------------------------------------------------

def test_low_trust_source_is_penalized():
    rec = _rec(0.6, _source(trust=0.30))
    assert rec.action == ResolutionAction.PENALIZE_SOURCE


def test_repeat_offender_is_penalized_even_with_decent_trust():
    rec = _rec(0.4, _source(trust=0.65, prior=3))
    assert rec.action == ResolutionAction.PENALIZE_SOURCE


def test_poor_agreement_rate_is_penalized():
    # 1/5 agreement = 20% over 5 comparisons -> unreliable.
    rec = _rec(0.4, _source(trust=0.65, comparisons=5, agreements=1))
    assert rec.action == ResolutionAction.PENALIZE_SOURCE


def test_reliable_isolated_disagreement_is_escalated():
    rec = _rec(0.4, _source(trust=0.85, comparisons=10, agreements=10, prior=0))
    assert rec.action == ResolutionAction.FLAG_FOR_REVIEW


def test_unscored_borderline_source_is_insufficient_data():
    rec = _rec(0.22, _source(trust=0.55, comparisons=0, agreements=0, prior=0))
    assert rec.action == ResolutionAction.INSUFFICIENT_DATA
    assert rec.confidence <= 0.4


def test_mid_trust_with_history_trusts_ground_truth():
    rec = _rec(0.4, _source(trust=0.55, comparisons=6, agreements=5, prior=1))
    assert rec.action == ResolutionAction.TRUST_GROUND_TRUTH


# ---- severity + confidence ------------------------------------------------

def test_severity_bands():
    assert policy.severity_for(0.21) == ConflictSeverity.MODERATE
    assert policy.severity_for(0.35) == ConflictSeverity.HIGH
    assert policy.severity_for(0.80) == ConflictSeverity.CRITICAL


def test_confidence_within_bounds_and_rationale_present():
    for variance in (0.21, 0.35, 0.9):
        for trust in (0.2, 0.55, 0.9):
            rec = _rec(variance, _source(trust=trust, comparisons=5, agreements=3, prior=1))
            assert 0.0 <= rec.confidence <= 0.95
            assert rec.rationale and str(round(variance * 100)) in rec.rationale


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
