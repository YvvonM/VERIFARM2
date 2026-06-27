"""Tests for bulk ingestion: S3-event parsing, audit, GeoJSON processor."""

from __future__ import annotations

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
    pyd.model_validator = lambda *a, **k: (lambda fn: fn)
    pyd.field_validator = lambda *a, **k: (lambda fn: fn)
    sys.modules["pydantic"] = pyd

try:  # pragma: no cover
    import neo4j  # noqa: F401
except ModuleNotFoundError:
    neo = types.ModuleType("neo4j")
    for _n in ("Driver", "GraphDatabase", "ManagedTransaction"):
        setattr(neo, _n, type(_n, (), {}))
    sys.modules["neo4j"] = neo
    nc = types.ModuleType("app.database.neo4j_client")
    nc.DEFAULT_DATABASE = "neo4j"
    nc.get_driver = lambda *a, **k: None
    sys.modules["app.database.neo4j_client"] = nc

events = importlib.import_module("app.bulk.events")
audit_mod = importlib.import_module("app.bulk.audit")
processor = importlib.import_module("app.bulk.processor")

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]]}


# --- S3 event parsing ------------------------------------------------------

def test_parse_s3_event_decodes_key_and_extension():
    event = {"Records": [
        {"s3": {"bucket": {"name": "partner-uploads"}, "object": {"key": "incoming/my+farm.geojson"}}},
    ]}
    refs = events.parse_s3_event(event)
    assert len(refs) == 1
    assert refs[0].bucket == "partner-uploads" and refs[0].key == "incoming/my farm.geojson"
    assert refs[0].extension == "geojson"


def test_route_extension():
    assert events.route_extension("geojson") == "spatial"
    assert events.route_extension("csv") == "tabular"
    assert events.route_extension("parquet") == "tabular"
    assert events.route_extension("txt") is None


# --- audit -----------------------------------------------------------------

def test_audit_counters_and_store():
    store = audit_mod.InMemoryAuditStore()
    a = audit_mod.BulkJobAudit(source="partner", object_key="f.geojson")
    a.total_rows, a.succeeded, a.failed_validation = 3, 2, 1
    a.finish()
    store.record(a)
    assert store.records[0].succeeded == 2 and store.records[0].finished_at is not None


# --- GeoJSON processor -----------------------------------------------------

def test_process_geojson_tallies_and_builds_claims():
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": SQUARE, "properties": {"farmer_id": "F-1"}},
        {"type": "Feature", "geometry": None, "properties": {"farmer_id": "F-2"}},  # invalid
    ]}
    captured: list = []
    store = audit_mod.InMemoryAuditStore()
    audit = processor.process_geojson(
        fc, source="partner_x", institution_id="ORG-PARTNER", institution_name="Partner X",
        publish=lambda bundles: captured.extend(bundles), audit_store=store,
    )
    assert audit.total_rows == 2 and audit.succeeded == 1 and audit.failed_validation == 1
    assert len(captured) == 1
    claim_types = {c.claim_type for c in captured[0].claims}
    assert claim_types == {"land_size_hectares", "parcel_bbox"}
    land = next(c for c in captured[0].claims if c.claim_type == "land_size_hectares")
    assert 110 < land.value_numeric < 140
    assert store.records and store.records[0].succeeded == 1


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
