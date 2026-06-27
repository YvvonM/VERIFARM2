"""Read-only graph service — the security boundary for the MCP egress.

Write operations are *physically* separated from this layer two ways:

  1. The :class:`GraphReadService` interface exposes **only read methods** — there
     is no create/update/delete surface for a tool to reach, even by mistake.
  2. :class:`Neo4jReadService` runs every query inside ``session.execute_read``,
     so Neo4j itself rejects any statement that attempts a write at the
     transaction level — defence in depth behind the interface.

The concrete service is chosen by ``MCP_BACKEND`` (``mock`` default, so the server
runs with no database; ``neo4j`` for the live gold layer). Tools depend on the
injected service, never on a driver directly.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional, Protocol, runtime_checkable

from app.mcp.models import (
    ComplianceStatus,
    OrgSummary,
    ProvenanceStep,
    ProvenanceTrace,
    VerifiedClaim,
    VerifiedClaimsBundle,
)

SCHEMA_TEXT = """\
VERIFARMS GOLD LAYER — reified trust graph (read-only).

Nodes:
  (Institution {id, name, type, trust_score, is_authoritative})
  (Claim {id, claim_type, value_numeric, value_string, unit, confidence, source_id, timestamp})
  (Farmer {id, phone_number})

Edges:
  (Institution)-[:ATTESTS_TO]->(Claim)-[:BELONGS_TO]->(Farmer)
  (Institution)-[:GRANTED_ACCESS {status, basis}]->(Farmer)   // consent
  (Claim)-[:CONFLICTS_WITH]->(Claim)                          // data-quality flags

Notes:
  - A metric is a reified Claim (claim_type is a value, e.g. 'land_size_hectares',
    'credit_history', 'production_volume_kg'); two sources can disagree.
  - "Verified" = an authoritative source (is_authoritative=true) OR a high-reputation
    one (trust_score >= 0.7) attests to the claim.
  - This boundary is READ-ONLY: no writes are possible through the MCP server.
"""


def _tier(trust_score: float, authoritative: bool) -> str:
    if authoritative:
        return "authoritative"
    if trust_score >= 0.7:
        return "trusted"
    if trust_score >= 0.4:
        return "provisional"
    return "unverified"


@runtime_checkable
class GraphReadService(Protocol):
    """Read-only contract — intentionally has NO write methods."""

    async def get_verified_claims(self, org_id: str) -> VerifiedClaimsBundle: ...
    async def trace_provenance(self, claim_id: str) -> Optional[ProvenanceTrace]: ...
    async def check_compliance(self, entity_name: str) -> ComplianceStatus: ...
    async def org_summary(self, org_id: str) -> Optional[OrgSummary]: ...


# ---------------------------------------------------------------------------
# Mock implementation — deterministic sample data; no database required.
# ---------------------------------------------------------------------------

_MOCK_ORGS = {
    "ORG-TEGEMEO": {"name": "Tegemeo Cereals", "type": "Cooperative", "trust": 0.65, "auth": False},
    "SAT-SENTINEL2": {"name": "Sentinel-2 NDVI Cross-Check", "type": "Satellite", "trust": 1.0, "auth": True},
}
_MOCK_CLAIMS = {
    "ORG-TEGEMEO": [
        VerifiedClaim(claim_id="claim_demo_1", claim_type="land_size_hectares", value_numeric=2.4,
                      unit="ha", confidence=0.8, attested_by_id="ORG-TEGEMEO", attested_by="Tegemeo Cereals",
                      attested_by_trust=0.65, authoritative=False, observed_at="2026-06-01T00:00:00Z"),
        VerifiedClaim(claim_id="claim_demo_2", claim_type="credit_history", value_numeric=712.0,
                      confidence=0.85, attested_by_id="ORG-TEGEMEO", attested_by="Tegemeo Cereals",
                      attested_by_trust=0.65, authoritative=False, observed_at="2026-06-01T00:00:00Z"),
    ],
}


class MockReadService:
    async def get_verified_claims(self, org_id: str) -> VerifiedClaimsBundle:
        claims = _MOCK_CLAIMS.get(org_id, [])
        return VerifiedClaimsBundle(org_id=org_id, count=len(claims), claims=claims)

    async def trace_provenance(self, claim_id: str) -> Optional[ProvenanceTrace]:
        if claim_id != "claim_demo_1":
            return None
        return ProvenanceTrace(
            claim_id=claim_id, claim_type="land_size_hectares",
            attested_by_id="ORG-TEGEMEO", attested_by="Tegemeo Cereals",
            source_system="tegemeo_cereals:registry", observed_at="2026-06-01T00:00:00Z",
            authoritative=False,
            lineage=[
                ProvenanceStep(stage="source_system", actor="tegemeo_cereals:registry", detail="Original record."),
                ProvenanceStep(stage="attestation", actor="ORG-TEGEMEO", detail="Attested via ATTESTS_TO."),
                ProvenanceStep(stage="subject", actor="F-0001", detail="Claim BELONGS_TO this farmer."),
            ],
        )

    async def check_compliance(self, entity_name: str) -> ComplianceStatus:
        for oid, o in _MOCK_ORGS.items():
            if entity_name in (oid, o["name"]):
                return ComplianceStatus(
                    entity_name=entity_name, entity_id=oid, found=True,
                    tier=_tier(o["trust"], o["auth"]), trust_score=o["trust"],
                    verified=o["auth"] or o["trust"] >= 0.7, notes="mock data",
                )
        return ComplianceStatus(entity_name=entity_name, found=False, tier="unverified", notes="No matching entity.")

    async def org_summary(self, org_id: str) -> Optional[OrgSummary]:
        o = _MOCK_ORGS.get(org_id)
        if not o:
            return None
        return OrgSummary(
            org_id=org_id, name=o["name"], type=o["type"], trust_score=o["trust"],
            authoritative=o["auth"], tier=_tier(o["trust"], o["auth"]),
            claim_count=len(_MOCK_CLAIMS.get(org_id, [])),
        )


# ---------------------------------------------------------------------------
# Neo4j implementation — READ TRANSACTIONS ONLY (no write surface at all).
# ---------------------------------------------------------------------------

_CLAIMS_Q = """
MATCH (i:Institution {id: $org_id})-[:ATTESTS_TO]->(c:Claim)-[:BELONGS_TO]->(f:Farmer)
RETURN c.id AS claim_id, c.claim_type AS claim_type, c.value_numeric AS value_numeric,
       c.value_string AS value_string, c.unit AS unit, c.confidence AS confidence,
       toString(c.timestamp) AS observed_at, i.id AS attested_by_id, i.name AS attested_by,
       coalesce(i.trust_score,0.0) AS attested_by_trust, coalesce(i.is_authoritative,false) AS authoritative
ORDER BY c.claim_type
"""
_PROV_Q = """
MATCH (i:Institution)-[:ATTESTS_TO]->(c:Claim {id: $claim_id})-[:BELONGS_TO]->(f:Farmer)
RETURN c.claim_type AS claim_type, c.source_id AS source_system, toString(c.timestamp) AS observed_at,
       i.id AS attested_by_id, i.name AS attested_by, coalesce(i.is_authoritative,false) AS authoritative,
       f.id AS farmer_id
LIMIT 1
"""
_COMPLIANCE_Q = """
MATCH (i:Institution) WHERE i.id = $name OR i.name = $name
RETURN i.id AS id, i.name AS name, coalesce(i.trust_score,0.0) AS trust,
       coalesce(i.is_authoritative,false) AS auth
LIMIT 1
"""
_SUMMARY_Q = """
MATCH (i:Institution {id: $org_id})
OPTIONAL MATCH (i)-[:ATTESTS_TO]->(c:Claim)
RETURN i.name AS name, i.type AS type, coalesce(i.trust_score,0.0) AS trust,
       coalesce(i.is_authoritative,false) AS auth, count(c) AS claim_count
"""


class Neo4jReadService:
    def __init__(self, driver, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    def _read_sync(self, cypher: str, **params):
        # execute_read ⇒ Neo4j refuses any write in this transaction (boundary).
        def work(tx):
            return [r.data() for r in tx.run(cypher, **params)]
        with self._driver.session(database=self._database) as session:
            return session.execute_read(work)

    async def _read(self, cypher: str, **params):
        return await asyncio.to_thread(self._read_sync, cypher, **params)

    async def get_verified_claims(self, org_id: str) -> VerifiedClaimsBundle:
        rows = await self._read(_CLAIMS_Q, org_id=org_id)
        return VerifiedClaimsBundle(org_id=org_id, count=len(rows), claims=[VerifiedClaim(**r) for r in rows])

    async def trace_provenance(self, claim_id: str) -> Optional[ProvenanceTrace]:
        rows = await self._read(_PROV_Q, claim_id=claim_id)
        if not rows:
            return None
        r = rows[0]
        lineage = [
            ProvenanceStep(stage="source_system", actor=r.get("source_system") or "unknown", detail="Original record."),
            ProvenanceStep(stage="attestation", actor=r["attested_by_id"], detail="Attested via ATTESTS_TO."),
            ProvenanceStep(stage="subject", actor=r.get("farmer_id") or "?", detail="Claim BELONGS_TO this farmer."),
        ]
        return ProvenanceTrace(
            claim_id=claim_id, claim_type=r["claim_type"], attested_by_id=r["attested_by_id"],
            attested_by=r.get("attested_by"), source_system=r.get("source_system"),
            observed_at=r.get("observed_at"), authoritative=r["authoritative"], lineage=lineage,
        )

    async def check_compliance(self, entity_name: str) -> ComplianceStatus:
        rows = await self._read(_COMPLIANCE_Q, name=entity_name)
        if not rows:
            return ComplianceStatus(entity_name=entity_name, found=False, tier="unverified", notes="No matching entity.")
        r = rows[0]
        return ComplianceStatus(
            entity_name=entity_name, entity_id=r["id"], found=True,
            tier=_tier(r["trust"], r["auth"]), trust_score=r["trust"],
            verified=r["auth"] or r["trust"] >= 0.7,
        )

    async def org_summary(self, org_id: str) -> Optional[OrgSummary]:
        rows = await self._read(_SUMMARY_Q, org_id=org_id)
        if not rows or rows[0].get("name") is None:
            return None
        r = rows[0]
        return OrgSummary(
            org_id=org_id, name=r["name"], type=r.get("type"), trust_score=r["trust"],
            authoritative=r["auth"], tier=_tier(r["trust"], r["auth"]), claim_count=r["claim_count"],
        )


def get_read_service() -> GraphReadService:
    """Dependency injection point — choose the read-only backend (no write impl exists)."""
    if os.environ.get("MCP_BACKEND", "mock").lower() == "neo4j":
        from app.database.neo4j_client import get_driver
        return Neo4jReadService(get_driver())
    return MockReadService()
