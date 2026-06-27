"""MATCH engine — evaluate a farmer's reified claims against product rules.

This is a lightweight, data-driven rules engine. A :class:`FinancialProduct`
carries its thresholds as *data* (``min_trust_score`` + ``eligibility_rules``);
this module translates those into a single parameterized Cypher query that
traverses the farmer's :class:`Claim` nodes and decides eligibility. No product
logic is hardcoded here, so new products are added to the catalog without
touching this file.

Eligibility rule, per metric: there must exist at least one claim of the given
``claim_type`` that

  * belongs to the farmer,
  * is attested by an institution whose ``trust_score`` ≥ the product's
    ``min_trust_score`` (the reputation bar), and
  * satisfies the metric's ``min`` / ``max`` / ``min_confidence`` thresholds.

A farmer is eligible for a product only if *every* rule is satisfied.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE
from app.models.products import FinancialProduct

logger = logging.getLogger(__name__)


FARMER_EXISTS_QUERY = "MATCH (f:Farmer {id: $farmer_id}) RETURN count(f) > 0 AS exists"


# $rules is a list of {claim_type, min, max, min_confidence}. The query is fully
# parameterized (no string interpolation), and UNWIND lets one planned query
# evaluate an arbitrary number of rules. The reputation bar ($min_trust_score)
# is applied at the institution, so only sufficiently-trusted attestations count.
EVALUATE_ELIGIBILITY_QUERY = """
MATCH (f:Farmer {id: $farmer_id})
UNWIND $rules AS rule
OPTIONAL MATCH (inst:Institution)-[:ATTESTS_TO]->
              (c:Claim {claim_type: rule.claim_type})-[:BELONGS_TO]->(f)
  WHERE coalesce(inst.trust_score, 0.0) >= $min_trust_score
    AND coalesce(c.confidence, 0.0)     >= coalesce(rule.min_confidence, 0.0)
    AND (rule.min IS NULL OR c.value_numeric >= rule.min)
    AND (rule.max IS NULL OR c.value_numeric <= rule.max)
// Best (most-confident) qualifying claim first, so matches[0] is the strongest.
WITH f, rule, c
ORDER BY coalesce(c.confidence, 0.0) DESC
WITH f, rule, collect(c) AS matches
WITH f, {
       claim_type:              rule.claim_type,
       satisfied:               size(matches) > 0,
       required_min:            rule.min,
       required_max:            rule.max,
       required_min_confidence: rule.min_confidence,
       matched_value:           CASE WHEN size(matches) > 0 THEN matches[0].value_numeric END,
       matched_confidence:      CASE WHEN size(matches) > 0 THEN matches[0].confidence    END
     } AS rule_result
WITH f, collect(rule_result) AS rule_breakdown
RETURN f.id                                          AS farmer_id,
       all(r IN rule_breakdown WHERE r.satisfied)    AS eligible,
       rule_breakdown                                AS rule_breakdown
"""


def _flatten_rules(product: FinancialProduct) -> list[dict[str, Any]]:
    """Turn ``{claim_type: EligibilityRule}`` into the query's ``$rules`` list."""
    return [
        {
            "claim_type": claim_type,
            "min": rule.min,
            "max": rule.max,
            "min_confidence": rule.min_confidence,
        }
        for claim_type, rule in product.eligibility_rules.items()
    ]


def farmer_exists(driver: Driver, farmer_id: str, database: str = DEFAULT_DATABASE) -> bool:
    """Return whether a farmer node with ``farmer_id`` exists."""
    with driver.session(database=database) as session:
        record = session.run(FARMER_EXISTS_QUERY, farmer_id=farmer_id).single()
        return bool(record["exists"]) if record else False


def evaluate_product(
    driver: Driver,
    farmer_id: str,
    product: FinancialProduct,
    database: str = DEFAULT_DATABASE,
) -> dict[str, Any]:
    """Evaluate one product for a farmer.

    Returns ``{"eligible": bool, "rule_breakdown": list[dict]}``. A product with
    no rules is trivially eligible (caller is expected to have confirmed the
    farmer exists). The breakdown explains each rule's outcome for the UI.
    """
    rules = _flatten_rules(product)
    if not rules:
        return {"eligible": True, "rule_breakdown": []}

    with driver.session(database=database) as session:
        record = session.run(
            EVALUATE_ELIGIBILITY_QUERY,
            farmer_id=farmer_id,
            rules=rules,
            min_trust_score=product.min_trust_score,
        ).single()

    if record is None:  # farmer node absent → nothing to match.
        return {"eligible": False, "rule_breakdown": []}

    return {"eligible": bool(record["eligible"]), "rule_breakdown": record["rule_breakdown"]}
