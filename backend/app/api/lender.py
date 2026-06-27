"""Lender-facing query layer — the commercial output of the whole system.

``GET /api/v1/lender/eligible-farmers`` is how a lender finds farmers to loan
to: filterable, paginated, privacy-safe (never returns ``farmer_id`` and
``phone`` together), and backed entirely by verified (reified) Claims —
never by the coarse ``Farmer.verified`` flag.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver
from pydantic import BaseModel, Field

from app.api.security import rate_limit, require_api_key
from app.database import match_engine
from app.database.neo4j_client import DEFAULT_DATABASE, get_shared_driver
from app.database.trust_graph import APPROVED_SOURCE_CATEGORIES
from app.services.product_catalog import get_product, list_products

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/lender",
    tags=["lender"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


# ---------------------------------------------------------------------------
# Response contracts. Deliberately no ``phone`` field anywhere here -- a
# lender browsing this list never receives farmer_id + phone in the same
# response (see docstring above).
# ---------------------------------------------------------------------------


class VerifiedClaimSummary(BaseModel):
    claim_type: str
    value: Optional[str] = None
    source: Optional[str] = None
    source_trust: float = 0.0


class MatchedProductSummary(BaseModel):
    product_id: str
    lender_name: str
    eligible: bool


class EligibleFarmer(BaseModel):
    farmer_id: str
    cooperative_name: Optional[str] = None
    crop_types: list[str] = Field(default_factory=list)
    verified_land_hectares: Optional[float] = None
    verification_sources: list[VerifiedClaimSummary] = Field(default_factory=list)
    matched_products: list[MatchedProductSummary] = Field(default_factory=list)


class EligibleFarmersPage(BaseModel):
    total: int
    page: int
    page_size: int
    farmers: list[EligibleFarmer]


# ---------------------------------------------------------------------------
# Query. Joins the registry layer (region/crop demographics) with the reified
# trust layer (verified claims) -- never the cached Farmer.verified flag.
# ---------------------------------------------------------------------------

_ELIGIBLE_FARMERS_QUERY = """
MATCH (f:Farmer)
OPTIONAL MATCH (f)-[:MEMBER_OF]->(org:Organization)
OPTIONAL MATCH (f)-[:OWNS]->(:FarmHolding)-[:HAS_CYCLE]->(cc:CropCycle)
WITH f, org, collect(DISTINCT cc.crop_type) AS crop_types
WHERE ($region IS NULL OR f.location = $region)
  AND ($crop_type IS NULL OR $crop_type IN crop_types)
MATCH (f)<-[:BELONGS_TO]-(c:Claim)<-[:ATTESTS_TO]-(inst:Institution)
WHERE coalesce(inst.trust_score, 0.0) >= $min_trust_score
  AND c.source_category IN $approved_source_categories
WITH f, org, crop_types,
     collect(DISTINCT {
         claim_type: c.claim_type,
         value: coalesce(c.value_string, toString(c.value_numeric)),
         source: inst.name,
         source_trust: coalesce(inst.trust_score, 0.0)
     }) AS verification_sources,
     max(CASE WHEN c.claim_type = 'land_size_hectares' THEN c.value_numeric ELSE null END) AS land_hectares
WHERE $min_land_hectares IS NULL OR land_hectares >= $min_land_hectares
RETURN f.id AS farmer_id, org.name AS cooperative_name, crop_types,
       land_hectares AS verified_land_hectares, verification_sources
ORDER BY f.id
SKIP $skip LIMIT $limit
"""

_ELIGIBLE_FARMERS_COUNT_QUERY = """
MATCH (f:Farmer)
OPTIONAL MATCH (f)-[:MEMBER_OF]->(org:Organization)
OPTIONAL MATCH (f)-[:OWNS]->(:FarmHolding)-[:HAS_CYCLE]->(cc:CropCycle)
WITH f, org, collect(DISTINCT cc.crop_type) AS crop_types
WHERE ($region IS NULL OR f.location = $region)
  AND ($crop_type IS NULL OR $crop_type IN crop_types)
MATCH (f)<-[:BELONGS_TO]-(c:Claim)<-[:ATTESTS_TO]-(inst:Institution)
WHERE coalesce(inst.trust_score, 0.0) >= $min_trust_score
  AND c.source_category IN $approved_source_categories
WITH f, max(CASE WHEN c.claim_type = 'land_size_hectares' THEN c.value_numeric ELSE null END) AS land_hectares
WHERE $min_land_hectares IS NULL OR land_hectares >= $min_land_hectares
RETURN count(DISTINCT f) AS total
"""


def _query_eligible_farmers(
    driver: Driver,
    min_trust_score: float,
    crop_type: Optional[str],
    region: Optional[str],
    min_land_hectares: Optional[float],
    skip: int,
    limit: int,
) -> tuple[int, list[dict]]:
    params = {
        "min_trust_score": min_trust_score,
        "crop_type": crop_type,
        "region": region,
        "min_land_hectares": min_land_hectares,
        "approved_source_categories": APPROVED_SOURCE_CATEGORIES,
    }
    with driver.session(database=DEFAULT_DATABASE) as session:
        total = session.run(_ELIGIBLE_FARMERS_COUNT_QUERY, **params).single()
        rows = session.run(
            _ELIGIBLE_FARMERS_QUERY, **params, skip=skip, limit=limit
        ).data()
    return (int(total["total"]) if total else 0), rows


@router.get("/eligible-farmers", response_model=EligibleFarmersPage)
async def get_eligible_farmers(
    min_trust_score: float = Query(0.5, ge=0.0, le=1.0),
    crop_type: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None),
    min_land_hectares: Optional[float] = Query(default=None, ge=0.0),
    product_id: Optional[str] = Query(
        default=None, description="Narrow matched_products to one catalog product id."
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    driver: Driver = Depends(get_shared_driver),
) -> EligibleFarmersPage:
    """List farmers whose verified claims clear the given thresholds.

    Eligibility is always re-derived from Claim/Institution.trust_score (never
    the cached ``Farmer.verified`` flag) and filtered to claims with an
    approved ``source_category`` -- a farmer's own self-report can never make
    them appear here.
    """
    skip = (page - 1) * page_size
    total, rows = await run_in_threadpool(
        _query_eligible_farmers,
        driver, min_trust_score, crop_type, region, min_land_hectares, skip, page_size,
    )

    if product_id:
        try:
            products = [get_product(product_id)]
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        products = list_products()
    farmers: list[EligibleFarmer] = []
    for row in rows:
        matched: list[MatchedProductSummary] = []
        for product in products:
            result = await run_in_threadpool(
                match_engine.evaluate_product, driver, row["farmer_id"], product
            )
            matched.append(
                MatchedProductSummary(
                    product_id=product.product_id,
                    lender_name=product.lender_name,
                    eligible=result["eligible"],
                )
            )

        farmers.append(
            EligibleFarmer(
                farmer_id=row["farmer_id"],
                cooperative_name=row.get("cooperative_name"),
                crop_types=[c for c in (row.get("crop_types") or []) if c],
                verified_land_hectares=row.get("verified_land_hectares"),
                verification_sources=[
                    VerifiedClaimSummary(**v) for v in (row.get("verification_sources") or []) if v.get("claim_type")
                ],
                matched_products=matched,
            )
        )

    logger.info(
        "Lender query: %d eligible farmer(s) (page %d/%d, min_trust=%.2f).",
        total, page, max(1, -(-total // page_size)), min_trust_score,
    )
    return EligibleFarmersPage(total=total, page=page, page_size=page_size, farmers=farmers)
