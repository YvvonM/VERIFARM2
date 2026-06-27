"""Logic tests for the agent's safety + rendering layers.

Covers the two pieces that must be correct regardless of the LLM:

  * ``cypher_guard.assert_read_only`` — rejects every write/admin/stacked query.
  * ``graph.build_component``        — maps each tool-result shape to the right
    validated GenUI component, never fabricating chart data.

The backend package is located **relative to this file** (``backend/`` is two
parents up), so the test is portable across machines and CI. When ``pydantic`` /
``neo4j`` aren't installed, minimal stand-ins are injected so the real modules
still import; if they are installed, the real packages are used untouched.

Run standalone (``python tests/test_agent_logic.py``) or under pytest.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

# Resolve the backend package directory relative to this test file.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _ensure_stubs() -> None:
    """Inject tiny stand-ins for uninstalled deps so real modules import."""
    try:  # pragma: no cover - prefer the real package when present.
        import pydantic  # noqa: F401
    except ModuleNotFoundError:
        pyd = types.ModuleType("pydantic")

        def Field(default=..., **_kw):
            return None if default is ... else default

        class BaseModel:
            def __init__(self, **kw):
                self.__dict__.update(kw)

            def model_dump(self):
                return dict(self.__dict__)

        pyd.BaseModel = BaseModel
        pyd.Field = Field
        sys.modules["pydantic"] = pyd

    try:  # pragma: no cover - prefer the real driver when present.
        import neo4j  # noqa: F401
    except ModuleNotFoundError:
        neo = types.ModuleType("neo4j")
        neo.Driver = type("Driver", (), {})
        neo.GraphDatabase = object
        neo.ManagedTransaction = object
        sys.modules["neo4j"] = neo
        # neo4j_client pulls the driver at import; stub the bits the guard needs.
        nc = types.ModuleType("app.database.neo4j_client")
        nc.DEFAULT_DATABASE = "neo4j"
        nc.get_shared_driver = lambda: None
        sys.modules["app.database.neo4j_client"] = nc


_ensure_stubs()

guard = importlib.import_module("app.agent.cypher_guard")
graph = importlib.import_module("app.agent.graph")


# ---------------------------------------------------------------------------
# cypher_guard.assert_read_only
# ---------------------------------------------------------------------------

SAFE_QUERIES = [
    "MATCH (f:Farmer) RETURN f.region AS region, count(*) AS n",
    "MATCH (f:Farmer {id:$id})<-[:BELONGS_TO]-(c:Claim) RETURN c.claim_type, c.value_numeric",
    "MATCH (i:Institution) RETURN i.name ORDER BY i.trust_score DESC LIMIT 10;",
]

UNSAFE_QUERIES = [
    "MATCH (f:Farmer) DETACH DELETE f",
    "CREATE (f:Farmer {id:'x'})",
    "MATCH (f:Farmer {id:'x'}) SET f.verified = true",
    "MATCH (f:Farmer) RETURN f; MATCH (i:Institution) DELETE i",
    "MERGE (f:Farmer {id:'x'})",
    "MATCH (f) CALL apoc.create.node(['X'],{}) YIELD node RETURN node",
    "MATCH (f:Farmer) REMOVE f.verified RETURN f",
    "",
]


def test_safe_queries_allowed():
    for q in SAFE_QUERIES:
        assert guard.assert_read_only(q) == q


def test_unsafe_queries_rejected():
    for q in UNSAFE_QUERIES:
        try:
            guard.assert_read_only(q)
        except guard.UnsafeCypherError:
            continue
        raise AssertionError(f"Write/unsafe query was not rejected: {q!r}")


# ---------------------------------------------------------------------------
# build_component — now takes a RAW tool/query result (not a collected wrapper).
# ---------------------------------------------------------------------------


def test_macro_stats_to_barchart():
    ct, props = graph.build_component({
        "institution_id": "ORG-TEGEMEO", "total_members": 42,
        "total_verified_hectares": 130.5, "unverified_members": 7,
        "missing_credit_history_count": 12})
    assert ct == "BarChart"
    assert len(props.data) == 4  # the four numeric metrics; id excluded
    assert all(row["metric"] != "Institution id" for row in props.data)


def test_two_column_series_to_barchart():
    ct, props = graph.build_component(
        [{"region": "Nakuru", "farmers": 312}, {"region": "Kano", "farmers": 241}])
    assert ct == "BarChart" and props.xKey == "region" and props.yKey == "farmers"


def test_numeric_first_column_swaps_axis():
    ct, props = graph.build_component(
        [{"count": 5, "crop": "Maize"}, {"count": 9, "crop": "Beans"}])
    assert ct == "BarChart" and props.xKey == "crop" and props.yKey == "count"


def test_multicolumn_list_to_table():
    ct, props = graph.build_component(
        [{"claim_type": "land_size_hectares", "value_numeric": 2.5,
          "confidence": 0.9, "attested_by": "Sat"}])
    assert ct == "Table" and props.columns[0] == "claim_type" and len(props.columns) == 4


def test_verified_history_flattened_to_table():
    ct, props = graph.build_component({
        "farmer_id": "F-1", "verified_history": {"land_size_hectares": [
            {"value_numeric": 2.5, "confidence": 0.99, "source_name": "Sat", "is_authoritative": True},
            {"value_numeric": 2.2, "confidence": 0.8, "source_name": "Coop", "is_authoritative": False}]}})
    assert ct == "Table" and len(props.rows) == 2 and props.rows[0][0] == "land_size_hectares"


def test_eligibility_to_table_with_caption():
    ct, props = graph.build_component({
        "eligible": False, "rule_breakdown": [
            {"claim_type": "land_size_hectares", "satisfied": False,
             "required_min": 1.5, "required_max": None, "matched_value": None}]})
    assert ct == "Table" and "NOT eligible" in props.caption and len(props.rows) == 1


def test_empty_and_missing_results_render_gracefully():
    ct, props = graph.build_component([])
    assert ct == "Table" and props.rows == []
    ct, props = graph.build_component(None)
    assert ct == "Table" and "No matching data" in (props.caption or "")


def test_error_only_result_still_renders():
    ct, props = graph.build_component({"error": "Farmer 'X' does not exist."})
    assert ct == "Table" and "error" in props.columns


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required).
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001 - report-and-continue for the runner.
            print(f"FAIL {fn.__name__}: {exc}")
            failures.append(fn.__name__)
    print("\n" + ("ALL PASSED" if not failures else f"{len(failures)} FAILURE(S): {failures}"))
    sys.exit(1 if failures else 0)
