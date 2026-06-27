"""Tests for the intent router's deterministic fast-path.

Only the no-LLM fast-path is exercised here (the LLM branch needs a live key and
langchain). Backend is resolved relative to this file; ``pydantic`` is stubbed
only when it isn't installed (the router declares a Pydantic output model at
import time, but the fast-path itself is pure regex).
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

    pyd.BaseModel = _BaseModel
    pyd.Field = _Field
    sys.modules["pydantic"] = pyd

router = importlib.import_module("app.agent.router")


def _fp(query):
    return router._fast_path(query)


def test_aggregate_questions_are_analytical():
    for q in [
        "Which farmers in my portfolio have over 2 hectares of verified land but no credit history?",
        "Show me the distribution of land sizes verified by Sentinel-2 in the last month",
        "How many farmers does ORG-TEGEMEO have?",
    ]:
        d = _fp(q)
        assert d is not None and d.path == "analytical", q


def test_precise_entity_lookups_are_operational():
    for q in [
        "Is farmer F-12 eligible for the smallholder_crop_loan?",
        "What is ORG-TEGEMEO's trust score?",
    ]:
        d = _fp(q)
        assert d is not None and d.path == "operational", q


def test_ambiguous_without_id_defers_to_llm():
    # No id present -> fast-path abstains so the LLM router decides.
    assert _fp("Is Farmer John eligible for the cassava input loan?") is None
    assert _fp("Tell me about verified land") is None


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
