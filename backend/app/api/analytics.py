"""Portfolio analytics for the lender dashboard — fixed, hand-written queries.

Deliberately NOT LLM-generated Cypher (see app.agent.cypher_tool / prompts.py,
whose schema description has drifted from the reified model and produces
unreliable queries). Every query here is fixed, read-only, and was run
directly against the live graph during development to confirm it returns
real, sane numbers before being wired up — see the queries' comments for what
was checked.

Chart selection is deliberately value-chain-shaped, not farmer-trust-shaped:
where the verified farmer pool sits across partner organizations, what's being
grown, how much is being produced, and which loan products farmers currently
qualify for. No trust-score-distribution chart by design.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver
from pydantic import BaseModel

from app.api.security import rate_limit, require_api_key
from app.database import match_engine
from app.database.neo4j_client import DEFAULT_DATABASE, get_shared_driver
from app.services.product_catalog import list_products

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


# ---------------------------------------------------------------------------
# 1. Farmers by partner organization (registry MEMBER_OF) -- "where does our
#    verified farmer pool actually sit across the value chain" (cooperatives,
#    off-takers, lenders, mobile-money providers all hold membership edges).
# ---------------------------------------------------------------------------

FARMERS_BY_ORGANIZATION_QUERY = """
MATCH (f:Farmer)-[:MEMBER_OF]->(o:Organization)
RETURN o.name AS organization, o.org_role AS org_role, count(f) AS farmer_count
ORDER BY farmer_count DESC
"""


class OrganizationFarmerCount(BaseModel):
    organization: str
    org_role: str | None
    farmer_count: int


@router.get("/farmers-by-organization", response_model=list[OrganizationFarmerCount])
async def farmers_by_organization(driver: Driver = Depends(get_shared_driver)) -> list[OrganizationFarmerCount]:
    """How the verified farmer pool is distributed across value-chain partners."""

    def _work() -> list[dict[str, Any]]:
        with driver.session(database=DEFAULT_DATABASE) as session:
            return session.run(FARMERS_BY_ORGANIZATION_QUERY).data()

    rows = await run_in_threadpool(_work)
    return [OrganizationFarmerCount(**r) for r in rows]


# ---------------------------------------------------------------------------
# 2. Crop distribution -- what's actually being grown across the portfolio.
# ---------------------------------------------------------------------------

CROP_DISTRIBUTION_QUERY = """
MATCH (f:Farmer)-[:OWNS]->(:FarmHolding)-[:HAS_CYCLE]->(cc:CropCycle)
RETURN cc.crop_type AS crop_type, count(DISTINCT f) AS farmer_count
ORDER BY farmer_count DESC
"""


class CropFarmerCount(BaseModel):
    crop_type: str
    farmer_count: int


@router.get("/crop-distribution", response_model=list[CropFarmerCount])
async def crop_distribution(driver: Driver = Depends(get_shared_driver)) -> list[CropFarmerCount]:
    """Which crops the verified farmer pool grows -- portfolio diversification."""

    def _work() -> list[dict[str, Any]]:
        with driver.session(database=DEFAULT_DATABASE) as session:
            return session.run(CROP_DISTRIBUTION_QUERY).data()

    rows = await run_in_threadpool(_work)
    return [CropFarmerCount(**r) for r in rows]


# ---------------------------------------------------------------------------
# 3. Verified land size by partner organization -- sizing signal: which
#    partners' farmers represent bigger/smaller holdings (relevant to loan
#    sizing and collateral expectations). Uses each farmer's strongest
#    land_size_hectares claim (max value_numeric among their claims) so a
#    farmer attested by both satellite + cooperative isn't double-counted.
# ---------------------------------------------------------------------------

LAND_SIZE_BY_ORGANIZATION_QUERY = """
MATCH (f:Farmer)-[:MEMBER_OF]->(o:Organization)
OPTIONAL MATCH (f)<-[:BELONGS_TO]-(c:Claim {claim_type: 'land_size_hectares'})
WITH o, f, max(c.value_numeric) AS farmer_land
WITH o, avg(farmer_land) AS avg_land, sum(farmer_land) AS total_land, count(f) AS farmer_count
RETURN o.name AS organization,
       round(coalesce(avg_land, 0.0), 2) AS avg_hectares,
       round(coalesce(total_land, 0.0), 2) AS total_hectares,
       farmer_count
ORDER BY total_hectares DESC
"""


class OrganizationLandSize(BaseModel):
    organization: str
    avg_hectares: float
    total_hectares: float
    farmer_count: int


@router.get("/land-size-by-organization", response_model=list[OrganizationLandSize])
async def land_size_by_organization(driver: Driver = Depends(get_shared_driver)) -> list[OrganizationLandSize]:
    """Verified land size aggregated per partner organization."""

    def _work() -> list[dict[str, Any]]:
        with driver.session(database=DEFAULT_DATABASE) as session:
            return session.run(LAND_SIZE_BY_ORGANIZATION_QUERY).data()

    rows = await run_in_threadpool(_work)
    return [OrganizationLandSize(**r) for r in rows]


# ---------------------------------------------------------------------------
# 4. Production volume by crop -- value-chain output: where the actual
#    physical supply is concentrated, by crop.
# ---------------------------------------------------------------------------

PRODUCTION_BY_CROP_QUERY = """
MATCH (f:Farmer)-[:OWNS]->(:FarmHolding)-[:HAS_CYCLE]->(cc:CropCycle)
OPTIONAL MATCH (f)<-[:BELONGS_TO]-(c:Claim {claim_type: 'production_volume_kg'})
WITH cc.crop_type AS crop_type, f, max(c.value_numeric) AS farmer_kg
WITH crop_type, sum(coalesce(farmer_kg, 0.0)) AS total_kg, count(DISTINCT f) AS farmer_count
RETURN crop_type, round(total_kg, 1) AS total_kg, farmer_count
ORDER BY total_kg DESC
"""


class CropProduction(BaseModel):
    crop_type: str
    total_kg: float
    farmer_count: int


@router.get("/production-by-crop", response_model=list[CropProduction])
async def production_by_crop(driver: Driver = Depends(get_shared_driver)) -> list[CropProduction]:
    """Verified production volume aggregated per crop."""

    def _work() -> list[dict[str, Any]]:
        with driver.session(database=DEFAULT_DATABASE) as session:
            return session.run(PRODUCTION_BY_CROP_QUERY).data()

    rows = await run_in_threadpool(_work)
    return [CropProduction(**r) for r in rows]


# ---------------------------------------------------------------------------
# 5. Eligibility by product -- calls the EXISTING MATCH engine per farmer per
#    product (app.database.match_engine.evaluate_product); no eligibility
#    logic is duplicated here. Directly actionable: how many farmers in the
#    portfolio are loan-ready today, per product.
# ---------------------------------------------------------------------------

ALL_FARMER_IDS_QUERY = "MATCH (f:Farmer) RETURN f.id AS id"


class ProductEligibility(BaseModel):
    product_id: str
    lender_name: str
    eligible_count: int
    total_farmers: int


@router.get("/eligibility-by-product", response_model=list[ProductEligibility])
async def eligibility_by_product(driver: Driver = Depends(get_shared_driver)) -> list[ProductEligibility]:
    """How many farmers in the portfolio currently qualify for each product."""

    def _work() -> list[ProductEligibility]:
        with driver.session(database=DEFAULT_DATABASE) as session:
            farmer_ids = [r["id"] for r in session.run(ALL_FARMER_IDS_QUERY).data()]

        products = list_products()
        # Each (farmer, product) check is one independent network round-trip
        # to Neo4j; with N farmers x M products that's N*M sequential round
        # trips if done in a loop (24s for 55 farmers x 3 products on a cloud
        # Aura instance, measured during development). The driver is
        # documented thread-safe elsewhere in this codebase (see
        # app.database.neo4j_client.get_shared_driver), so fan the checks out
        # across threads instead -- this is I/O-bound, not CPU-bound.
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {
                (product.product_id, fid): pool.submit(match_engine.evaluate_product, driver, fid, product)
                for product in products
                for fid in farmer_ids
            }
            outcomes = {key: future.result()["eligible"] for key, future in futures.items()}

        return [
            ProductEligibility(
                product_id=product.product_id,
                lender_name=product.lender_name,
                eligible_count=sum(1 for fid in farmer_ids if outcomes[(product.product_id, fid)]),
                total_farmers=len(farmer_ids),
            )
            for product in products
        ]

    return await run_in_threadpool(_work)
