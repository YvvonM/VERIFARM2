"""Read-side aggregation queries for the Loan Officer Dashboard.

A single Cypher round-trip pulls a farmer, every claim about them, and each
claim's attesting institution, then assembles the ``verified_history`` map
*in the database* (``apoc.map.fromPairs``) keyed by ``claim_type`` — so the API
layer does almost no post-processing and the payload is dashboard-ready.

Within each ``claim_type`` list, attestations are ordered authoritative-first,
then by descending institution reputation (``trust_score``) — so the strongest
evidence for any metric is always element ``[0]``.

Reified direction: ``(:Farmer)<-[:BELONGS_TO]-(:Claim)<-[:ATTESTS_TO]-(:Institution)``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)


# Shared tail: from a bound farmer `f`, fan out to claims+institutions, sort,
# group into [claim_type, [ClaimDetail, ...]] pairs, and project the final map.
# apoc.map.fromPairs turns the dynamic claim_type keys into a real map — which a
# plain Cypher map literal cannot do (its keys must be static).
_AGGREGATION_TAIL = """
OPTIONAL MATCH (f)<-[:BELONGS_TO]-(c:Claim)<-[:ATTESTS_TO]-(i:Institution)
WITH f, c, i
ORDER BY coalesce(i.is_authoritative, false) DESC,
         coalesce(i.trust_score, 0.0)        DESC
WITH f, c.claim_type AS claim_type, collect(
       CASE WHEN c IS NULL THEN null ELSE {
         value_numeric:    c.value_numeric,
         confidence:       c.confidence,
         source_name:      coalesce(i.name, i.id),
         is_authoritative: coalesce(i.is_authoritative, false),
         reputation_score: i.trust_score
       } END
     ) AS details
WITH f, claim_type, [d IN details WHERE d IS NOT NULL] AS details
WITH f, collect(
       CASE WHEN claim_type IS NULL THEN null ELSE [claim_type, details] END
     ) AS pairs
WITH f, [p IN pairs WHERE p IS NOT NULL] AS pairs
RETURN {
  farmer_id:        f.id,
  phone_number:     f.phone_number,
  verified_history: apoc.map.fromPairs(pairs)
} AS profile
"""

GET_VERIFIED_HISTORY_QUERY = "MATCH (f:Farmer {id: $farmer_id})\n" + _AGGREGATION_TAIL


def get_verified_history(
    driver: Driver,
    farmer_id: str,
    database: str = DEFAULT_DATABASE,
) -> Optional[dict[str, Any]]:
    """Return the verified-history map for a farmer, or ``None`` if absent."""
    with driver.session(database=database) as session:
        record = session.run(GET_VERIFIED_HISTORY_QUERY, farmer_id=farmer_id).single()
        return record["profile"] if record else None


# ---------------------------------------------------------------------------
# Consent-gated variant (responsible-data-access enforcement).
#
# Identical aggregation, but it MUST first traverse an APPROVED [:GRANTED_ACCESS]
# edge from the *requesting* institution to the farmer. The gate is basis-
# agnostic: an edge from an explicit USSD approval and one provisioned from
# collection-time consent both have status='APPROVED', so either unlocks the
# read. No approved grant → the opening MATCH yields nothing → zero rows → no
# claim data ever leaves the database. Denying consent deletes that edge (see
# app.database.consent), re-locking access.
# ---------------------------------------------------------------------------

GATED_VERIFIED_HISTORY_QUERY = (
    "// === CONSENT GATE — no APPROVED [:GRANTED_ACCESS], no data. ===\n"
    "MATCH (req:Institution {id: $institution_id})"
    "-[:GRANTED_ACCESS {status: 'APPROVED'}]->(f:Farmer {id: $farmer_id})\n"
    + _AGGREGATION_TAIL
)


def get_verified_history_gated(
    driver: Driver,
    institution_id: str,
    farmer_id: str,
    database: str = DEFAULT_DATABASE,
) -> Optional[dict[str, Any]]:
    """Consent-enforced read.

    Returns the profile map only when ``institution_id`` holds an APPROVED
    ``[:GRANTED_ACCESS]`` edge to ``farmer_id``; otherwise ``None`` (the caller
    maps that to HTTP 403 — access not consented).
    """
    with driver.session(database=database) as session:
        record = session.run(
            GATED_VERIFIED_HISTORY_QUERY,
            institution_id=institution_id,
            farmer_id=farmer_id,
        ).single()
        return record["profile"] if record else None
