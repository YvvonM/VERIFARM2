"""Gold-layer consumer APIs — three purpose-shaped views over the Silver graph.

  * Route 1 — Financial consumer (loan officer): full risk profile, ground-truth
    first. Reuses the verified-history aggregation.
  * Route 2 — Data owner (farmer): plain-language statuses + who is viewing.
  * Route 3 — Macro consumer (analytics): anonymized portfolio aggregates only.

All reads run on the shared driver in a worker thread so the event loop is never
blocked, and 404 on a missing root node.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver

from app.api.security import rate_limit, require_api_key
from app.database.consumer_queries import get_cooperative_stats, get_my_data
from app.database.neo4j_client import get_shared_driver
from app.database.profile_queries import get_verified_history
from app.models.consumer import CooperativeStatsResponse, MyDataResponse
from app.models.profiles import FarmerProfileResponse

logger = logging.getLogger(__name__)

# Auth + rate limit: gold-layer reads expose verified farmer/coop data.
router = APIRouter(
    prefix="/api/v1",
    tags=["gold"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


# --- Route 1: Financial Consumer (Risk Profiling) --------------------------

@router.get("/loan-officer/farmer/{farmer_id}", response_model=FarmerProfileResponse)
async def loan_officer_view(
    farmer_id: str,
    driver: Driver = Depends(get_shared_driver),
) -> FarmerProfileResponse:
    """Full verified history for risk profiling; ground-truth at index 0 per metric."""
    profile = await run_in_threadpool(get_verified_history, driver, farmer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown farmer_id {farmer_id!r}.")
    return FarmerProfileResponse(
        farmer_id=profile.get("farmer_id", farmer_id),
        phone_number=profile.get("phone_number"),
        verified_history=profile.get("verified_history") or {},
    )


# --- Route 2: Data Owner (Farmer View) -------------------------------------

@router.get("/farmer/{farmer_id}/my-data", response_model=MyDataResponse)
async def my_data_view(
    farmer_id: str,
    driver: Driver = Depends(get_shared_driver),
) -> MyDataResponse:
    """The farmer's own view: plain-language statuses and who can see their data."""
    data = await run_in_threadpool(get_my_data, driver, farmer_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Unknown farmer_id {farmer_id!r}.")
    return MyDataResponse(
        farmer_id=data.get("farmer_id", farmer_id),
        phone_number=data.get("phone_number"),
        shared_with=data.get("shared_with") or [],
        claims=data.get("claims") or [],
    )


# --- Route 3: Macro Consumer (Analytics View) ------------------------------

@router.get("/macro/cooperative/{institution_id}/stats", response_model=CooperativeStatsResponse)
async def cooperative_stats(
    institution_id: str,
    driver: Driver = Depends(get_shared_driver),
) -> CooperativeStatsResponse:
    """Anonymized portfolio metrics for an institution — no per-farmer identifiers."""
    stats = await run_in_threadpool(get_cooperative_stats, driver, institution_id)
    if stats is None:
        raise HTTPException(status_code=404, detail=f"Unknown institution_id {institution_id!r}.")
    return CooperativeStatsResponse(**stats)
