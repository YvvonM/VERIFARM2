"""Outbound export queries — let downstream systems consume the verified graph.

Read-only projections of the reified trust layer into flat, ETL-friendly rows:
each row is one attested claim with its source and trust. Filterable by
claim_type / minimum source trust / a ``since`` watermark (for incremental
downstream syncs), and keyset-free offset pagination for simplicity.

PII boundary: these projections expose verified *claims* and their attesting
institution — never the farmer's phone number — so the export is shareable with
data consumers without leaking contact details.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)


_RETURN_CLAIM = """
RETURN c.id                                AS claim_id,
       f.id                                AS farmer_id,
       c.claim_type                        AS claim_type,
       c.value_numeric                     AS value_numeric,
       c.value_string                      AS value_string,
       c.unit                              AS unit,
       c.confidence                        AS confidence,
       toString(c.timestamp)               AS timestamp,
       i.id                                AS attested_by_id,
       i.name                              AS attested_by,
       coalesce(i.trust_score, 0.0)        AS attested_by_trust,
       coalesce(i.is_authoritative, false) AS authoritative
"""

EXPORT_CLAIMS_QUERY = """
MATCH (i:Institution)-[:ATTESTS_TO]->(c:Claim)-[:BELONGS_TO]->(f:Farmer)
WHERE ($claim_type IS NULL OR c.claim_type = $claim_type)
  AND coalesce(i.trust_score, 0.0) >= $min_trust_score
  AND ($since IS NULL OR c.timestamp >= datetime($since))
""" + _RETURN_CLAIM + """
ORDER BY c.timestamp DESC, f.id, c.claim_type
SKIP $offset LIMIT $limit
"""

EXPORT_FARMER_CLAIMS_QUERY = """
MATCH (i:Institution)-[:ATTESTS_TO]->(c:Claim)-[:BELONGS_TO]->(f:Farmer {id: $farmer_id})
WHERE coalesce(i.trust_score, 0.0) >= $min_trust_score
""" + _RETURN_CLAIM + """
ORDER BY authoritative DESC, attested_by_trust DESC, c.timestamp DESC
"""


def export_claims(
    driver: Driver,
    claim_type: Optional[str] = None,
    min_trust_score: float = 0.0,
    since: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    database: str = DEFAULT_DATABASE,
) -> list[dict[str, Any]]:
    """Return a page of verified claims for downstream consumption."""
    with driver.session(database=database) as session:
        result = session.run(
            EXPORT_CLAIMS_QUERY,
            claim_type=claim_type,
            min_trust_score=min_trust_score,
            since=since,
            offset=offset,
            limit=limit,
        )
        return [record.data() for record in result]


def export_farmer_claims(
    driver: Driver,
    farmer_id: str,
    min_trust_score: float = 0.0,
    database: str = DEFAULT_DATABASE,
) -> list[dict[str, Any]]:
    """Return all verified claims for one farmer (strongest evidence first)."""
    with driver.session(database=database) as session:
        result = session.run(
            EXPORT_FARMER_CLAIMS_QUERY, farmer_id=farmer_id, min_trust_score=min_trust_score
        )
        return [record.data() for record in result]


GET_CLAIM_BY_ID_QUERY = """
MATCH (i:Institution)-[:ATTESTS_TO]->(c:Claim {id: $claim_id})-[:BELONGS_TO]->(f:Farmer)
""" + _RETURN_CLAIM + "\nLIMIT 1"


def get_claim(driver: Driver, claim_id: str, database: str = DEFAULT_DATABASE) -> Optional[dict[str, Any]]:
    """Return one claim by its id (with source/trust), or None."""
    with driver.session(database=database) as session:
        record = session.run(GET_CLAIM_BY_ID_QUERY, claim_id=claim_id).single()
        return record.data() if record else None


# Institutions ("organizations" to external consumers). ``status`` derives from
# verification strength: an authoritative or high-reputation (≥0.7) source is
# "verified", otherwise "pending".
EXPORT_INSTITUTIONS_QUERY = """
MATCH (i:Institution)
WITH i, (coalesce(i.is_authoritative, false) OR coalesce(i.trust_score, 0.0) >= 0.7) AS verified
WHERE $status = 'all'
   OR ($status = 'verified' AND verified)
   OR ($status = 'pending'  AND NOT verified)
RETURN i.id                              AS institution_id,
       i.name                            AS name,
       i.type                            AS type,
       coalesce(i.trust_score, 0.0)      AS trust_score,
       coalesce(i.is_authoritative, false) AS is_authoritative,
       verified                          AS verified
ORDER BY i.id
SKIP $offset LIMIT $limit
"""


def export_organizations(
    driver: Driver,
    status: str = "all",
    offset: int = 0,
    limit: int = 200,
    database: str = DEFAULT_DATABASE,
) -> list[dict[str, Any]]:
    """Return institutions filtered by verification status (paginated)."""
    with driver.session(database=database) as session:
        result = session.run(
            EXPORT_INSTITUTIONS_QUERY, status=status, offset=offset, limit=limit
        )
        return [record.data() for record in result]
