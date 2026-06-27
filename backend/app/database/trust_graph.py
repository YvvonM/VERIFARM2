"""Intent-agnostic trust graph: traversal + reputation (analytics only).

This module is the *read/analytics* half of the generalized trust layer. The
**write** path is owned exclusively by
:class:`app.database.graph_ingestion.GraphIngestionService`, which persists the
canonical reified pattern::

    (:Institution)-[:ATTESTS_TO]->(:Claim {claim_type, value_numeric, ...})-[:BELONGS_TO]->(:Farmer)

Reification is what makes the system schema-free across an unknown and growing
set of metrics: ``claim_type`` is a *value* (``'land_size_hectares'``,
``'organic_certified'``, ``'credit_history_score'``, ...), so it can be
parameterized, indexed, and cross-checked — without ever altering the schema
when a new metric or data source appears. See ``SCHEMA_NOTE`` below.

Authoritative ("ground truth") sources are flagged by ``is_authoritative = true``
on the :class:`Institution` (no separate ``:GroundTruth`` label) — the single
flag the ingestion service writes and these queries read.

Public surface:
  * :data:`VERIFY_CLAIM_QUERY`           — Part 1: intent-agnostic traversal
  * :func:`verify_claim`
  * :data:`RECALCULATE_REPUTATION_QUERY` — Part 2: generalized reputation
  * :func:`recalculate_reputation`
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)

# Default global reputation assigned to a freshly-seen institution. Shared with
# the ingestion service, which seeds Institution.trust_score from it on create.
DEFAULT_TRUST_SCORE = 0.5

# Approved provenance for a verified Claim (see app.models.reified.SourceCategory).
# Deliberately excludes "self_reported" -- a figure with no qualifying external
# source is a PendingClaim, never visible here.
APPROVED_SOURCE_CATEGORIES: list[str] = [
    "cooperative", "off_taker", "government", "remote_sensing", "field_officer",
]


# ===========================================================================
# Part 1 — Intent-agnostic traversal query.
# ===========================================================================
#
# Verify ANY metric for ANY farmer, returning the value only when it is backed
# by an institution whose *global* reputation clears $min_trust_score. Nothing
# about the metric is hardcoded: $claim_type is a parameter, matched against the
# indexed Claim.claim_type. Adding 'credit_history_score' tomorrow needs zero
# query or schema changes.
# ---------------------------------------------------------------------------

VERIFY_CLAIM_QUERY = """
MATCH (inst:Institution)
      -[:ATTESTS_TO]->(c:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f:Farmer {id: $farmer_id})
WHERE coalesce(inst.trust_score, 0.0) >= $min_trust_score
  // Hard gate: a claim is only ever surfaced here if it carries an approved,
  // external source_category. self_reported figures are PendingClaims and
  // structurally absent from this traversal -- this WHERE is the second,
  // belt-and-suspenders enforcement of that rule.
  AND c.source_category IN $approved_source_categories
OPTIONAL MATCH (c)-[:CORROBORATED_BY]->(:Claim)
WITH c, inst, count(*) > 0 AS corroborated
RETURN c.claim_type                            AS claim_type,
       c.value_string                          AS value,
       c.value_numeric                         AS value_numeric,
       c.unit                                  AS unit,
       c.source_category                       AS source_category,
       c.confidence                            AS claim_confidence,
       c.timestamp                             AS observed_at,
       inst.id                                 AS attested_by_id,
       inst.name                                AS attested_by,
       coalesce(inst.trust_score, 0.0)         AS institution_trust,
       coalesce(inst.is_authoritative, false)  AS authoritative,
       corroborated                            AS corroborated
// Corroborated-by-an-independent-source ranks above single-source, then most
// authoritative + most trusted + most recent attestation first.
ORDER BY corroborated DESC, authoritative DESC, institution_trust DESC, observed_at DESC
"""


def verify_claim(
    driver: Driver,
    farmer_id: str,
    claim_type: str,
    min_trust_score: float = 0.5,
    database: str = DEFAULT_DATABASE,
) -> list[dict[str, Any]]:
    """Return all sufficiently-trusted attestations of ``claim_type`` for a farmer.

    The first row (post-ordering) is the best-supported answer; the full list
    lets a caller show corroboration or disagreement across institutions.
    """
    with driver.session(database=database) as session:
        result = session.run(
            VERIFY_CLAIM_QUERY,
            farmer_id=farmer_id,
            claim_type=claim_type,
            min_trust_score=min_trust_score,
            approved_source_categories=APPROVED_SOURCE_CATEGORIES,
        )
        return [record.data() for record in result]


# ===========================================================================
# Part 2 — Generalized reputation scoring query.
# ===========================================================================
#
# Recompute an institution's global trust score against ground truth, with no
# data source hardcoded. "Ground truth" is any institution with
# is_authoritative = true (satellite, government registry, ...).
#
# For each claim the institution made, we look for a corresponding authoritative
# claim on the SAME farmer and the SAME claim_type, then:
#   * numeric claims  -> percentage variance vs the authoritative value;
#   * categorical/boolean claims -> exact value match.
# Agreement (variance <= $acceptable_variance_percentage, or an exact match)
# earns +$reward; disagreement earns -$penalty. The per-comparison deltas are
# AVERAGED (not summed) so the update is bounded and stable regardless of how
# many farmers the institution covers, then clamped to [0, 1].
# ---------------------------------------------------------------------------

RECALCULATE_REPUTATION_QUERY = """
MATCH (inst:Institution {id: $institution_id})
// Every claim this institution attests to (OPTIONAL so a bare institution with
// no ground-truth overlap still returns a status row and keeps its score).
OPTIONAL MATCH (inst)-[:ATTESTS_TO]->(c:Claim)-[:BELONGS_TO]->(f:Farmer)
OPTIONAL MATCH (auth:Institution)-[:ATTESTS_TO]->(truth:Claim {claim_type: c.claim_type})
               -[:BELONGS_TO]->(f)
    WHERE coalesce(auth.is_authoritative, false)
      AND auth.id <> inst.id
// Per-pairing variance (numeric) ...
WITH inst, c, truth,
     CASE
       WHEN truth IS NULL THEN null
       WHEN c.value_numeric IS NOT NULL AND truth.value_numeric IS NOT NULL
         THEN abs(c.value_numeric - truth.value_numeric) /
              (CASE WHEN truth.value_numeric = 0 THEN 1.0 ELSE abs(truth.value_numeric) END)
              * 100.0
       ELSE null
     END AS variance_pct
// ... and the resulting agreement verdict (numeric tolerance or exact match).
WITH inst, truth, variance_pct,
     CASE
       WHEN truth IS NULL THEN null
       WHEN variance_pct IS NOT NULL THEN variance_pct <= $acceptable_variance_percentage
       ELSE toLower(trim(toString(c.value_string))) = toLower(trim(toString(truth.value_string)))
     END AS within_tolerance
// Aggregate across all comparable pairs. count(truth) ignores the null rows.
WITH inst,
     count(truth)                                              AS comparisons,
     sum(CASE WHEN within_tolerance THEN 1 ELSE 0 END)         AS agreements,
     avg(variance_pct)                                         AS mean_variance_pct,
     avg(CASE WHEN truth IS NULL THEN null
              ELSE (CASE WHEN within_tolerance THEN $reward ELSE -$penalty END)
         END)                                                  AS mean_delta
// Bounded, clamped update. No ground truth -> score is left untouched.
WITH inst, comparisons, agreements, mean_variance_pct,
     CASE
       WHEN comparisons = 0 OR mean_delta IS NULL
         THEN coalesce(inst.trust_score, $default_trust)
       ELSE apoc.coll.max([0.0,
              apoc.coll.min([1.0,
                coalesce(inst.trust_score, $default_trust) + mean_delta])])
     END AS new_score
SET inst.trust_score      = new_score,
    inst.trust_updated_at = datetime(),
    inst.last_comparisons = comparisons,
    inst.last_agreements  = agreements
RETURN inst.id                              AS institution_id,
       comparisons,
       agreements,
       round(coalesce(mean_variance_pct, 0.0), 2) AS mean_variance_pct,
       round(new_score, 4)                  AS trust_score
"""


def recalculate_reputation(
    driver: Driver,
    institution_id: str,
    acceptable_variance_percentage: float = 5.0,
    reward: float = 0.05,
    penalty: float = 0.10,
    database: str = DEFAULT_DATABASE,
) -> dict[str, Any]:
    """Recompute and persist an institution's global trust score vs ground truth.

    Returns a summary: ``comparisons``, ``agreements``, ``mean_variance_pct``
    and the new ``trust_score``. Penalties are heavier than rewards by default
    so a few bad attestations cost more than they gain — tune to taste.
    """
    with driver.session(database=database) as session:
        result = session.run(
            RECALCULATE_REPUTATION_QUERY,
            institution_id=institution_id,
            acceptable_variance_percentage=acceptable_variance_percentage,
            reward=reward,
            penalty=penalty,
            default_trust=DEFAULT_TRUST_SCORE,
        )
        record = result.single()
        return record.data() if record else {}


# ---------------------------------------------------------------------------
# Part 3 — Schema advice (kept beside the code it justifies).
# ---------------------------------------------------------------------------

SCHEMA_NOTE = """\
Reify the claim. Model it as a node:

    (Institution)-[:ATTESTS_TO]->(Claim {claim_type, value_numeric, ...})-[:BELONGS_TO]->(Farmer)

NOT as properties on the [:VERIFIED_BY] edge.

Why, for THIS problem (unknown/growing claim_types and data sources):

  * Parameterization & indexing. With reification, claim_type is a VALUE, so it
    is parameterizable ($claim_type) and backed by a real index
    (CREATE INDEX FOR (c:Claim) ON (c.claim_type)). As an edge property, the
    metric is a KEY; dynamic-key access (r[$claim_type]) works but cannot use a
    schema index and degrades to a scan.
  * Per-claim provenance. Every metric carries its own confidence, unit,
    observed_at and source. On an edge you'd need parallel key families
    (land_size_value, land_size_confidence, yield_value, ...), which explodes.
  * Ground-truth cross-checking. Comparing institutional vs authoritative claims
    on the same farmer + claim_type is one clean pattern over Claim nodes.
  * Temporal history & n-ary facts. Multiple attestations of the same metric
    over time, by multiple parties, are just multiple Claim nodes / edges.
  * Zero-schema growth. A brand-new metric or data source is new DATA, never a
    migration.

Cost: one extra hop (Institution -> Claim -> Farmer) and more nodes. With the
claim_type index this is negligible, and it is dwarfed by the flexibility the
requirement demands. Watch for farmer/claim_type supernodes at very large scale
(mitigate by traversing from the indexed Claim, not by scanning a farmer's
thousands of edges).

Keep edge-properties only for a small, fixed, always-present set of attributes
that never need independent provenance or versioning.
"""
