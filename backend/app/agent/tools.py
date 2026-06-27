"""Operational path — vetted, high-stakes tools (LangChain ``@tool``).

These are the hardcoded, optimized query functions the supervisor routes to when
a request is operational ("Is farmer F-12 eligible for the crop loan?", "What is
Tegemeo's trust score?"). Each wraps the existing parameterized read layer, so it
can't be injected and needs no Cypher from the model — the LLM only picks the
tool and supplies arguments, validated by the tool's Pydantic-derived schema.

Decorated with ``langchain_core.tools.tool`` so they bind straight onto the model
via ``ChatOpenAI.bind_tools(TOOLS)`` and dispatch by ``tool.invoke(args)`` — the
orchestration around them (the ReAct loop) stays plain Python in
:mod:`app.agent.copilot`.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from app.database import consumer_queries, profile_queries, trust_graph
from app.database.match_engine import evaluate_product, farmer_exists
from app.database.neo4j_client import DEFAULT_DATABASE, get_shared_driver
from app.services.product_catalog import PRODUCT_CATALOG, get_product

logger = logging.getLogger(__name__)


def _clean(value: Any) -> Any:
    """Recursively convert a Neo4j result into JSON-serializable primitives."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@tool
def verify_farmer_claim(
    farmer_id: str, claim_type: str, min_trust_score: float = 0.5
) -> list[dict[str, Any]]:
    """Verify a single metric for one farmer against trusted institutions.

    Use for "is farmer F-12's land size verified?". ``claim_type`` is e.g.
    'land_size_hectares', 'production_volume_kg', 'credit_history',
    'organic_certified'. Returns every attestation from an institution whose
    trust_score >= min_trust_score, strongest evidence first; empty = unverified.
    """
    rows = trust_graph.verify_claim(get_shared_driver(), farmer_id, claim_type, min_trust_score)
    return _clean(rows)


@tool
def farmer_verified_history(farmer_id: str) -> dict[str, Any] | None:
    """Return the full verified-history profile (every claim_type) for one farmer.

    Use for a complete loan-officer view of farmer F-123. Null if absent.
    """
    return _clean(profile_queries.get_verified_history(get_shared_driver(), farmer_id))


@tool
def cooperative_macro_stats(institution_id: str) -> dict[str, Any] | None:
    """Return anonymized portfolio statistics for one cooperative/institution.

    Members, total verified hectares, unverified members, missing credit history.
    No farmer ids or phone numbers. Null if the institution is absent.
    """
    return _clean(consumer_queries.get_cooperative_stats(get_shared_driver(), institution_id))


_INSTITUTION_TRUST_QUERY = """
MATCH (i:Institution {id: $institution_id})
RETURN i.id                              AS institution_id,
       i.name                            AS name,
       i.type                            AS type,
       coalesce(i.trust_score, 0.0)      AS trust_score,
       coalesce(i.is_authoritative, false) AS is_authoritative,
       coalesce(i.last_comparisons, 0)   AS comparisons,
       coalesce(i.last_agreements, 0)    AS agreements
"""


@tool
def institution_trust_score(institution_id: str) -> dict[str, Any] | None:
    """Return an institution's reputation/trust score and ground-truth track record.

    Use for "what is Tegemeo's (ORG-TEGEMEO) trust score?". Null if absent.
    """
    with get_shared_driver().session(database=DEFAULT_DATABASE) as session:
        record = session.run(_INSTITUTION_TRUST_QUERY, institution_id=institution_id).single()
        return _clean(record.data()) if record else None


@tool
def list_financial_products() -> list[dict[str, Any]]:
    """List financial products a farmer can be matched against (ids, lender, rules).

    Call before check_loan_eligibility when the question names no product id.
    """
    return [
        {
            "product_id": p.product_id,
            "lender_name": p.lender_name,
            "min_trust_score": p.min_trust_score,
            "eligibility_rules": {
                ct: {"min": r.min, "max": r.max, "min_confidence": r.min_confidence}
                for ct, r in p.eligibility_rules.items()
            },
        }
        for p in PRODUCT_CATALOG.values()
    ]


@tool
def check_loan_eligibility(farmer_id: str, product_id: str) -> dict[str, Any]:
    """Check whether a farmer qualifies for a specific financial product.

    ``product_id`` must be one from list_financial_products. Returns ``eligible``
    plus a per-rule ``rule_breakdown`` of which thresholds passed or failed.
    """
    driver = get_shared_driver()
    if not farmer_exists(driver, farmer_id):
        return {"error": f"Farmer {farmer_id!r} does not exist.", "eligible": False}
    try:
        product = get_product(product_id)
    except KeyError as exc:
        return {"error": str(exc), "eligible": False}
    return _clean(evaluate_product(driver, farmer_id, product))


# Registry consumed by the copilot: bound onto the model and dispatched by name.
TOOLS = [
    verify_farmer_claim,
    farmer_verified_history,
    cooperative_macro_stats,
    institution_trust_score,
    list_financial_products,
    check_loan_eligibility,
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}
