"""
VeriFarm — Farmer REST API (refactored v3)
==========================================
Uses shared neo4j_client and scoring modules.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.neo4j_client import run_query, run_write
from app.services.scoring import (
    compute_risk_score,
    compute_completeness,
    compute_risk_factors,
    compute_completeness_reasons,
    compute_status_reason,
    compute_status,
    compute_offers,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/farmers", tags=["farmers"])


def _claim_to_verification(claim: dict[str, Any]) -> dict[str, Any]:
    """Map a Neo4j Claim node to the shape App.tsx expects.

    ``method`` here is the attesting institution's ``source_category`` (the
    reified model has no Claim.method / self_reported — see
    app.schemas.graph_schema.SOURCE_CATEGORIES).
    """
    claim_type = claim.get("claim_type", "")
    method = claim.get("method") or "none"
    confidence = claim.get("confidence", 0.0)
    org_name = claim.get("org_name") or "—"

    type_label_map = {
        "identity": "Identity",
        "land_size_hectares": "Land Size",
        "production_volume": "Production Volume",
        "credit_history": "Credit History",
    }
    label = type_label_map.get(claim_type, claim_type.replace("_", " ").title())

    if confidence >= 0.7:
        status = "Verified"
    elif confidence >= 0.4:
        status = "Pending"
    else:
        status = "Unverified"

    source_category_label_map = {
        "remote_sensing": "Satellite Imagery",
        "government": "Government Registry",
        "off_taker": "Off-taker Records",
        "cooperative": "Cooperative-reported",
        "field_officer": "Field Officer",
    }
    source = source_category_label_map.get(method, org_name if org_name != "—" else method)

    return {
        "id": claim.get("id"),
        "type": label,
        "claim_type": claim_type,
        "status": status,
        "confidence": confidence,
        "source": source,
        "method": method,
        "value": claim.get("value"),
        "date": str(claim.get("date") or ""),
        "conflictsWithIds": claim.get("conflictsWithIds") or [],
    }


def _shape_claims_preserving_conflicts(raw_claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep ALL conflicting claims; keep only best non-conflicting claim per type."""
    verifications = [_claim_to_verification(c) for c in raw_claims]

    by_type: dict[str, list[dict]] = {}
    for v in verifications:
        by_type.setdefault(v["claim_type"], []).append(v)

    final: list[dict] = []
    for claim_type, group in by_type.items():
        has_conflict = any(v["conflictsWithIds"] for v in group)
        if has_conflict:
            final.extend(group)
        else:
            best = max(group, key=lambda v: v["confidence"])
            final.append(best)

    return final


def _shape_farmer(record: dict[str, Any]) -> dict[str, Any]:
    raw_claims = [c for c in (record.get("claims") or []) if c.get("claim_type")]
    final_verifications = _shape_claims_preserving_conflicts(raw_claims)

    present_types = {v["claim_type"] for v in final_verifications}
    core_types = [
        ("identity", "Identity"),
        ("land_size_hectares", "Land Size"),
        ("production_volume", "Production Volume"),
        ("credit_history", "Credit History"),
    ]
    for ct, label in core_types:
        if ct not in present_types:
            final_verifications.append({
                "id": None, "type": label, "claim_type": ct,
                "status": "Unverified", "confidence": 0.0,
                "source": "—", "method": "none", "value": None,
                "date": "", "conflictsWithIds": [],
            })

    risk_score = compute_risk_score(raw_claims)
    completeness = compute_completeness(raw_claims)
    risk_factors = compute_risk_factors(raw_claims)
    completeness_reasons = compute_completeness_reasons(final_verifications)

    size_ha = record.get("size_hectares")
    farm_size_str = f"{size_ha} ha" if size_ha else "Unknown"

    has_unresolved_conflict = any(v["conflictsWithIds"] for v in final_verifications)
    status = compute_status(risk_score, has_unresolved_conflict)
    status_reason = compute_status_reason(status, risk_score, has_unresolved_conflict, final_verifications)

    base = {
        "id": record.get("id"), "name": record.get("name"),
        "crop": record.get("primary_crop") or "Mixed",
        "cooperative": record.get("cooperative") or "Independent",
        "size_hectares": size_ha, "riskScore": risk_score,
    }
    offers = compute_offers(base, raw_claims)

    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "phone": record.get("phone"),
        "location": record.get("location"),
        "country": record.get("country"),
        "verified": record.get("verified", False),
        "consent_signed": record.get("consent_signed", False),
        "cooperative": record.get("cooperative") or "Independent",
        "crop": record.get("primary_crop") or "Mixed",
        "farmSize": farm_size_str,
        "size_hectares": size_ha,
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "riskScore": risk_score,
        "completeness": completeness,
        "status": status,
        "statusReason": status_reason,
        "verifications": final_verifications,
        "completenessReasons": completeness_reasons,
        "riskFactors": risk_factors,
        "offers": offers,
    }


# Claim shape is rebuilt for the App.tsx-facing helpers below: `method` is
# derived from the attesting institution's reified `source_category` (no more
# Claim.method / Organization.org_role from the old gold-layer shape), and
# `value` is whichever of value_numeric/value_string is populated.
LIST_FARMERS_CYPHER = """
MATCH (f:Farmer)
OPTIONAL MATCH (fh:FarmHolding)<-[:OWNS]-(f)
OPTIONAL MATCH (f)<-[:BELONGS_TO]-(c:Claim)<-[:ATTESTS_TO]-(i:Institution)
OPTIONAL MATCH (c)-[:CONFLICTS_WITH]-(conflict:Claim)
WITH f, fh, c, i, collect(DISTINCT conflict.id) AS conflict_ids
WITH f, fh,
     collect(DISTINCT {
         id: c.id,
         claim_type: c.claim_type,
         confidence: c.confidence,
         method: c.source_category,
         value: coalesce(c.value_string, toString(c.value_numeric)),
         date: toString(c.timestamp),
         org_name: i.name,
         conflictsWithIds: conflict_ids
     }) AS claims
RETURN
    f.id AS id, f.name AS name, f.phone AS phone,
    f.location AS location, f.country AS country,
    f.verified AS verified, f.consent_signed AS consent_signed,
    fh.size_hectares AS size_hectares,
    fh.latitude AS latitude, fh.longitude AS longitude,
    claims
ORDER BY f.name
"""

SEARCH_FARMER_CYPHER = """
MATCH (f:Farmer)
WHERE toLower(f.name) CONTAINS toLower($name)
OPTIONAL MATCH (fh:FarmHolding)<-[:OWNS]-(f)
OPTIONAL MATCH (f)<-[:BELONGS_TO]-(c:Claim)<-[:ATTESTS_TO]-(i:Institution)
OPTIONAL MATCH (c)-[:CONFLICTS_WITH]-(conflict:Claim)
WITH f, fh, c, i, collect(DISTINCT conflict.id) AS conflict_ids
WITH f, fh,
     collect(DISTINCT {
         id: c.id,
         claim_type: c.claim_type,
         confidence: c.confidence,
         method: c.source_category,
         value: coalesce(c.value_string, toString(c.value_numeric)),
         date: toString(c.timestamp),
         org_name: i.name,
         conflictsWithIds: conflict_ids
     }) AS claims
RETURN
    f.id AS id, f.name AS name, f.phone AS phone,
    f.location AS location, f.country AS country,
    f.verified AS verified, f.consent_signed AS consent_signed,
    fh.size_hectares AS size_hectares,
    fh.latitude AS latitude, fh.longitude AS longitude,
    claims
LIMIT 10
"""

GET_FARMER_CYPHER = """
MATCH (f:Farmer {id: $farmer_id})
OPTIONAL MATCH (fh:FarmHolding)<-[:OWNS]-(f)
OPTIONAL MATCH (cc:CropCycle)<-[:HAS_CYCLE]-(fh)
OPTIONAL MATCH (f)-[:MEMBER_OF]->(coop:Organization)
OPTIONAL MATCH (f)<-[:BELONGS_TO]-(c:Claim)<-[:ATTESTS_TO]-(i:Institution)
OPTIONAL MATCH (c)-[:CONFLICTS_WITH]-(conflict:Claim)
WITH f, fh, coop, cc, c, i, collect(DISTINCT conflict.id) AS conflict_ids
WITH f, fh, coop,
     collect(DISTINCT {
         id: c.id,
         claim_type: c.claim_type,
         confidence: c.confidence,
         method: c.source_category,
         value: coalesce(c.value_string, toString(c.value_numeric)),
         date: toString(c.timestamp),
         org_name: i.name,
         org_role: i.type,
         org_reputation: i.trust_score,
         conflictsWithIds: conflict_ids
     }) AS claims,
     collect(DISTINCT cc.crop_type)[0] AS primary_crop,
     collect(DISTINCT cc.harvest_estimate_tons) AS harvests
RETURN
    f.id AS id, f.name AS name, f.phone AS phone,
    f.location AS location, f.country AS country,
    f.verified AS verified, f.consent_signed AS consent_signed,
    fh.size_hectares AS size_hectares,
    fh.latitude AS latitude, fh.longitude AS longitude,
    coop.name AS cooperative,
    primary_crop, harvests, claims
"""


@router.get("")
async def list_farmers() -> list[dict[str, Any]]:
    records = await run_query(LIST_FARMERS_CYPHER)
    return [_shape_farmer(r) for r in records]


@router.get("/search")
async def search_farmers(name: str = Query(..., min_length=1)) -> dict[str, Any]:
    records = await run_query(SEARCH_FARMER_CYPHER, {"name": name})
    if records:
        return {"found": True, "farmers": [_shape_farmer(r) for r in records]}
    return {"found": False, "query": name}


@router.get("/{farmer_id}")
async def get_farmer(farmer_id: str) -> dict[str, Any]:
    records = await run_query(GET_FARMER_CYPHER, {"farmer_id": farmer_id})
    if not records:
        raise HTTPException(status_code=404, detail=f"Farmer {farmer_id!r} not found")
    return _shape_farmer(records[0])