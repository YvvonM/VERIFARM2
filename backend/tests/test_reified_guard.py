"""Tests for the schema-split enforcement (reified-only publish boundary).

Pure-logic gates, runnable without a DB: the text gate rejects gold-layer Cypher,
the type gate rejects anything that isn't a strict PayloadBundle. ``pydantic`` is
stubbed only when not installed.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:  # pragma: no cover - prefer real pydantic.
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

    def _field_validator(*_a, **_k):
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
    pyd.field_validator = _field_validator
    sys.modules["pydantic"] = pyd

guard = importlib.import_module("app.ingestion.reified_guard")
from app.models.reified import Claim, Farmer, Institution, PayloadBundle  # noqa: E402

GoldLayerWriteError = guard.GoldLayerWriteError


def _valid_bundle() -> PayloadBundle:
    """A minimal, schema-valid reified bundle (works under real or stubbed pydantic)."""
    return PayloadBundle(
        institution=Institution(institution_id="ORG-X", name="X"),
        farmer=Farmer(farmer_id="F-1"),
        claims=[Claim(claim_type="land_size_hectares", value_numeric=1.0, confidence=0.5,
                      source_category="cooperative")],
    )


# --- text gate: assert_reified_only ----------------------------------------

REIFIED_OK = [
    "UNWIND $bundles AS b MERGE (i:Institution {id:b.id})-[:ATTESTS_TO]->(c:Claim)-[:BELONGS_TO]->(f:Farmer)",
    "MATCH (i:Institution)-[:ATTESTS_TO]->(c:Claim)-[:BELONGS_TO]->(f:Farmer) RETURN c",
    "MERGE (i)-[ga:GRANTED_ACCESS]->(f) SET ga.status='APPROVED'",  # reified consent edge — allowed
]

GOLD_LAYER_REJECT = [
    "CREATE (o:Organization {id:'org_1'})",
    "MERGE (c:Claim)-[:VERIFIED_BY {confidence:0.9}]->(o:Organization)",
    "CREATE (c:Claim)-[:ABOUT]->(f:Farmer)",
    "CREATE (d:Document {id:'doc1'})",
    "MERGE (cg:ConsentGrant)-[:SCOPED_TO]->(o:Organization)",
    "MERGE (f:Farmer)-[:GRANTED]->(cg:ConsentGrant)",
]


def test_reified_cypher_is_allowed():
    for q in REIFIED_OK:
        assert guard.assert_reified_only(q) == q


def test_gold_layer_cypher_is_rejected():
    for q in GOLD_LAYER_REJECT:
        try:
            guard.assert_reified_only(q)
        except GoldLayerWriteError:
            continue
        raise AssertionError(f"gold-layer Cypher not rejected: {q!r}")


# --- type gate: enforce_reified_contract -----------------------------------

def test_payload_bundles_pass_the_type_gate():
    bundles = [_valid_bundle()]
    assert guard.enforce_reified_contract(bundles) == bundles


def test_non_bundle_payloads_are_rejected():
    for bad in ({"label": "Organization"}, "not-a-bundle", 42, None):
        try:
            guard.enforce_reified_contract([bad])
        except GoldLayerWriteError:
            continue
        raise AssertionError(f"non-bundle payload not rejected: {bad!r}")


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
