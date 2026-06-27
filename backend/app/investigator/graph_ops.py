"""Cypher surface for the DLQ Investigator.

Three concerns, kept beside the queries that serve them:

  * **Discover** what to scan — :data:`AUTHORITATIVE_CLAIM_TYPES_CYPHER`.
  * **Investigate** — :data:`FIND_CONFLICTS_CYPHER` returns each conflict *with
    claim ids* (so specific nodes can be flagged) plus the attesting source's
    reputation and reputation-pass history in one round trip; and
    :data:`COUNT_SOURCE_CONFLICTS_CYPHER` cross-references the source's broader
    track record (how many of its claims currently contradict ground truth).
  * **Resolve** — :data:`FLAG_CONFLICT_CYPHER` writes the verdict back as a
    graph fact: a ``[:CONFLICTS_WITH]`` edge between the two claims and the
    recommendation stamped onto the reported Claim node, so a loan officer's
    query can surface "this figure is disputed" directly.

The reified topology and constraint names match
:mod:`app.database.graph_ingestion`, so the investigator reads/writes the same
graph rather than forking it.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE
from app.models.investigation import ConflictInvestigation

logger = logging.getLogger(__name__)


# Distinct claim_types that have at least one authoritative *numeric* claim —
# the only ones a variance check is meaningful for. Drives an all-types scan.
AUTHORITATIVE_CLAIM_TYPES_CYPHER = """
MATCH (i:Institution)-[:ATTESTS_TO]->(c:Claim)
WHERE i.is_authoritative = true AND c.value_numeric IS NOT NULL
RETURN DISTINCT c.claim_type AS claim_type
"""


# Conflicts for one claim_type, enriched with claim ids + the source's
# reputation and last reputation-pass counters. Connected traversal off the
# shared farmer f (not a Cartesian product); a claim never conflicts with itself.
FIND_CONFLICTS_CYPHER = """
MATCH (auth:Institution)-[:ATTESTS_TO]->(ac:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f:Farmer)
WHERE auth.is_authoritative = true AND ac.value_numeric IS NOT NULL
MATCH (nonauth:Institution)-[:ATTESTS_TO]->(nc:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f)
WHERE coalesce(nonauth.is_authoritative, false) = false
  AND nc.value_numeric IS NOT NULL
  AND nc.id <> ac.id
WITH f, ac, auth, nc, nonauth,
     abs(nc.value_numeric - ac.value_numeric) /
       (CASE WHEN ac.value_numeric = 0 THEN 1.0 ELSE abs(ac.value_numeric) END)
     AS variance
WHERE variance > $variance_threshold
RETURN f.id                                  AS farmer_id,
       $claim_type                           AS claim_type,
       ac.id                                 AS authoritative_claim_id,
       ac.value_numeric                      AS authoritative_value,
       auth.name                             AS authoritative_source,
       nc.id                                 AS reported_claim_id,
       nc.value_numeric                      AS reported_value,
       nonauth.id                            AS reported_by_id,
       nonauth.name                          AS reported_by,
       coalesce(nonauth.trust_score, 0.0)    AS source_trust_score,
       coalesce(nonauth.last_comparisons, 0) AS source_comparisons,
       coalesce(nonauth.last_agreements, 0)  AS source_agreements,
       round(variance, 4)                    AS variance
ORDER BY variance DESC
"""


# How many distinct claims by this source currently contradict ground truth,
# across every farmer and metric — the source's "rap sheet".
COUNT_SOURCE_CONFLICTS_CYPHER = """
MATCH (nonauth:Institution {id: $institution_id})-[:ATTESTS_TO]->(nc:Claim)
      -[:BELONGS_TO]->(f:Farmer)
WHERE coalesce(nonauth.is_authoritative, false) = false
  AND nc.value_numeric IS NOT NULL
MATCH (auth:Institution)-[:ATTESTS_TO]->(ac:Claim {claim_type: nc.claim_type})
      -[:BELONGS_TO]->(f)
WHERE auth.is_authoritative = true
  AND ac.value_numeric IS NOT NULL
  AND ac.id <> nc.id
WITH nc, ac,
     abs(nc.value_numeric - ac.value_numeric) /
       (CASE WHEN ac.value_numeric = 0 THEN 1.0 ELSE abs(ac.value_numeric) END)
     AS variance
WHERE variance > $variance_threshold
RETURN count(DISTINCT nc) AS prior_conflicts
"""


# Persist the verdict. Idempotent: re-running updates the flag in place.
FLAG_CONFLICT_CYPHER = """
MATCH (nc:Claim {id: $reported_claim_id})
MATCH (ac:Claim {id: $authoritative_claim_id})
MERGE (nc)-[r:CONFLICTS_WITH]->(ac)
  SET r.variance    = $variance,
      r.detected_at = datetime()
SET nc.flagged                  = true,
    nc.flag_action              = $action,
    nc.flag_severity            = $severity,
    nc.flag_confidence          = $confidence,
    nc.flag_rationale           = $rationale,
    nc.flag_authoritative_value = $authoritative_value,
    nc.flag_variance            = $variance,
    nc.flagged_at               = datetime()
RETURN nc.id AS flagged_claim_id
"""


# Read back open flags for inspection / a steward UI.
LIST_FLAGS_CYPHER = """
MATCH (nonauth:Institution)-[:ATTESTS_TO]->(nc:Claim)-[:BELONGS_TO]->(f:Farmer)
WHERE nc.flagged = true
OPTIONAL MATCH (nc)-[r:CONFLICTS_WITH]->(ac:Claim)
RETURN f.id                       AS farmer_id,
       nc.claim_type              AS claim_type,
       nc.id                      AS reported_claim_id,
       nc.value_numeric           AS reported_value,
       nc.flag_authoritative_value AS authoritative_value,
       nc.flag_variance           AS variance,
       nc.flag_action             AS action,
       nc.flag_severity           AS severity,
       nc.flag_confidence         AS confidence,
       nc.flag_rationale          AS rationale,
       toString(nc.flagged_at)    AS flagged_at,
       nonauth.id                 AS reported_by_id,
       nonauth.name               AS reported_by
ORDER BY nc.flag_variance DESC
LIMIT $limit
"""


def list_authoritative_claim_types(driver: Driver, database: str = DEFAULT_DATABASE) -> list[str]:
    """Return every claim_type that has an authoritative numeric claim to check."""
    with driver.session(database=database) as session:
        result = session.run(AUTHORITATIVE_CLAIM_TYPES_CYPHER)
        return [r["claim_type"] for r in result]


def find_conflicts(
    driver: Driver,
    claim_type: str,
    variance_threshold: float,
    database: str = DEFAULT_DATABASE,
) -> list[dict[str, Any]]:
    """Return conflicts (with claim ids + source reputation) for one claim_type."""
    with driver.session(database=database) as session:
        result = session.run(
            FIND_CONFLICTS_CYPHER,
            claim_type=claim_type,
            variance_threshold=variance_threshold,
        )
        return [r.data() for r in result]


def count_source_conflicts(
    driver: Driver,
    institution_id: str,
    variance_threshold: float,
    database: str = DEFAULT_DATABASE,
) -> int:
    """Count the source's distinct claims currently conflicting with ground truth."""
    with driver.session(database=database) as session:
        record = session.run(
            COUNT_SOURCE_CONFLICTS_CYPHER,
            institution_id=institution_id,
            variance_threshold=variance_threshold,
        ).single()
        return int(record["prior_conflicts"]) if record else 0


def flag_conflict(
    driver: Driver,
    investigation: ConflictInvestigation,
    database: str = DEFAULT_DATABASE,
) -> str | None:
    """Write the verdict to the graph; return the flagged claim id."""
    rec = investigation.recommendation
    with driver.session(database=database) as session:
        record = session.run(
            FLAG_CONFLICT_CYPHER,
            reported_claim_id=investigation.reported_claim_id,
            authoritative_claim_id=investigation.authoritative_claim_id,
            authoritative_value=investigation.authoritative_value,
            variance=investigation.variance,
            action=rec.action.value,
            severity=rec.severity.value,
            confidence=rec.confidence,
            rationale=rec.rationale,
        ).single()
        return record["flagged_claim_id"] if record else None


def list_flags(
    driver: Driver,
    limit: int = 100,
    database: str = DEFAULT_DATABASE,
) -> list[dict[str, Any]]:
    """Return the currently-flagged claims, worst variance first."""
    with driver.session(database=database) as session:
        result = session.run(LIST_FLAGS_CYPHER, limit=limit)
        return [r.data() for r in result]
