"""Plain-Python bulk processor (Silver-layer producer).

Reads a partner GeoJSON FeatureCollection, validates each feature, flattens its
geometry to spatial metadata, and maps it to reified claims (a geodesic
``land_size_hectares`` + a ``parcel_bbox`` string), publishing through the
schema-split guard. It tallies succeeded / failed-validation / rejected counts
into a :class:`BulkJobAudit`.

This handles local / modest files. For very large dumps the distributed
``spark_job`` does the Bronze→Silver cleaning first; this stage then ingests the
Silver output the same way.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable, Optional

from app.bulk.audit import BulkJobAudit
from app.bulk.spatial import extract_geojson_feature
from app.models.reified import Claim, Farmer, Institution, PayloadBundle

logger = logging.getLogger(__name__)


def _claim_id(institution_id: str, farmer_id: str, claim_type: str) -> str:
    raw = "|".join((institution_id, farmer_id, claim_type))
    return "claim_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _farmer_id(props: dict) -> Optional[str]:
    return props.get("farmer_id") or props.get("farmerId") or props.get("id")


def process_geojson(
    feature_collection: dict,
    *,
    source: str,
    institution_id: str,
    institution_name: str,
    object_key: str = "inline",
    publish: Optional[Callable[[list[PayloadBundle]], Any]] = None,
    driver=None,
    audit_store=None,
) -> BulkJobAudit:
    """Process a GeoJSON FeatureCollection into reified bundles; return the audit."""
    audit = BulkJobAudit(source=source, object_key=object_key)
    features = feature_collection.get("features", []) or []
    audit.total_rows = len(features)

    bundles: list[PayloadBundle] = []
    for feature in features:
        try:
            geometry = feature.get("geometry")
            props = feature.get("properties") or {}
            farmer_id = _farmer_id(props)
            if not geometry or not farmer_id:
                raise ValueError("missing geometry or farmer_id")
            meta = extract_geojson_feature(feature)  # raises if geometry has no coords
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Feature failed validation: %s", exc)
            audit.failed_validation += 1
            continue

        bundles.append(PayloadBundle(
            institution=Institution(
                institution_id=institution_id, name=institution_name,
                type="SpatialPartner", is_authoritative=False, consent_at_source=True,
            ),
            farmer=Farmer(farmer_id=str(farmer_id)),
            claims=[
                Claim(
                    claim_id=_claim_id(institution_id, str(farmer_id), "land_size_hectares"),
                    claim_type="land_size_hectares", value_numeric=meta.area_hectares,
                    unit="ha", confidence=0.7, source_id=source,
                    source_category="remote_sensing",
                ),
                Claim(
                    claim_id=_claim_id(institution_id, str(farmer_id), "parcel_bbox"),
                    claim_type="parcel_bbox", value_string=meta.bbox_string(),
                    confidence=0.7, source_id=source,
                    source_category="remote_sensing",
                ),
            ],
        ))

    if bundles:
        try:
            (publish or _default_publish(driver))(bundles)
            audit.succeeded = len(bundles)
        except Exception:  # noqa: BLE001 - claim_bridge / write rejected the batch.
            logger.exception("Bulk batch rejected by the claim_bridge.")
            audit.rejected = len(bundles)

    audit.finish()
    if audit_store is not None:
        audit_store.record(audit)
    return audit


def _default_publish(driver):
    """Default publisher → the reified schema-split guard."""
    def _publish(bundles: list[PayloadBundle]):
        from app.database.neo4j_client import get_driver
        from app.ingestion.reified_guard import publish_reified

        publish_reified(driver or get_driver(), bundles)
    return _publish
