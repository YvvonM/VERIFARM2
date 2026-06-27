"""
VeriFarm — Farmer Onboarding & Verification API
================================================

Endpoints:
  POST /api/onboarding/register
  GET  /api/onboarding/{phone}/status
  POST /api/onboarding/{phone}/verify-identity
  POST /api/onboarding/{phone}/verify-land
  POST /api/onboarding/{phone}/verify-production
  POST /api/onboarding/{phone}/verify-credit
  POST /api/onboarding/{phone}/resolve-conflict

Writes the reified model only: ``(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)``.
A figure with no qualifying external source (the farmer's own self-report) is
stored as a ``(:PendingClaim {status: 'unverified'})`` — it is never a verified
Claim and is never read by trust traversal (see app.schemas.graph_schema).
``Farmer.verified`` is recomputed here as a CACHED CONVENIENCE FLAG only; the
actual eligibility/trust decision always re-derives from Claim/Institution.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.neo4j_client import run_query, run_write
from app.services.scoring import (
    compute_risk_score,
    compute_completeness,
    compute_risk_factors,
    compute_completeness_reasons,
    compute_status_reason,
    compute_status,
    compute_offers,
    CORE_CLAIM_TYPES,
)
from app.services.earth_engine import check_land_size
from app.models.schemas import (
    FarmerRegisterRequest,
    IdentityVerifyRequest,
    LandVerifyRequest,
    ProductionVerifyRequest,
    CreditVerifyRequest,
    ConflictResolveRequest,
    OnboardingStatusResponse,
)

# Mock providers
from app.data_generation.synthetic_providers.identity_mock import verify_identity
from app.data_generation.synthetic_providers.credit_mock import check_credit_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

# Institutions this router attests through. Government/satellite are
# authoritative ground-truth sources; "verifarm" is the platform itself,
# granted universal standing access to farmers it registers directly.
GOV_IDENTITY_INSTITUTION_ID = "ORG-GOV-IDENTITY"
SATELLITE_INSTITUTION_ID = "ORG-SENTINEL2"
CREDIT_BUREAU_INSTITUTION_ID = "ORG-CREDIT-BUREAU"
PLATFORM_INSTITUTION_ID = "verifarm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_claim_id() -> str:
    return f"claim_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_farmer_claims(phone: str) -> list[dict]:
    """Fetch all verified Claims for a farmer (PendingClaims are excluded —
    they are not verified and must never be treated as such)."""
    cypher = """
    MATCH (f:Farmer {id: $phone})
    OPTIONAL MATCH (f)<-[:BELONGS_TO]-(c:Claim)<-[:ATTESTS_TO]-(i:Institution)
    OPTIONAL MATCH (c)-[:CONFLICTS_WITH]-(conflict:Claim)
    OPTIONAL MATCH (c)<-[:CONFLICTS_WITH]-(pending:PendingClaim)
    WITH c, i, collect(DISTINCT conflict.id) + collect(DISTINCT pending.id) AS conflict_ids
    RETURN collect(DISTINCT {
        id: c.id,
        claim_type: c.claim_type,
        confidence: c.confidence,
        source_category: c.source_category,
        value: coalesce(c.value_string, toString(c.value_numeric)),
        date: toString(c.timestamp),
        source: i.name,
        conflictsWithIds: conflict_ids
    }) AS claims
    """
    records = await run_query(cypher, {"phone": phone})
    claims = records[0]["claims"] if records else []
    return [c for c in claims if c.get("claim_type")]


async def _recompute_and_update(phone: str) -> dict[str, Any]:
    """Recompute scores and update farmer node.

    ``f.verified`` is set here as a CACHED CONVENIENCE FLAG only (e.g. for fast
    list-view rendering) — it is never read back as the source of truth for
    trust traversal or product eligibility; those always re-derive from
    Claim/Institution directly (see app.database.match_engine).
    """
    claims = await _get_farmer_claims(phone)
    risk_score = compute_risk_score(claims)
    completeness = compute_completeness(claims)
    has_conflict = any(c.get("conflictsWithIds") for c in claims)
    status = compute_status(risk_score, has_conflict)

    await run_write("""
    MATCH (f:Farmer {id: $phone})
    SET f.risk_score = $risk_score,
        f.completeness = $completeness,
        f.status = $status,
        f.verified = $verified,
        f.updated_at = $now
    """, {
        "phone": phone, "risk_score": risk_score,
        "completeness": completeness, "status": status,
        "verified": completeness == 100 and not has_conflict,
        "now": _now_iso(),
    })

    return {
        "risk_score": risk_score,
        "completeness": completeness,
        "status": status,
        "has_conflict": has_conflict,
        "claims": claims,
    }


def _build_status_response(phone: str, name: str, result: dict) -> OnboardingStatusResponse:
    claims = result["claims"]
    completed = {c["claim_type"] for c in claims if c.get("claim_type")}
    pending = [ct for ct in CORE_CLAIM_TYPES if ct not in completed]

    # Build verifications shape for scoring helpers
    verifications = []
    for c in claims:
        if not c.get("claim_type"):
            continue
        status = "Verified" if c.get("confidence", 0) >= 0.7 else "Pending" if c.get("confidence", 0) >= 0.4 else "Unverified"
        verifications.append({
            **c, "status": status,
            "conflictsWithIds": c.get("conflictsWithIds") or [],
        })

    status_reason_obj = compute_status_reason(result["status"], result["risk_score"], result["has_conflict"], verifications)
    status_reason = status_reason_obj.get("description", "") if status_reason_obj else ""
    offers = compute_offers(
        {"id": phone, "name": name, "riskScore": result["risk_score"], "size_hectares": 0, "crop": "Mixed", "cooperative": "Independent"},
        claims,
    )

    return OnboardingStatusResponse(
        farmer_id=phone,
        name=name,
        current_step="complete" if not pending else pending[0],
        completed_steps=list(completed),
        pending_steps=pending,
        has_conflicts=result["has_conflict"],
        risk_score=result["risk_score"],
        completeness=result["completeness"],
        status=result["status"],
        status_reason=status_reason,
        offers=offers,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register")
async def register_farmer(req: FarmerRegisterRequest) -> dict[str, Any]:
    """Register a new farmer and record consent."""
    # Check if farmer exists
    existing = await run_query("MATCH (f:Farmer {id: $phone}) RETURN f.id AS id", {"phone": req.phone})
    if existing:
        raise HTTPException(status_code=409, detail=f"Farmer with phone {req.phone} already exists")

    # Create farmer
    await run_write("""
    CREATE (f:Farmer {
        id: $phone,
        name: $name,
        phone: $phone,
        country: $country,
        location: $location,
        verified: false,
        consent_signed: $consent,
        created_at: $now,
        updated_at: $now
    })
    """, {
        "phone": req.phone, "name": req.name, "country": req.country,
        "location": req.location, "consent": req.consent, "now": _now_iso(),
    })

    # Standing access grant for the platform itself, scoped universal (any
    # lender the farmer later approves still goes through the consent API —
    # this only covers the platform's own onboarding/operational reads).
    if req.consent:
        await run_write("""
        MATCH (f:Farmer {id: $phone})
        MERGE (i:Institution {id: $institution_id})
          ON CREATE SET i.name = "VeriFarm Platform", i.is_authoritative = false,
                        i.trust_score = 1.0, i.can_originate_claims = false
        MERGE (i)-[g:GRANTED_ACCESS]->(f)
        SET g.status = "APPROVED",
            g.basis = "REQUEST",
            g.scope = "universal",
            g.granted_at = $now
        """, {"phone": req.phone, "institution_id": PLATFORM_INSTITUTION_ID, "now": _now_iso()})

    return {
        "farmer_id": req.phone,
        "message": "Farmer registered successfully.",
        "next_step": "identity",
    }


@router.get("/{phone}/status")
async def get_status(phone: str) -> OnboardingStatusResponse:
    """Get current onboarding progress for a farmer."""
    farmer = await run_query("MATCH (f:Farmer {id: $phone}) RETURN f.name AS name", {"phone": phone})
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    result = await _recompute_and_update(phone)
    return _build_status_response(phone, farmer[0]["name"], result)


@router.post("/{phone}/verify-identity")
async def verify_identity_step(phone: str, req: IdentityVerifyRequest) -> dict[str, Any]:
    """Step 1: Verify identity via mock NIBSS/NIMC (government, authoritative)."""
    farmer = await run_query("MATCH (f:Farmer {id: $phone}) RETURN f.name AS name, f.country AS country", {"phone": phone})
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    # Call mock identity provider
    id_result = verify_identity(
        country=farmer[0]["country"],
        claimed_name=farmer[0]["name"],
        identifier=req.national_id,
    )

    claim_id = _gen_claim_id()
    await run_write("""
    MATCH (f:Farmer {id: $phone})
    MERGE (i:Institution {id: $institution_id})
      ON CREATE SET i.name = $provider, i.is_authoritative = true,
                    i.trust_score = 1.0, i.can_originate_claims = true,
                    i.minimum_onboarding_trust = 1.0
    CREATE (c:Claim {
        id: $claim_id,
        claim_type: "identity",
        value_string: $verified_name,
        source_category: "government",
        confidence: $confidence,
        timestamp: datetime($now)
    })
    CREATE (i)-[:ATTESTS_TO]->(c)
    CREATE (c)-[:BELONGS_TO]->(f)
    """, {
        "phone": phone, "claim_id": claim_id,
        "institution_id": GOV_IDENTITY_INSTITUTION_ID,
        "verified_name": id_result.verified_name,
        "confidence": id_result.confidence,
        "provider": id_result.provider,
        "now": _now_iso(),
    })

    result = await _recompute_and_update(phone)
    return {
        "step": "identity",
        "status": "completed",
        "claim_id": claim_id,
        "verified_name": id_result.verified_name,
        "confidence": id_result.confidence,
        "next_step": "land",
        "message": f"Identity verified with {round(id_result.confidence*100)}% confidence.",
    }


@router.post("/{phone}/verify-land")
async def verify_land_step(phone: str, req: LandVerifyRequest) -> dict[str, Any]:
    """Step 2: Self-reported land size (PendingClaim, unverified) + optional
    satellite cross-check (Claim, attested by the remote-sensing institution)."""
    farmer = await run_query("MATCH (f:Farmer {id: $phone}) RETURN f.name AS name, f.location AS location", {"phone": phone})
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    # The farmer's own figure has no qualifying external source -- it is a
    # PendingClaim, not a verified Claim, and is invisible to trust traversal.
    self_claim_id = _gen_claim_id()
    await run_write("""
    MATCH (f:Farmer {id: $phone})
    CREATE (p:PendingClaim {
        id: $claim_id,
        claim_type: "land_size_hectares",
        value_numeric: $value,
        status: "unverified",
        submitted_at: $now
    })
    CREATE (p)-[:BELONGS_TO]->(f)
    SET f.size_hectares = $size_ha
    """, {
        "phone": phone, "claim_id": self_claim_id,
        "value": req.self_reported_hectares,
        "size_ha": req.self_reported_hectares,
        "now": _now_iso(),
    })

    conflict_created = False
    sat_claim_id = None
    sat_result = None

    # Satellite cross-check
    if req.use_satellite and req.latitude and req.longitude:
        sat_result = check_land_size(
            latitude=req.latitude,
            longitude=req.longitude,
            self_reported_hectares=req.self_reported_hectares,
        )

        if sat_result.get("detected_ha") is not None:
            sat_claim_id = _gen_claim_id()
            await run_write("""
            MATCH (f:Farmer {id: $phone})
            MERGE (i:Institution {id: $institution_id})
              ON CREATE SET i.name = "Sentinel-2 NDVI Cross-Check", i.is_authoritative = true,
                            i.trust_score = 1.0, i.can_originate_claims = true,
                            i.minimum_onboarding_trust = 1.0
            CREATE (c:Claim {
                id: $claim_id,
                claim_type: "land_size_hectares",
                value_numeric: $value,
                source_category: "remote_sensing",
                confidence: $confidence,
                timestamp: datetime($now)
            })
            CREATE (i)-[:ATTESTS_TO]->(c)
            CREATE (c)-[:BELONGS_TO]->(f)
            """, {
                "phone": phone, "claim_id": sat_claim_id,
                "institution_id": SATELLITE_INSTITUTION_ID,
                "value": sat_result["detected_ha"],
                "confidence": sat_result["confidence"],
                "now": _now_iso(),
            })

            # Create conflict if discrepancy > 30% -- recorded between the
            # PendingClaim and the verified satellite Claim, for officer
            # review; the PendingClaim itself still never enters trust reads.
            if sat_result.get("discrepancy_pct", 0) > 30:
                conflict_created = True
                await run_write("""
                MATCH (p:PendingClaim {id: $self_id}), (c:Claim {id: $sat_id})
                CREATE (p)-[:CONFLICTS_WITH]->(c)
                """, {"self_id": self_claim_id, "sat_id": sat_claim_id})

    result = await _recompute_and_update(phone)
    return {
        "step": "land",
        "status": "conflict" if conflict_created else "completed",
        "self_reported_claim_id": self_claim_id,
        "satellite_claim_id": sat_claim_id,
        "satellite_detected_ha": sat_result.get("detected_ha") if sat_result else None,
        "discrepancy_pct": sat_result.get("discrepancy_pct") if sat_result else None,
        "next_step": "production",
        "message": "Land size recorded." + (" Satellite cross-check found a significant discrepancy — manual review required." if conflict_created else ""),
    }


@router.post("/{phone}/verify-production")
async def verify_production_step(phone: str, req: ProductionVerifyRequest) -> dict[str, Any]:
    """Step 3: Record production estimate as a PendingClaim — a bare farmer
    self-estimate has no external source and is never a verified Claim."""
    farmer = await run_query("MATCH (f:Farmer {id: $phone}) RETURN f.name AS name", {"phone": phone})
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    claim_id = _gen_claim_id()
    await run_write("""
    MATCH (f:Farmer {id: $phone})
    CREATE (p:PendingClaim {
        id: $claim_id,
        claim_type: "production_volume",
        value_string: $value,
        status: "unverified",
        submitted_at: $now
    })
    CREATE (p)-[:BELONGS_TO]->(f)
    SET f.crop = $crop_type
    """, {
        "phone": phone, "claim_id": claim_id,
        "value": f"{req.estimated_tons} tons ({req.season})",
        "crop_type": req.crop_type,
        "now": _now_iso(),
    })

    result = await _recompute_and_update(phone)
    return {
        "step": "production",
        "status": "completed",
        "claim_id": claim_id,
        "next_step": "credit",
        "message": f"Production estimate of {req.estimated_tons} tons recorded (pending — needs a cooperative/off-taker attestation to verify).",
    }


@router.post("/{phone}/verify-credit")
async def verify_credit_step(phone: str, req: CreditVerifyRequest) -> dict[str, Any]:
    """Step 4: Credit bureau check (government/authoritative source)."""
    farmer = await run_query("MATCH (f:Farmer {id: $phone}) RETURN f.name AS name, f.country AS country", {"phone": phone})
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    if not req.consent_for_credit_check:
        raise HTTPException(status_code=400, detail="Consent required for credit check")

    # Call mock credit provider
    credit_result = check_credit_history(
        country=farmer[0]["country"],
        identifier=phone,
    )

    claim_id = _gen_claim_id()
    await run_write("""
    MATCH (f:Farmer {id: $phone})
    MERGE (i:Institution {id: $institution_id})
      ON CREATE SET i.name = $provider, i.is_authoritative = true,
                    i.trust_score = 1.0, i.can_originate_claims = true,
                    i.minimum_onboarding_trust = 1.0
    CREATE (c:Claim {
        id: $claim_id,
        claim_type: "credit_history",
        value_string: $value,
        source_category: "government",
        confidence: $confidence,
        timestamp: datetime($now)
    })
    CREATE (i)-[:ATTESTS_TO]->(c)
    CREATE (c)-[:BELONGS_TO]->(f)
    """, {
        "phone": phone, "claim_id": claim_id,
        "institution_id": CREDIT_BUREAU_INSTITUTION_ID,
        "value": f"score={credit_result.credit_score};default_flag={credit_result.has_default_flag}",
        "confidence": credit_result.confidence,
        "provider": credit_result.provider,
        "now": _now_iso(),
    })

    result = await _recompute_and_update(phone)
    status_resp = _build_status_response(phone, farmer[0]["name"], result)

    return {
        "step": "credit",
        "status": "completed",
        "claim_id": claim_id,
        "credit_score": credit_result.credit_score,
        "has_default": credit_result.has_default_flag,
        "next_step": None,
        "message": f"Credit check complete. Score: {credit_result.credit_score}.",
        "final_status": status_resp.status,
        "risk_score": status_resp.risk_score,
        "completeness": status_resp.completeness,
        "offers": status_resp.offers,
    }


@router.post("/{phone}/resolve-conflict")
async def resolve_conflict(phone: str, req: ConflictResolveRequest) -> dict[str, Any]:
    """Officer resolves a conflicting claim."""
    # Verify the keep claim exists and belongs to this farmer (it may be a
    # Claim or a PendingClaim -- either label can be the kept side).
    claim_check = await run_query("""
    MATCH (c)-[:BELONGS_TO]->(f:Farmer {id: $phone})
    WHERE (c:Claim OR c:PendingClaim) AND c.id = $claim_id
    RETURN c.id AS id
    """, {"claim_id": req.keep_claim_id, "phone": phone})
    if not claim_check:
        raise HTTPException(status_code=404, detail="Claim not found for this farmer")

    # Remove CONFLICTS_WITH edges for the kept claim
    await run_write("""
    MATCH (c {id: $claim_id})-[r:CONFLICTS_WITH]-()
    WHERE c:Claim OR c:PendingClaim
    DELETE r
    """, {"claim_id": req.keep_claim_id})

    # Optionally archive/demote other claims
    for archive_id in req.archive_claim_ids:
        await run_write("""
        MATCH (c {id: $archive_id})
        WHERE c:Claim OR c:PendingClaim
        SET c.archived = true,
            c.archived_at = $now,
            c.archived_reason = "resolved_in_favor_of_" + $keep_id
        """, {"archive_id": archive_id, "keep_id": req.keep_claim_id, "now": _now_iso()})

    result = await _recompute_and_update(phone)
    return {
        "resolved": True,
        "kept_claim_id": req.keep_claim_id,
        "archived_claim_ids": req.archive_claim_ids,
        "new_status": result["status"],
        "new_risk_score": result["risk_score"],
    }
