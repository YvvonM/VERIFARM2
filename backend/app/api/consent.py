"""Farmer Consent API — data-access control.

Two endpoints implement the handshake that makes the farmer the gatekeeper of
their own data:

  * ``POST /api/v1/consent/request`` — a lender raises a PENDING request.
  * ``POST /api/v1/consent/resolve`` — the (simulated USSD) farmer interface
    approves or denies it, creating or removing the active access grant.

The actual read enforcement lives in
:func:`app.database.profile_queries.get_verified_history_gated`, whose query
refuses to return any claim data without an APPROVED ``[:GRANTED_ACCESS]`` edge.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver

from app.api.security import rate_limit, require_api_key
from app.database import consent as consent_db
from app.database.neo4j_client import get_shared_driver
from app.models.consent import (
    AccessRequestPayload,
    AccessRequestResponse,
    ConsentResolutionPayload,
    ConsentResolutionResponse,
    SourceConsentPayload,
    SourceConsentResponse,
)

logger = logging.getLogger(__name__)

# Auth + rate limit: consent grants/resolutions are sensitive mutations.
router = APIRouter(
    prefix="/api/v1/consent",
    tags=["consent"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


@router.post("/request", response_model=AccessRequestResponse, status_code=201)
async def request_access(
    payload: AccessRequestPayload,
    driver: Driver = Depends(get_shared_driver),
) -> AccessRequestResponse:
    """A lender requests access to a farmer's profile (creates a PENDING node).

    Returns 404 if the farmer does not exist. The request is recorded but grants
    nothing until the farmer approves it.
    """
    request_id = str(uuid4())
    result = await run_in_threadpool(
        consent_db.create_access_request,
        driver,
        request_id,
        payload.institution_id,
        payload.farmer_id,
        payload.scope.value,
        payload.purpose,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown farmer_id {payload.farmer_id!r}.")

    logger.info(
        "Consent request %s: %r → %r (scope=%s) PENDING.",
        request_id, payload.institution_id, payload.farmer_id, payload.scope,
    )
    return AccessRequestResponse(**result)


@router.post("/resolve", response_model=ConsentResolutionResponse)
async def resolve_access(
    payload: ConsentResolutionPayload,
    driver: Driver = Depends(get_shared_driver),
) -> ConsentResolutionResponse:
    """The farmer (via USSD/SMS) approves or denies a pending request.

    APPROVED merges the active ``[:GRANTED_ACCESS]`` edge; DENIED removes any
    existing grant. Returns 404 if no matching request exists (or it does not
    target ``farmer_id`` when that guard is supplied).
    """
    result = await run_in_threadpool(
        consent_db.resolve_access_request,
        driver,
        str(payload.request_id),
        payload.status.value,
        payload.farmer_id,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No resolvable request {payload.request_id!s} for the given farmer.",
        )

    logger.info(
        "Consent request %s resolved %s; access_granted=%s.",
        payload.request_id, result["status"], result["access_granted"],
    )
    return ConsentResolutionResponse(**result)


@router.post("/source-grant", response_model=SourceConsentResponse, status_code=201)
async def register_source_consent(
    payload: SourceConsentPayload,
    driver: Driver = Depends(get_shared_driver),
) -> SourceConsentResponse:
    """Register collection-time consent for an institution over a set of farmers.

    Use this for data sources where the farmer already consented when the data was
    collected — those institutions get a standing ``[:GRANTED_ACCESS]`` edge and
    never need the request/resolve handshake. Only farmers that already exist in
    the graph are granted; the response reports matched vs. submitted counts.
    """
    granted = await run_in_threadpool(
        consent_db.register_source_consent,
        driver,
        payload.institution_id,
        payload.farmer_ids,
        payload.institution_name,
        payload.scope.value,
    )
    logger.info(
        "Source consent for %r: granted %d/%d farmer(s).",
        payload.institution_id, granted, len(payload.farmer_ids),
    )
    return SourceConsentResponse(
        institution_id=payload.institution_id,
        granted=granted,
        requested=len(payload.farmer_ids),
    )
