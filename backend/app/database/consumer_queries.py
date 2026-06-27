"""Gold-layer Cypher for the Farmer-view and Macro consumer routes.

Both queries are written to avoid Cartesian explosions:

  * the farmer view evaluates "who has access" and "what is verified" in two
    *independent* ``CALL {}`` subqueries, so grants and claims are never matched
    in the same pattern (which would multiply rows);
  * the macro stats collapse the portfolio to a DISTINCT set of members first,
    then test each member with cheap ``EXISTS {}`` subqueries rather than
    expanding multiple OPTIONAL MATCH patterns into a product.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Route 2 — Data Owner (Farmer View).
#
# A claim_type is "Verified" iff at least one ATTESTING institution is
# authoritative (ground truth); otherwise "Unverified". Confidence decimals are
# never surfaced. The two CALL subqueries keep grants and claims in separate
# pattern scopes — no grant×claim Cartesian product.
# ---------------------------------------------------------------------------

MY_DATA_QUERY = """
MATCH (f:Farmer {id: $farmer_id})
CALL {
    WITH f
    OPTIONAL MATCH (viewer:Institution)-[g:GRANTED_ACCESS]->(f)
    RETURN collect(
        CASE WHEN viewer IS NULL THEN null ELSE {
            institution: coalesce(viewer.name, viewer.id),
            basis:       coalesce(g.basis, 'EXPLICIT'),
            since:       toString(g.granted_at)
        } END
    ) AS shares
}
CALL {
    WITH f
    OPTIONAL MATCH (src:Institution)-[:ATTESTS_TO]->(c:Claim)-[:BELONGS_TO]->(f)
    WITH c.claim_type AS claim_type, collect(DISTINCT src) AS sources
    WITH claim_type,
         any(s IN sources WHERE coalesce(s.is_authoritative, false)) AS verified
    WHERE claim_type IS NOT NULL
    RETURN collect({
        claim_type: claim_type,
        status:     CASE WHEN verified THEN 'Verified' ELSE 'Unverified' END
    }) AS claims
}
RETURN {
    farmer_id:    f.id,
    phone_number: f.phone_number,
    shared_with:  [s IN shares WHERE s IS NOT NULL],
    claims:       claims
} AS mydata
"""


def get_my_data(
    driver: Driver,
    farmer_id: str,
    database: str = DEFAULT_DATABASE,
) -> Optional[dict[str, Any]]:
    """Return the farmer's own plain-language data view, or ``None`` if absent."""
    with driver.session(database=database) as session:
        record = session.run(MY_DATA_QUERY, farmer_id=farmer_id).single()
        return record["mydata"] if record else None


# ---------------------------------------------------------------------------
# Route 3 — Macro Consumer (Analytics View). Fully anonymized.
#
# Portfolio = farmers this institution has attested about. We collapse them to a
# DISTINCT set, then per member use EXISTS {} subqueries for the boolean flags
# and a scoped OPTIONAL MATCH for the verified hectares. The UNWIND CASE keeps a
# single null row for an empty portfolio so the institution still reports zeros.
# Output is pure aggregate — no farmer_id, no phone_number ever leaves the DB.
# ---------------------------------------------------------------------------

COOP_STATS_QUERY = """
MATCH (inst:Institution {id: $institution_id})
OPTIONAL MATCH (inst)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(f:Farmer)
WITH inst, collect(DISTINCT f) AS members
WITH inst, [x IN members WHERE x IS NOT NULL] AS members
// Average trust score across every institution attesting about this
// portfolio's farmers (including this institution itself) -- an additive
// aggregate alongside the existing anonymized member-count metrics below.
CALL {
    WITH members
    UNWIND (CASE WHEN size(members) = 0 THEN [null] ELSE members END) AS m
    OPTIONAL MATCH (attestor:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(m)
    RETURN avg(coalesce(attestor.trust_score, 0.0)) AS average_trust_score
}
UNWIND (CASE WHEN size(members) = 0 THEN [null] ELSE members END) AS m
// Best authoritative land figure for this member (NULL if none / no member).
OPTIONAL MATCH (auth:Institution)-[:ATTESTS_TO]->
              (lc:Claim {claim_type: 'land_size_hectares'})-[:BELONGS_TO]->(m)
    WHERE coalesce(auth.is_authoritative, false)
WITH inst, m, average_trust_score, max(lc.value_numeric) AS verified_ha
WITH inst, m, average_trust_score, verified_ha,
     (m IS NOT NULL AND EXISTS {
         MATCH (a:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(m)
         WHERE coalesce(a.is_authoritative, false)
     }) AS has_authoritative,
     (m IS NOT NULL AND EXISTS {
         MATCH (:Institution)-[:ATTESTS_TO]->
               (:Claim {claim_type: 'credit_history'})-[:BELONGS_TO]->(m)
     }) AS has_credit_history
WITH inst, average_trust_score,
     count(m)                                                              AS total_members,
     sum(coalesce(verified_ha, 0.0))                                       AS total_verified_hectares,
     sum(CASE WHEN m IS NOT NULL AND NOT has_authoritative  THEN 1 ELSE 0 END) AS unverified_members,
     sum(CASE WHEN m IS NOT NULL AND NOT has_credit_history THEN 1 ELSE 0 END) AS missing_credit_history_count
RETURN {
    institution_id:               inst.id,
    total_members:                total_members,
    total_verified_hectares:      total_verified_hectares,
    unverified_members:           unverified_members,
    missing_credit_history_count: missing_credit_history_count,
    average_trust_score:          round(coalesce(average_trust_score, 0.0), 4)
} AS stats
"""


def get_cooperative_stats(
    driver: Driver,
    institution_id: str,
    database: str = DEFAULT_DATABASE,
) -> Optional[dict[str, Any]]:
    """Return anonymized portfolio stats for an institution, or ``None`` if absent."""
    with driver.session(database=database) as session:
        record = session.run(COOP_STATS_QUERY, institution_id=institution_id).single()
        return record["stats"] if record else None
