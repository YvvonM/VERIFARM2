"""Tests for the streaming core: normalize, micro-batch, dedup, aggregate.

Pure logic (no broker). ``pydantic`` is stubbed only when not installed.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from datetime import datetime, timezone
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

    def _ConfigDict(**kw):
        return dict(kw)

    def _deco(*_a, **_k):
        def _w(fn):
            return fn
        return _w

    class _BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    pyd.BaseModel = _BaseModel
    pyd.Field = _Field
    pyd.ConfigDict = _ConfigDict
    pyd.model_validator = _deco
    pyd.field_validator = _deco
    sys.modules["pydantic"] = pyd

normalize_mod = importlib.import_module("app.streaming.normalize")
microbatch = importlib.import_module("app.streaming.microbatch")
dedup = importlib.import_module("app.streaming.dedup")
aggregate = importlib.import_module("app.streaming.aggregate")
models = importlib.import_module("app.streaming.models")

normalize = normalize_mod.normalize
TelemetryFormatError = normalize_mod.TelemetryFormatError


# --- normalize -------------------------------------------------------------

def test_normalize_diverse_payload_and_epoch_seconds():
    r = normalize({"sensorId": "S1", "farmerId": "F-1", "metric": "soil_moisture_pct",
                   "value": "42.5", "ts": 1717200000, "unit": "%"})
    assert r.sensor_id == "S1" and r.farmer_id == "F-1" and r.value == 42.5 and r.unit == "%"
    assert r.observed_at.year == 2024 and r.message_id.startswith("tel_")  # synthesized


def test_normalize_epoch_millis_and_iso():
    r_ms = normalize({"device_id": "S", "farmer": "F", "measurement": "t", "reading": 1, "time": 1717200000000})
    r_iso = normalize({"sensor": "S", "subject_id": "F", "type": "t", "v": 1, "eventTime": "2026-06-01T00:00:00Z"})
    assert r_ms.observed_at.year == 2024
    assert r_iso.observed_at.year == 2026 and r_iso.observed_at.tzinfo is not None


def test_normalize_explicit_message_id_passthrough_and_dedupe_key_is_deterministic():
    p = {"id": "m-7", "sensorId": "S", "farmerId": "F", "metric": "x", "value": 1, "ts": 1717200000}
    assert normalize(p).message_id == "m-7"
    # No id → identical payloads get the SAME synthesized id (dedupe on resend).
    a = normalize({"sensorId": "S", "farmerId": "F", "metric": "x", "value": 1, "ts": 1717200000})
    b = normalize({"sensorId": "S", "farmerId": "F", "metric": "x", "value": 1, "ts": 1717200000})
    assert a.message_id == b.message_id


def test_normalize_rejects_missing_fields():
    try:
        normalize({"value": 1})
    except TelemetryFormatError:
        pass
    else:
        raise AssertionError("missing sensor/farmer/metric should raise")


# --- micro-batch -----------------------------------------------------------

def test_microbatch_flushes_on_size():
    mb = microbatch.MicroBatcher(max_size=3, max_age_seconds=999)
    mb.add("a"); mb.add("b")
    assert not mb.size_full()
    mb.add("c")
    assert mb.size_full() and mb.should_flush()
    assert mb.drain() == ["a", "b", "c"] and mb.size == 0


def test_microbatch_flushes_on_age():
    mb = microbatch.MicroBatcher(max_size=999, max_age_seconds=0)
    mb.add("a")
    assert mb.age_due() and mb.should_flush()


# --- dedup -----------------------------------------------------------------

def test_inmemory_dedup_exactly_once():
    s = dedup.InMemoryDedupStore()
    assert asyncio.run(s.filter_new(["a", "b"])) == {"a", "b"}
    asyncio.run(s.mark_committed(["a"]))
    assert asyncio.run(s.filter_new(["a", "b"])) == {"b"}      # 'a' already committed
    assert asyncio.run(s.seen("a")) and not asyncio.run(s.seen("b"))


# --- aggregate -------------------------------------------------------------

def _reading(farmer, metric, value, *, unit=None, ts=None):
    return models.TelemetryReading(
        message_id=f"{farmer}-{metric}-{value}", sensor_id="S", farmer_id=farmer,
        metric=metric, value=value, unit=unit,
        observed_at=ts or datetime(2026, 6, 1, tzinfo=timezone.utc), source="iot",
    )


def test_aggregate_means_per_farmer_metric():
    readings = [
        _reading("F-1", "soil_moisture_pct", 40.0, unit="%"),
        _reading("F-1", "soil_moisture_pct", 44.0, unit="%"),
        _reading("F-1", "air_temperature_c", 21.0),
        _reading("F-2", "soil_moisture_pct", 30.0),
    ]
    bundles = aggregate.aggregate_readings(readings)
    by_farmer = {b.farmer.farmer_id: b for b in bundles}
    assert set(by_farmer) == {"F-1", "F-2"}
    f1 = {c.claim_type: c for c in by_farmer["F-1"].claims}
    assert f1["soil_moisture_pct"].value_numeric == 42.0          # mean(40,44)
    assert f1["air_temperature_c"].value_numeric == 21.0
    assert by_farmer["F-1"].institution.type == "SensorNetwork"


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
