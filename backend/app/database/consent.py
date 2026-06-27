"""Consent / data-access-control graph layer.

Schema
------
A ``(:DataAccessRequest)`` node is the **audit record** of one lender asking to
see one farmer's data::

    (i:Institution)-[:REQUESTED_ACCESS]->(r:DataAccessRequest {
        request_id, status, scope, requested_at, resolved_at
    })-[:TO_FARMER]->(f:Farmer)

``status`` moves PENDING → APPROVED | DENIED. The request node is never deleted;
it is the history of who asked for what, when, and how the farmer responded.

Separately, an active grant is the **capability edge**::

    (i:Institution)-[:GRANTED_ACCESS {status, request_id, granted_at, scope}]->(f:Farmer)

It exists *only* while access is actually granted: created on APPROVED, deleted
on DENIED. The read path checks for this edge — so revoking consent (a denial)
removes the edge and immediately re-locks the data. Presence of the edge is the
authorization; the node is the paper trail.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)


CONSENT_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT data_access_request_id IF NOT EXISTS "
    "FOR (r:DataAccessRequest) REQUIRE r.request_id IS UNIQUE",
]


def apply_consent_constraints(driver: Driver, database: str = DEFAULT_DATABASE) -> None:
    """Apply consent uniqueness constraints (idempotent)."""
    with driver.session(database=database) as session:
        for statement in CONSENT_CONSTRAINTS:
            session.run(statement)
    logger.info("Applied %d consent constraint(s).", len(CONSENT_CONSTRAINTS))


# The farmer must exist (you cannot request access to nobody); the institution is
# MERGE'd so a first-time lender is registered as it makes its first request.
CREATE_REQUEST_QUERY = """
MATCH (f:Farmer {id: $farmer_id})
MERGE (i:Institution {id: $institution_id})
  ON CREATE SET i.name = $institution_id
CREATE (r:DataAccessRequest {
    request_id:   $request_id,
    status:       'PENDING',
    scope:        $scope,
    purpose:      $purpose,
    requested_at: datetime(),
    resolved_at:  null
})
CREATE (i)-[:REQUESTED_ACCESS]->(r)
CREATE (r)-[:TO_FARMER]->(f)
RETURN r.request_id              AS request_id,
       i.id                      AS institution_id,
       f.id                      AS farmer_id,
       r.status                  AS status,
       r.scope                   AS scope,
       toString(r.requested_at)  AS requested_at
"""


# Resolve flips the audit node's status, then reconciles the capability edge:
# any prior grant for this (institution, farmer) is removed first (clean revoke
# / refresh), and a fresh GRANTED_ACCESS edge is created only on APPROVED.
RESOLVE_REQUEST_QUERY = """
MATCH (i:Institution)-[:REQUESTED_ACCESS]->
      (r:DataAccessRequest {request_id: $request_id})-[:TO_FARMER]->(f:Farmer)
WHERE ($farmer_id IS NULL OR f.id = $farmer_id)
SET r.status = $status, r.resolved_at = datetime()
WITH i, r, f
// Reconcile the capability edge. Remove any prior grant first so a DENIED
// resolution revokes access; then, on APPROVED, MERGE a fresh grant edge.
OPTIONAL MATCH (i)-[old:GRANTED_ACCESS]->(f)
DELETE old
WITH i, r, f
FOREACH (_ IN CASE WHEN $status = 'APPROVED' THEN [1] ELSE [] END |
    MERGE (i)-[g:GRANTED_ACCESS]->(f)
    SET g.status     = 'APPROVED',
        g.request_id = r.request_id,
        g.scope      = r.scope,
        g.granted_at = datetime()
)
WITH i, r, f
OPTIONAL MATCH (i)-[g:GRANTED_ACCESS]->(f)
RETURN r.request_id             AS request_id,
       i.id                     AS institution_id,
       f.id                     AS farmer_id,
       r.status                 AS status,
       toString(r.resolved_at)  AS resolved_at,
       g IS NOT NULL            AS access_granted
"""


def create_access_request(
    driver: Driver,
    request_id: str,
    institution_id: str,
    farmer_id: str,
    scope: str,
    purpose: Optional[str] = None,
    database: str = DEFAULT_DATABASE,
) -> Optional[dict[str, Any]]:
    """Create a PENDING access request. Returns ``None`` if the farmer is unknown.

    ``scope`` is one of ``app.models.consent.ConsentScope``'s values."""
    with driver.session(database=database) as session:
        record = session.run(
            CREATE_REQUEST_QUERY,
            request_id=request_id,
            institution_id=institution_id,
            farmer_id=farmer_id,
            scope=scope,
            purpose=purpose,
        ).single()
        return record.data() if record else None


def resolve_access_request(
    driver: Driver,
    request_id: str,
    status: str,
    farmer_id: Optional[str] = None,
    database: str = DEFAULT_DATABASE,
) -> Optional[dict[str, Any]]:
    """Approve or deny a request. Returns ``None`` if no matching request exists."""
    with driver.session(database=database) as session:
        record = session.run(
            RESOLVE_REQUEST_QUERY,
            request_id=request_id,
            status=status,
            farmer_id=farmer_id,
        ).single()
        return record.data() if record else None


# Collection-time consent for institutions that already obtained the farmer's
# consent when the data was gathered (e.g. an external registry/database). No
# request/resolve handshake is needed — we provision the standing grant directly.
# Only farmers that exist in the graph are granted (the UNWIND+MATCH skips others).
REGISTER_SOURCE_CONSENT_QUERY = """
MERGE (i:Institution {id: $institution_id})
  ON CREATE SET i.name = coalesce($institution_name, $institution_id)
SET i.consent_at_source = true
WITH i
UNWIND $farmer_ids AS fid
MATCH (f:Farmer {id: fid})
MERGE (i)-[g:GRANTED_ACCESS]->(f)
SET g.status     = 'APPROVED',
    g.basis      = 'COLLECTION',
    g.scope      = $scope,
    g.granted_at = coalesce(g.granted_at, datetime())
RETURN count(f) AS granted
"""


def register_source_consent(
    driver: Driver,
    institution_id: str,
    farmer_ids: list[str],
    institution_name: Optional[str] = None,
    scope: str = "category",
    database: str = DEFAULT_DATABASE,
) -> int:
    """Provision standing collection-time grants; returns how many farmers matched.

    ``scope`` is one of ``app.models.consent.ConsentScope``'s values; defaults to
    ``category`` (e.g. any lender may read a cooperative-onboarded farmer)."""
    if not farmer_ids:
        return 0
    with driver.session(database=database) as session:
        record = session.run(
            REGISTER_SOURCE_CONSENT_QUERY,
            institution_id=institution_id,
            farmer_ids=farmer_ids,
            institution_name=institution_name,
            scope=scope,
        ).single()
        return int(record["granted"]) if record else 0
