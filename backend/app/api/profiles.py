"""Loan Officer Dashboard API — transparent risk profiling.

``GET /api/v1/profiles/{farmer_id}/verified-history`` returns a farmer's full
verification history: what is verified, by whom, at what confidence, and from
which source — collapsing a multi-week manual diligence process into a single
read. Ground-truth sources are flagged (``is_authoritative``) so the UI can
visually separate authoritative evidence from self-reported claims.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver

from app.api.security import rate_limit, require_api_key
from app.database.neo4j_client import get_shared_driver
from app.database.profile_queries import get_verified_history
from app.models.profiles import FarmerProfileResponse

logger = logging.getLogger(__name__)

# Auth + rate limit: profile reads expose a farmer's verified history.
router = APIRouter(
    prefix="/api/v1/profiles",
    tags=["profiles"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


@router.get("/{farmer_id}/verified-history", response_model=FarmerProfileResponse)
async def verified_history(
    farmer_id: str,
    driver: Driver = Depends(get_shared_driver),
) -> FarmerProfileResponse:
    """Return the aggregated verified history for one farmer.

    Responds 404 when no farmer node exists for ``farmer_id``. The blocking
    Neo4j read runs in a worker thread so the event loop stays responsive.
    """
    profile = await run_in_threadpool(get_verified_history, driver, farmer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown farmer_id {farmer_id!r}.")

    # Unpack the Cypher map projection defensively — never assume a key is present.
    verified_history = profile.get("verified_history") or {}
    logger.info(
        "Served verified history for farmer %r (%d claim type(s)).",
        farmer_id, len(verified_history),
    )
    return FarmerProfileResponse(
        farmer_id=profile.get("farmer_id", farmer_id),
        phone_number=profile.get("phone_number"),
        verified_history=verified_history,
    )
