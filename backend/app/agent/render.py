"""Deterministic rendering of tool/query results into GenUI components.

The LLM decides *what data to fetch* (router → tools/Cypher) and *how to phrase
the answer* (synthesis), but it never fabricates the chart/table — that mapping
is deterministic here, so a rendered component always reflects exactly what the
database returned. Returns a Pydantic props model (validated by construction).
"""

from __future__ import annotations

from typing import Any

from app.models.ui_schemas import BarChartProps, TableProps


def build_component(rows: Any):
    """Map a tool/query result to a (componentType, props) pair.

    Accepts the shapes the operational tools and analytical Cypher return:
    a list of row dicts, a single dict, or a scalar.
    """
    if isinstance(rows, dict):
        return _component_from_dict(rows)
    if isinstance(rows, list):
        return _component_from_list(rows)
    if rows in (None, ""):
        return "Table", TableProps(columns=["result"], rows=[], caption="No matching data was found.")
    return "Table", TableProps(columns=["result"], rows=[[_scalar(rows)]])


def _component_from_dict(result: dict[str, Any]):
    if "verified_history" in result:
        return _verified_history_table(result)
    if "rule_breakdown" in result:
        return _eligibility_table(result)
    if "error" in result and len(result) == 1:
        return "Table", TableProps(
            columns=["error"], rows=[[result["error"]]], caption="The copilot could not answer."
        )

    numeric = {
        k: v for k, v in result.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    if numeric:
        data = [{"metric": _humanize(k), "value": v} for k, v in numeric.items()]
        return "BarChart", BarChartProps(data=data, xKey="metric", yKey="value")

    return "Table", TableProps(
        columns=["field", "value"],
        rows=[[_humanize(k), _scalar(v)] for k, v in result.items()],
    )


def _component_from_list(rows: list[Any]):
    if not rows:
        return "Table", TableProps(columns=["result"], rows=[], caption="No matching records.")
    if not all(isinstance(r, dict) for r in rows):
        return "Table", TableProps(columns=["value"], rows=[[_scalar(r)] for r in rows])

    bar = _try_bar_chart(rows)
    if bar is not None:
        return bar

    columns = list({k: None for row in rows for k in row}.keys())  # ordered union
    table_rows = [[_scalar(row.get(c)) for c in columns] for row in rows]
    return "Table", TableProps(columns=columns, rows=table_rows)


def _try_bar_chart(rows: list[dict[str, Any]]):
    columns = list({k: None for row in rows for k in row}.keys())
    if len(columns) != 2:
        return None
    cat_key, val_key = columns
    if _all_numeric(rows, val_key) and not _all_numeric(rows, cat_key):
        pass
    elif _all_numeric(rows, cat_key) and not _all_numeric(rows, val_key):
        cat_key, val_key = val_key, cat_key
    else:
        return None
    data = [{cat_key: _scalar(r.get(cat_key)), val_key: r.get(val_key)} for r in rows]
    return "BarChart", BarChartProps(data=data, xKey=cat_key, yKey=val_key)


def _verified_history_table(result: dict[str, Any]):
    columns = ["claim_type", "value", "confidence", "source", "authoritative"]
    table_rows: list[list[Any]] = []
    for claim_type, attestations in (result.get("verified_history") or {}).items():
        for att in attestations:
            table_rows.append([
                claim_type,
                att.get("value_numeric"),
                att.get("confidence"),
                att.get("source_name"),
                att.get("is_authoritative"),
            ])
    caption = f"Verified history for farmer {result.get('farmer_id', '?')}."
    return "Table", TableProps(columns=columns, rows=table_rows, caption=caption)


def _eligibility_table(result: dict[str, Any]):
    columns = ["claim_type", "satisfied", "required_min", "required_max", "matched_value"]
    table_rows = [
        [r.get("claim_type"), r.get("satisfied"), r.get("required_min"),
         r.get("required_max"), r.get("matched_value")]
        for r in (result.get("rule_breakdown") or [])
    ]
    eligible = result.get("eligible")
    caption = f"Eligibility: {'ELIGIBLE' if eligible else 'NOT eligible'}."
    return "Table", TableProps(columns=columns, rows=table_rows, caption=caption)


# -- helpers ----------------------------------------------------------------


def _all_numeric(rows: list[dict[str, Any]], key: str) -> bool:
    vals = [row.get(key) for row in rows]
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals)


def _humanize(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
