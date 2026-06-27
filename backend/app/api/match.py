"""MATCH API — ``POST /match/{farmer_id}``.

Connects a verified farmer profile to the catalog of financial products. For
each requested product it runs the data-driven rules engine
(:mod:`app.database.match_engine`) against the farmer's reified claims and
reports eligibility plus a rule-by-rule breakdown.

The blocking Neo4j calls are dispatched to a worker thread
(``run_in_threadpool``) so the async event loop is never stalled.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver

from app.api.security import rate_limit, require_api_key
from app.database import match_engine
from app.database.neo4j_client import get_shared_driver
from app.models.products import (
    FinancialProduct,
    MatchRequest,
    MatchResponse,
    ProductMatch,
)
from app.services.product_catalog import get_product, list_products

logger = logging.getLogger(__name__)

# Auth + rate limit: matching reads farmer eligibility against products.
router = APIRouter(
    prefix="/match",
    tags=["matching"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


def _select_products(request: MatchRequest | None) -> list[FinancialProduct]:
    """Resolve the request into a concrete list of products to evaluate."""
    if request is None or not request.product_ids:
        return list_products()
    products: list[FinancialProduct] = []
    for product_id in request.product_ids:
        try:
            products.append(get_product(product_id))
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return products


@router.get("/products", response_model=list[FinancialProduct])
async def get_products() -> list[FinancialProduct]:
    """List the financial-product catalog (handy for the demo UI)."""
    return list_products()


@router.post("/{farmer_id}", response_model=MatchResponse)
async def match_farmer(
    farmer_id: str,
    request: MatchRequest | None = Body(default=None),
    driver: Driver = Depends(get_shared_driver),
) -> MatchResponse:
    """Evaluate a farmer against the product catalog (or a named subset).

    Returns one :class:`ProductMatch` per evaluated product. A 404 is returned
    when the farmer node does not exist; an unknown ``product_id`` yields 422.
    """
    products = _select_products(request)

    exists = await run_in_threadpool(match_engine.farmer_exists, driver, farmer_id)
    if not exists:
        raise HTTPException(status_code=404, detail=f"Unknown farmer_id {farmer_id!r}.")

    matches: list[ProductMatch] = []
    for product in products:
        result = await run_in_threadpool(
            match_engine.evaluate_product, driver, farmer_id, product
        )
        matches.append(
            ProductMatch(
                product_id=product.product_id,
                lender_name=product.lender_name,
                eligible=result["eligible"],
                rule_breakdown=result["rule_breakdown"],
            )
        )

    eligible_count = sum(1 for m in matches if m.eligible)
    logger.info(
        "Matched farmer %r against %d product(s); eligible for %d.",
        farmer_id, len(matches), eligible_count,
    )
    return MatchResponse(farmer_id=farmer_id, matches=matches)
