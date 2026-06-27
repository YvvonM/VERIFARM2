"""Reified-graph ingestion + conflict analytics over the official neo4j driver.

:class:`GraphIngestionService` is the single write/analytics surface for the
:class:`~app.models.reified.PayloadBundle` contract. It writes the reified
pattern idempotently::

    (i:Institution)-[:ATTESTS_TO]->(c:Claim)<-[:BELONGS_TO]-(f:Farmer)

and exposes the payoff query — :meth:`detect_conflicts` — which surfaces
non-authoritative claims that materially contradict an authoritative
(ground-truth) source for the same farmer and metric.

Topology, constraint names and labels match :mod:`app.database.trust_graph`, so
the two modules operate on one consistent graph rather than forking it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE, get_driver
from app.database.trust_graph import DEFAULT_TRUST_SCORE

logger = logging.getLogger(__name__)


# Idempotent uniqueness constraints. Names are identical to trust_graph's so the
# two modules share constraints instead of colliding ("equivalent constraint
# already exists" is avoided because IF NOT EXISTS + same name is a no-op).
CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT institution_id IF NOT EXISTS "
    "FOR (i:Institution) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT claim_id IF NOT EXISTS "
    "FOR (c:Claim) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT trust_farmer_id IF NOT EXISTS "
    "FOR (f:Farmer) REQUIRE f.id IS UNIQUE",
    # claim_type is a value, not a key — so it earns a real index that the
    # traversal/conflict queries ride on.
    "CREATE INDEX claim_type_idx IF NOT EXISTS FOR (c:Claim) ON (c.claim_type)",
    "CREATE INDEX institution_authoritative_idx IF NOT EXISTS "
    "FOR (i:Institution) ON (i.is_authoritative)",
]


# ---------------------------------------------------------------------------
# Ingestion. One parameterized statement; UNWIND drives the batch.
# ---------------------------------------------------------------------------
#
# $bundles is a list of {institution, farmer, claims:[...]}. Outer UNWIND
# streams the bundles; the inner UNWIND streams each bundle's claims. Every node
# and relationship is MERGE'd (never CREATE'd), so re-ingesting the same payload
# updates in place — the whole batch is idempotent.
# ---------------------------------------------------------------------------

INGEST_BUNDLES_CYPHER = """
UNWIND $bundles AS bundle
MERGE (i:Institution {id: bundle.institution.institution_id})
  // Seed reputation once, on first sight; reputation scoring owns it thereafter.
  // A non-authoritative institution is capped at minimum_onboarding_trust on
  // first sight, regardless of what initial_trust_score it requests -- a fresh
  // cooperative cannot just declare itself highly trusted; it must be
  // corroborated by an authoritative source first.
  ON CREATE SET i.trust_score = CASE
        WHEN bundle.institution.is_authoritative THEN coalesce(bundle.institution.initial_trust_score, 1.0)
        ELSE apoc.coll.min([
          coalesce(bundle.institution.initial_trust_score, $default_trust),
          coalesce(bundle.institution.minimum_onboarding_trust, $default_trust)
        ])
      END
  SET i.name                     = bundle.institution.name,
      i.is_authoritative         = bundle.institution.is_authoritative,
      i.type                     = bundle.institution.type,
      i.consent_at_source        = coalesce(bundle.institution.consent_at_source, false),
      i.can_originate_claims     = coalesce(bundle.institution.can_originate_claims, false),
      i.minimum_onboarding_trust = coalesce(bundle.institution.minimum_onboarding_trust, $default_trust)
MERGE (f:Farmer {id: bundle.farmer.farmer_id})
  SET f.phone_number = bundle.farmer.phone_number
WITH i, f, bundle
// Collection-time consent: the farmer already consented to this institution when
// the data was gathered, so provision a standing grant — no request/resolve needed.
FOREACH (_ IN CASE WHEN coalesce(bundle.institution.consent_at_source, false)
                   THEN [1] ELSE [] END |
    MERGE (i)-[ga:GRANTED_ACCESS]->(f)
    SET ga.status     = 'APPROVED',
        ga.basis      = 'COLLECTION',
        ga.granted_at = coalesce(ga.granted_at, datetime())
)
WITH i, f, bundle
UNWIND bundle.claims AS claim
MERGE (c:Claim {id: claim.claim_id})
  SET c.claim_type      = claim.claim_type,
      c.value_numeric   = claim.value_numeric,
      c.value_string    = claim.value_string,
      c.unit            = claim.unit,
      c.source_id       = claim.source_id,
      c.source_category = claim.source_category,
      c.confidence      = claim.confidence,
      c.timestamp       = datetime(claim.timestamp)
MERGE (i)-[:ATTESTS_TO]->(c)
MERGE (c)-[:BELONGS_TO]->(f)
RETURN count(c) AS claims_written
"""


# ---------------------------------------------------------------------------
# Payoff query — conflict detection against ground truth.
# ---------------------------------------------------------------------------
#
# Anchor on the authoritative claim (auth -> ac -> f), then EXPAND from the
# already-bound farmer f to its non-authoritative claims of the same type. The
# second MATCH reuses f, so this is a connected traversal — NOT a Cartesian
# product of two independent node sets. `nc.id <> ac.id` blocks a claim from
# conflicting with itself. The variance is normalized against the authoritative
# value (its denominator guarded against zero), and only deltas beyond
# $variance_threshold are returned.
# ---------------------------------------------------------------------------

DETECT_CONFLICTS_CYPHER = """
MATCH (auth:Institution)-[:ATTESTS_TO]->(ac:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f:Farmer)
WHERE auth.is_authoritative = true AND ac.value_numeric IS NOT NULL
MATCH (nonauth:Institution)-[:ATTESTS_TO]->(nc:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f)
WHERE nonauth.is_authoritative = false
  AND nc.value_numeric IS NOT NULL
  AND nc.id <> ac.id
WITH f, ac, nc, nonauth,
     abs(nc.value_numeric - ac.value_numeric) /
       (CASE WHEN ac.value_numeric = 0 THEN 1.0 ELSE abs(ac.value_numeric) END)
     AS variance
WHERE variance > $variance_threshold
RETURN f.id                     AS farmer_id,
       $claim_type              AS claim_type,
       ac.value_numeric         AS authoritative_value,
       nc.value_numeric         AS reported_value,
       nonauth.name             AS reported_by,
       nonauth.id               AS reported_by_id,
       round(variance, 4)       AS variance
ORDER BY variance DESC
"""


# ---------------------------------------------------------------------------
# Corroboration — two independent institutions agreeing on the same farmer +
# claim_type, within tolerance, are linked so trust traversal can rank
# corroborated claims above single-source ones (see app.database.trust_graph).
# Mirrors detect_conflicts' shape but flags agreement instead of variance.
# ---------------------------------------------------------------------------

CORROBORATE_CLAIMS_CYPHER = """
MATCH (i1:Institution)-[:ATTESTS_TO]->(c1:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f:Farmer)
WHERE c1.value_numeric IS NOT NULL
MATCH (i2:Institution)-[:ATTESTS_TO]->(c2:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f)
WHERE c2.value_numeric IS NOT NULL AND c2.id > c1.id AND i2.id <> i1.id
WITH c1, c2,
     abs(c2.value_numeric - c1.value_numeric) /
       (CASE WHEN c1.value_numeric = 0 THEN 1.0 ELSE abs(c1.value_numeric) END)
     AS variance
WHERE variance <= $tolerance
MERGE (c1)-[:CORROBORATED_BY]->(c2)
MERGE (c2)-[:CORROBORATED_BY]->(c1)
RETURN count(*) AS pairs_corroborated
"""


class GraphIngestionService:
    """Write reified bundles and run conflict analytics against Neo4j.

    Usable as a context manager::

        with GraphIngestionService() as svc:
            svc.ingest_bundles(rows)
            conflicts = svc.detect_conflicts("land_size_hectares", 0.20)
    """

    def __init__(
        self,
        driver: Optional[Driver] = None,
        database: str = DEFAULT_DATABASE,
    ) -> None:
        self._owns_driver = driver is None
        self._driver = driver or get_driver()
        self._database = database

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "GraphIngestionService":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the driver only if this service created it."""
        if self._owns_driver:
            self._driver.close()

    # -- schema -------------------------------------------------------------

    def ensure_constraints(self) -> None:
        """Apply uniqueness constraints + indexes (idempotent)."""
        with self._driver.session(database=self._database) as session:
            for statement in CONSTRAINTS:
                session.run(statement)
        logger.info("Applied %d constraint(s)/index(es).", len(CONSTRAINTS))

    # -- ingestion ----------------------------------------------------------

    def ingest_bundles(self, bundles: list[dict]) -> int:
        """Idempotently MERGE a batch of reified bundles; return claims written.

        ``bundles`` is the JSON-mode dump of :class:`PayloadBundle` objects
        (i.e. ``[b.model_dump(mode="json") for b in payload_bundles]``) so that
        ``claim.timestamp`` is an ISO-8601 string Cypher's ``datetime()`` accepts.
        """
        if not bundles:
            return 0
        with self._driver.session(database=self._database) as session:
            result = session.execute_write(self._write_bundles, bundles)
        logger.info("Ingested %d bundle(s); %d claim(s) written.", len(bundles), result)
        return result

    @staticmethod
    def _write_bundles(tx: Any, bundles: list[dict]) -> int:
        record = tx.run(
            INGEST_BUNDLES_CYPHER, bundles=bundles, default_trust=DEFAULT_TRUST_SCORE
        ).single()
        return int(record["claims_written"]) if record else 0

    def ingest_payload_bundles(self, bundles: list[Any]) -> int:
        """Convenience: accept :class:`PayloadBundle` objects and ingest them."""
        return self.ingest_bundles([b.model_dump(mode="json") for b in bundles])

    # -- analytics ----------------------------------------------------------

    def detect_conflicts(
        self,
        claim_type: str,
        variance_threshold: float = 0.20,
    ) -> list[dict[str, Any]]:
        """Return non-authoritative claims that contradict ground truth.

        For each farmer with both an authoritative and a non-authoritative claim
        of ``claim_type``, flags the pair when their relative variance exceeds
        ``variance_threshold`` (0.20 == 20%). Results are ordered worst-first.
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(
                DETECT_CONFLICTS_CYPHER,
                claim_type=claim_type,
                variance_threshold=variance_threshold,
            )
            return [record.data() for record in result]

    def corroborate_claims(
        self,
        claim_type: str,
        tolerance: float = 0.15,
    ) -> int:
        """Link Claims of ``claim_type`` that agree within ``tolerance`` (15% by
        default — e.g. cooperative-reported land size matching satellite land
        size) via ``[:CORROBORATED_BY]``, so trust traversal can rank them above
        single-source claims. Returns the number of pairs linked (idempotent —
        re-running on already-linked pairs is a no-op MERGE).
        """
        with self._driver.session(database=self._database) as session:
            record = session.execute_write(
                lambda tx: tx.run(
                    CORROBORATE_CLAIMS_CYPHER, claim_type=claim_type, tolerance=tolerance
                ).single()
            )
            return int(record["pairs_corroborated"]) if record else 0
