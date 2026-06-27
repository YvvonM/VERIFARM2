"""API surface for the Autonomous DLQ Investigator.

The investigator normally runs as a background worker, but these routes make it
demoable and give a data steward a window onto its output:

  * ``POST /api/v1/investigator/run``  — trigger one pass on demand.
  * ``GET  /api/v1/investigator/flags`` — list currently-flagged claims.

The DB work is synchronous (Neo4j driver), so it's offloaded to a thread to keep
the event loop responsive.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query

from app.api.security import rate_limit, require_api_key
from app.database.neo4j_client import get_shared_driver
from app.investigator import graph_ops
from app.investigator.investigator import DEFAULT_VARIANCE_THRESHOLD
from app.investigator.worker import run_pass

logger = logging.getLogger(__name__)

# Auth + rate limit: triggers data-quality passes over the graph.
router = APIRouter(
    prefix="/api/v1/investigator",
    tags=["investigator"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


@router.post("/run")
async def run_investigation(
    variance_threshold: float = Query(
        DEFAULT_VARIANCE_THRESHOLD, ge=0.0, le=10.0,
        description="Relative variance above which a discrepancy is investigated (0.20 == 20%).",
    ),
    flag: bool = Query(True, description="Persist flags to the graph."),
    use_llm: bool = Query(True, description="Let Featherless rephrase rationales when configured."),
) -> dict:
    """Run one investigation pass and return its summary."""
    logger.info("Manual investigator run (threshold=%.2f, flag=%s).", variance_threshold, flag)
    return await asyncio.to_thread(run_pass, variance_threshold, flag, use_llm)


@router.get("/flags")
async def list_flags(
    limit: int = Query(100, ge=1, le=1000, description="Max flags to return."),
) -> dict:
    """List currently-flagged claims, worst variance first."""
    flags = await asyncio.to_thread(graph_ops.list_flags, get_shared_driver(), limit)
    return {"total": len(flags), "flags": flags}
