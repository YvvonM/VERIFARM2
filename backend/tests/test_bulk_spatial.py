"""Tests for spatial extraction (GeoJSON / STAC → flattened metadata)."""

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

spatial = importlib.import_module("app.bulk.spatial")

# ~0.01° square at the equator (≈1.11 km a side ⇒ ~123 ha).
SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]]}


def test_bounding_box():
    assert spatial.bounding_box(SQUARE) == (0.0, 0.0, 0.01, 0.01)


def test_area_hectares_for_known_square():
    ha = spatial.area_hectares(SQUARE)
    assert 110 < ha < 140, ha  # geodesic ~123 ha


def test_point_and_line_have_zero_area():
    assert spatial.area_hectares({"type": "Point", "coordinates": [1, 2]}) == 0.0
    assert spatial.area_hectares(
        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
    ) == 0.0


def test_extract_geojson_feature_flattens():
    feature = {"type": "Feature", "geometry": SQUARE, "properties": {"datetime": "2026-06-01T00:00:00Z"}}
    m = spatial.extract_geojson_feature(feature)
    assert m.geometry_type == "Polygon" and m.observed_at == "2026-06-01T00:00:00Z"
    assert m.bbox_string() == "0.0,0.0,0.01,0.01"
    assert 110 < m.area_hectares < 140


def test_extract_stac_item_prefers_declared_bbox():
    item = {
        "type": "Feature",
        "bbox": [10.0, 20.0, 11.0, 21.0],
        "geometry": SQUARE,
        "properties": {"datetime": "2026-05-01T00:00:00Z"},
    }
    m = spatial.extract_stac_item(item)
    assert (m.min_lon, m.min_lat, m.max_lon, m.max_lat) == (10.0, 20.0, 11.0, 21.0)
    assert m.observed_at == "2026-05-01T00:00:00Z"


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
