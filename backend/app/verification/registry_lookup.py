"""On-demand verification against public registries (land authority, certifier).

Unlike the scheduled batch connectors, a registry lookup is triggered *during the
verification phase of a single claim* — synchronous from the caller's view — and
is cached so repeated lookups of the same parcel/holder during high-volume
ingestion don't spam the external API.

Configuration (env, resolved via the secrets seam):
    LAND_REGISTRY_BASE_URL / land_registry_token   (the registry endpoint + bearer)

If the registry isn't configured, :class:`RegistryNotConfigured` is raised — the
system never fabricates an authoritative result.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.clients.cache import DEFAULT_TTL, cache_key, get_cache

logger = logging.getLogger(__name__)


class RegistryNotConfigured(RuntimeError):
    """Raised when a registry endpoint isn't configured (no fabricated result)."""


class LandRegistryResult(BaseModel):
    """Strict projection of a land-registry parcel lookup."""

    model_config = ConfigDict(extra="ignore")

    parcel_id: str
    registered_area_hectares: Optional[float] = Field(default=None, alias="areaHectares")
    owner_verified: bool = Field(default=False, alias="ownerVerified")
    registry: str = "land_registry"


async def verify_land_parcel(parcel_id: str, *, country: str) -> LandRegistryResult:
    """Look up a parcel on demand, caching the result idempotently.

    Cache hit → no external call. Cache miss → one authenticated GET, then cache.
    """
    cache = get_cache()
    key = cache_key("land_registry", country=country, parcel_id=parcel_id)

    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Registry cache hit for %s.", key)
        return LandRegistryResult.model_validate(json.loads(cached))

    base_url = os.environ.get("LAND_REGISTRY_BASE_URL")
    if not base_url:
        raise RegistryNotConfigured("LAND_REGISTRY_BASE_URL not set.")

    # Lazy imports so this module is importable without httpx / a live endpoint.
    from app.clients.auth import BearerAuth
    from app.clients.http_client import AsyncAPIClient
    from app.secrets import get_secret

    token = get_secret("land_registry_token")
    auth = BearerAuth(token) if token else None

    async with AsyncAPIClient(base_url=base_url, auth=auth) as client:
        payload = await client.get_json(f"/parcels/{parcel_id}", params={"country": country})

    result = LandRegistryResult.model_validate({"parcel_id": parcel_id, **payload})
    await cache.set(key, result.model_dump_json(), ttl=DEFAULT_TTL)
    return result


def verify_land_parcel_sync(parcel_id: str, *, country: str) -> LandRegistryResult:
    """Blocking wrapper for sync verification-phase callers."""
    import asyncio

    return asyncio.run(verify_land_parcel(parcel_id, country=country))
