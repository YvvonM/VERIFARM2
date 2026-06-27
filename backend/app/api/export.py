"""Outbound (egress) API — downstream systems consume the verified graph.

The standardized read interface over the reified gold layer. Pydantic response
schemas (``app.models.export``) present flat, provenance-stamped claims and hide
all internal graph structure (no node labels, relationships, or Cypher).

  * ``GET /api/v1/export/claims``         — paginated JSON page of claims.
  * ``GET /api/v1/export/claims.ndjson``  — streamed NDJSON for bulk ETL.
  * ``GET /api/v1/export/farmer/{id}/claims`` — one farmer's verified claims.

Every route is protected by API-key auth (``EXPORT_API_KEY``) and a per-key/IP
rate limit (``EXPORT_RATE_LIMIT_PER_MIN``) — applied as router-level dependencies
so the database is shielded from heavy downstream read load. For push (rather
than polling), see the event layer (``app.events``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from fastapi import HTTPException

from app.api.security import rate_limit, require_api_key
from app.database import export_queries
from app.database.neo4j_client import get_shared_driver
from app.models.export import (
    ClaimExportPage,
    ExportedClaim,
    ExportedOrganization,
    FarmerClaimsExport,
    OrganizationExportPage,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/export",
    tags=["export"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],  # auth + rate limit on all routes
)

MAX_LIMIT = 1000
STREAM_PAGE = 500


@router.get("/claims", response_model=ClaimExportPage)
async def export_claims(
    claim_type: Optional[str] = Query(None, description="Filter to one claim_type."),
    min_trust_score: float = Query(0.0, ge=0.0, le=1.0, description="Min attesting-source trust."),
    since: Optional[str] = Query(None, description="ISO timestamp; only claims at/after it."),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
) -> ClaimExportPage:
    """Return a page of verified claims (newest first)."""
    rows = await asyncio.to_thread(
        export_queries.export_claims, get_shared_driver(),
        claim_type, min_trust_score, since, offset, limit,
    )
    next_offset = offset + limit if len(rows) == limit else None
    return ClaimExportPage(
        count=len(rows), offset=offset, limit=limit, next_offset=next_offset,
        claims=[ExportedClaim(**r) for r in rows],
    )


@router.get("/claims.ndjson")
async def export_claims_ndjson(
    claim_type: Optional[str] = Query(None),
    min_trust_score: float = Query(0.0, ge=0.0, le=1.0),
    since: Optional[str] = Query(None),
) -> StreamingResponse:
    """Stream the full matching set as newline-delimited JSON (one claim/line)."""

    async def _generate() -> AsyncGenerator[str, None]:
        offset = 0
        while True:
            rows = await asyncio.to_thread(
                export_queries.export_claims, get_shared_driver(),
                claim_type, min_trust_score, since, offset, STREAM_PAGE,
            )
            for row in rows:
                yield json.dumps(row, default=str) + "\n"
            if len(rows) < STREAM_PAGE:
                break
            offset += STREAM_PAGE

    return StreamingResponse(_generate(), media_type="application/x-ndjson")


@router.get("/claims/{claim_id}", response_model=ExportedClaim)
async def get_claim(claim_id: str) -> ExportedClaim:
    """Fetch a single verified claim by id (404 if not found)."""
    row = await asyncio.to_thread(export_queries.get_claim, get_shared_driver(), claim_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id!r} not found.")
    return ExportedClaim(**row)


@router.get("/organizations", response_model=OrganizationExportPage)
async def export_organizations(
    status: str = Query("all", pattern="^(verified|pending|all)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
) -> OrganizationExportPage:
    """List institutions filtered by verification status (paginated)."""
    rows = await asyncio.to_thread(
        export_queries.export_organizations, get_shared_driver(), status, offset, limit
    )
    next_offset = offset + limit if len(rows) == limit else None
    return OrganizationExportPage(
        count=len(rows), offset=offset, limit=limit, next_offset=next_offset,
        organizations=[ExportedOrganization(**r) for r in rows],
    )


@router.get("/farmer/{farmer_id}/claims", response_model=FarmerClaimsExport)
async def export_farmer_claims(
    farmer_id: str,
    min_trust_score: float = Query(0.0, ge=0.0, le=1.0),
) -> FarmerClaimsExport:
    """Return one farmer's verified claims, strongest evidence first."""
    rows = await asyncio.to_thread(
        export_queries.export_farmer_claims, get_shared_driver(), farmer_id, min_trust_score
    )
    return FarmerClaimsExport(
        farmer_id=farmer_id, count=len(rows), claims=[ExportedClaim(**r) for r in rows]
    )
