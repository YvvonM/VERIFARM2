"""Cooperative onboarding — the cooperative-first verification entry point.

A cooperative already knows its members: delivery records, membership
history, land estimates, seasonal patterns. When it onboards to VeriFarm,
those existing member records become pre-verified Claims about its
farmers — the farmer never self-verifies; the cooperative attests, the
lender queries (see ``GET /api/v1/lender/eligible-farmers``).

``POST /api/v1/cooperative/onboard`` is the cooperative's front door: it turns
a spreadsheet-shaped member list into lender-accessible farmer profiles in one
call, all the way through the existing Silver gateway (validation + DLQ).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver
from pydantic import BaseModel, Field

from app.api.security import rate_limit, require_api_key
from app.database import consent as consent_db
from app.database.graph_ingestion import GraphIngestionService
from app.database.neo4j_client import get_shared_driver
from app.ingestion.gateway import process_incoming_batch
from app.models.consent import ConsentScope

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/cooperative",
    tags=["cooperative"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)

# A farmer with at least this many distinct verified claim_types is reported
# as "eligible" in the onboarding summary -- a simple completeness heuristic,
# distinct from (and upstream of) a specific product's real eligibility rules
# in app.database.match_engine.evaluate_product, which this endpoint never
# touches or duplicates.
MIN_CLAIM_TYPES_FOR_MATCH_ELIGIBILITY = 1


# ---------------------------------------------------------------------------
# Request / response contracts.
# ---------------------------------------------------------------------------


class MemberClaim(BaseModel):
    """One attested fact about a member, in the existing reified Claim shape."""

    claim_type: str = Field(..., min_length=1, description="e.g. 'land_size_hectares'.")
    value_numeric: Optional[float] = None
    value_string: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class CooperativeMember(BaseModel):
    """One row of the cooperative's member spreadsheet."""

    farmer_id: str = Field(..., min_length=1)
    phone_number: Optional[str] = None
    claims: list[MemberClaim] = Field(..., min_length=1)


class CooperativeOnboardRequest(BaseModel):
    """A cooperative's batch onboarding submission — the existing PayloadBundle
    shape (institution + farmer + claims), one bundle per member."""

    institution_id: str = Field(..., min_length=1, description="Stable cooperative id.")
    institution_name: str = Field(..., min_length=1)
    members: list[CooperativeMember] = Field(..., min_length=1)
    consent_scope: ConsentScope = Field(
        default=ConsentScope.CATEGORY,
        description="Default access scope for the standing [:GRANTED_ACCESS] grant — "
        "CATEGORY means any lender may query these farmers unless a farmer later "
        "narrows it to SINGLE_INSTITUTION.",
    )


class CooperativeOnboardSummary(BaseModel):
    institution_id: str
    members_submitted: int
    members_ingested: int = Field(..., description="Members whose claims passed validation and were written.")
    members_dlq: int = Field(..., description="Members quarantined to the Dead-Letter Queue.")
    claims_written: int
    members_eligible_for_match: list[str] = Field(
        ..., description="Farmer ids with enough verified claims to enter the MATCH engine."
    )


# ---------------------------------------------------------------------------
# Endpoint.
# ---------------------------------------------------------------------------


@router.post("/onboard", response_model=CooperativeOnboardSummary, status_code=201)
async def onboard_cooperative(
    payload: CooperativeOnboardRequest,
    driver: Driver = Depends(get_shared_driver),
) -> CooperativeOnboardSummary:
    """Turn a cooperative's member list into lender-accessible farmer profiles.

    Every claim is force-stamped ``source_category: cooperative`` regardless of
    what the caller sent (a cooperative submission is, by definition, a
    cooperative attestation) and the existing ``method: cooperative_attestation``
    provenance tag, then run through the Silver gateway (Pydantic validation +
    DLQ) exactly like any other ingestion path. Passing claims are written via
    the single reified writer, and each onboarded farmer gets a standing
    ``[:GRANTED_ACCESS {basis: 'COLLECTION'}]`` grant — the cooperative already
    has the farmer's consent from collection time.
    """
    raw_bundles: list[dict[str, Any]] = [
        {
            "institution": {
                "institution_id": payload.institution_id,
                "name": payload.institution_name,
                "type": "Cooperative",
                "is_authoritative": False,
                "consent_at_source": True,
                "can_originate_claims": True,
            },
            "farmer": {"farmer_id": member.farmer_id, "phone_number": member.phone_number},
            "claims": [
                {
                    "claim_type": claim.claim_type,
                    "value_numeric": claim.value_numeric,
                    "value_string": claim.value_string,
                    "unit": claim.unit,
                    "confidence": claim.confidence,
                    "source_id": f"{payload.institution_id}:cooperative_attestation",
                    # Forced regardless of caller input -- see docstring above.
                    "source_category": "cooperative",
                }
                for claim in member.claims
            ],
        }
        for member in payload.members
    ]

    validated = await run_in_threadpool(process_incoming_batch, raw_bundles)
    dlq_count = len(payload.members) - len(validated)

    claims_written = 0
    eligible: list[str] = []
    if validated:
        def _ingest_and_check() -> tuple[int, list[str]]:
            svc = GraphIngestionService(driver=driver)
            svc.ensure_constraints()
            written = svc.ingest_payload_bundles(validated)

            farmer_ids = [b.farmer.farmer_id for b in validated]
            eligible_ids: list[str] = []
            with driver.session() as session:
                rows = session.run(
                    """
                    UNWIND $farmer_ids AS fid
                    MATCH (f:Farmer {id: fid})<-[:BELONGS_TO]-(c:Claim)
                    WITH fid, count(DISTINCT c.claim_type) AS n
                    WHERE n >= $min_types
                    RETURN fid
                    """,
                    farmer_ids=farmer_ids,
                    min_types=MIN_CLAIM_TYPES_FOR_MATCH_ELIGIBILITY,
                ).data()
            eligible_ids = [r["fid"] for r in rows]
            return written, eligible_ids

        claims_written, eligible = await run_in_threadpool(_ingest_and_check)

        # Standing collection-time access grant -- the cooperative already has
        # consent from when it originally collected these member records.
        await run_in_threadpool(
            consent_db.register_source_consent,
            driver,
            payload.institution_id,
            [b.farmer.farmer_id for b in validated],
            payload.institution_name,
            payload.consent_scope.value,
        )

    logger.info(
        "Cooperative %s onboarded: %d/%d member(s) ingested, %d to DLQ, %d claim(s) written.",
        payload.institution_id, len(validated), len(payload.members), dlq_count, claims_written,
    )

    return CooperativeOnboardSummary(
        institution_id=payload.institution_id,
        members_submitted=len(payload.members),
        members_ingested=len(validated),
        members_dlq=dlq_count,
        claims_written=claims_written,
        members_eligible_for_match=eligible,
    )
