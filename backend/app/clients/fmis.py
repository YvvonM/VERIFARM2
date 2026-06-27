"""FMIS (Farm Management Information System) GraphQL adapter.

ERP/FMIS payloads are heavy. We minimize over-fetching by sending a query that
selects *exactly* the fields the claim_bridge needs, then pass the response
through a **strict Pydantic model** that drops anything else. The model maps
camelCase GraphQL fields to our snake_case names and converts the result into a
reified :class:`PayloadBundle` with deterministic, idempotent claim ids.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.reified import Claim, Farmer, Institution, PayloadBundle

# Exactly the fields the reified claims need — nothing more (no over-fetch).
FMIS_FARMER_QUERY = """
query FarmerForClaims($farmerId: ID!) {
  farmer(id: $farmerId) {
    id
    landSizeHectares
    cropType
    productionVolumeKg
  }
}
""".strip()


class FmisFarmer(BaseModel):
    """Strict projection of the FMIS ``farmer`` node (extras dropped)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    farmer_id: str = Field(..., alias="id", min_length=1)
    land_size_hectares: Optional[float] = Field(default=None, alias="landSizeHectares")
    crop_type: Optional[str] = Field(default=None, alias="cropType")
    production_volume_kg: Optional[float] = Field(default=None, alias="productionVolumeKg")


def _claim_id(institution_id: str, farmer_id: str, claim_type: str) -> str:
    raw = "|".join((institution_id, farmer_id, claim_type))
    return "claim_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def fmis_farmer_to_bundle(
    farmer: FmisFarmer,
    institution_id: str,
    institution_name: str,
) -> Optional[PayloadBundle]:
    """Map a validated FMIS farmer onto a reified bundle (None if no metrics)."""
    claims: list[Claim] = []
    if farmer.land_size_hectares is not None:
        claims.append(Claim(
            claim_id=_claim_id(institution_id, farmer.farmer_id, "land_size_hectares"),
            claim_type="land_size_hectares", value_numeric=farmer.land_size_hectares,
            unit="ha", confidence=0.75, source_id=institution_id.lower(),
            source_category="off_taker",
        ))
    if farmer.production_volume_kg is not None:
        claims.append(Claim(
            claim_id=_claim_id(institution_id, farmer.farmer_id, "production_volume_kg"),
            claim_type="production_volume_kg", value_numeric=farmer.production_volume_kg,
            unit="kg", confidence=0.75, source_id=institution_id.lower(),
            source_category="off_taker",
        ))
    if farmer.crop_type is not None:
        claims.append(Claim(
            claim_id=_claim_id(institution_id, farmer.farmer_id, "crop_type"),
            claim_type="crop_type", value_string=farmer.crop_type,
            confidence=0.7, source_id=institution_id.lower(),
            source_category="off_taker",
        ))
    if not claims:
        return None
    return PayloadBundle(
        institution=Institution(
            institution_id=institution_id, name=institution_name,
            type="FMIS", is_authoritative=False, consent_at_source=True,
        ),
        farmer=Farmer(farmer_id=farmer.farmer_id),
        claims=claims,
    )


async def fetch_fmis_farmer(client, farmer_id: str) -> Optional[FmisFarmer]:
    """Query the FMIS GraphQL endpoint for one farmer; validate strictly."""
    data = await client.graphql(FMIS_FARMER_QUERY, {"farmerId": farmer_id})
    node = (data or {}).get("farmer")
    return FmisFarmer.model_validate(node) if node else None
