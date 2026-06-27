"""Tests for the Sprint 2 core: secrets seam, failure classification, watermark.

Pure logic, runnable without external services. ``neo4j`` is stubbed only when
absent (the watermark module imports a constant from the neo4j client).
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

try:  # pragma: no cover - stub only when neo4j isn't installed.
    import neo4j  # noqa: F401
except ModuleNotFoundError:
    neo = types.ModuleType("neo4j")
    neo.Driver = type("Driver", (), {})
    neo.GraphDatabase = object
    sys.modules["neo4j"] = neo
    nc = types.ModuleType("app.database.neo4j_client")
    nc.DEFAULT_DATABASE = "neo4j"
    nc.get_driver = lambda *a, **k: None
    sys.modules["app.database.neo4j_client"] = nc

secrets = importlib.import_module("app.secrets")
observability = importlib.import_module("app.ingestion.observability")
watermark = importlib.import_module("app.ingestion.watermark")

FailureCategory = observability.FailureCategory


# --- secrets seam ----------------------------------------------------------

def test_env_backend_resolves_logical_name_to_env_var(monkeypatch=None):
    os.environ.pop("SECRETS_BACKEND", None)  # default = env
    os.environ["COOP_PG_DSN"] = "postgresql://u:p@h:5432/db"
    try:
        assert secrets.get_secret("coop_pg_dsn") == "postgresql://u:p@h:5432/db"
        assert secrets.get_secret("sources/tegemeo/dsn") is None  # SOURCES_TEGEMEO_DSN unset
        assert secrets.get_secret("missing", default="fallback") == "fallback"
    finally:
        os.environ.pop("COOP_PG_DSN", None)


def test_unknown_backend_raises():
    os.environ["SECRETS_BACKEND"] = "nope"
    try:
        secrets.get_secret("x")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown SECRETS_BACKEND should raise ValueError")
    finally:
        os.environ.pop("SECRETS_BACKEND", None)


# --- failure classification ------------------------------------------------

class _OperationalError(Exception):
    pass


class _ValidationError(Exception):
    pass


class _GoldLayerWriteError(Exception):
    pass


def test_failure_classification():
    import asyncio
    assert observability.classify(ConnectionError("down")) is FailureCategory.CONNECTION
    assert observability.classify(asyncio.TimeoutError()) is FailureCategory.CONNECTION
    assert observability.classify(_OperationalError("connection refused")) is FailureCategory.CONNECTION
    assert observability.classify(_ValidationError("3 validation errors")) is FailureCategory.MAPPING
    assert observability.classify(_GoldLayerWriteError("gold-layer")) is FailureCategory.WRITE
    assert observability.classify(ValueError("boom")) is FailureCategory.UNKNOWN


def test_notify_without_webhook_does_not_raise():
    os.environ.pop("ALERT_WEBHOOK_URL", None)
    observability.notify("subject", "message", category="mapping")  # logs only, no exception


# --- watermark / CDC state -------------------------------------------------

def test_in_memory_watermark_roundtrip():
    store = watermark.InMemoryWatermarkStore()
    assert store.get("tegemeo") is None
    store.set("tegemeo", "2026-06-25T10:00:00+00:00")
    assert store.get("tegemeo") == "2026-06-25T10:00:00+00:00"


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
