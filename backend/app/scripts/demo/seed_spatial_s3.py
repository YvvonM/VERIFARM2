"""Seed the demo object store with roster-aligned parcel GeoJSON (Phase 3).

Generates one square parcel polygon per roster farmer whose **geodesic area**
matches that farmer's ground-truth land size (so the spatial partner agrees with
the satellite), inflating every Kth farmer's parcel into a conflict the
Investigator will flag. Uploads the features — split across a couple of objects,
plus a deliberately malformed feature to exercise the audit's failed-validation
counter — to an S3/MinIO bucket under a prefix the connector scans.

    python -m app.scripts.demo.seed_spatial_s3 --farmers 60

Then pull them into the graph:

    python -m app.bulk.s3_connector --bucket verifarms-bulk --prefix spatial/

DSN/endpoint: ``--endpoint-url`` > ``BULK_S3_ENDPOINT_URL`` env; bucket from
``--bucket`` > ``BULK_S3_BUCKET`` > ``verifarms-bulk``. Credentials from the
standard ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from typing import Optional

from app.bulk.s3_connector import s3_client
from app.scripts.demo.roster import (
    DEFAULT_CONFLICT_EVERY,
    DEFAULT_FARMERS,
    DemoFarmer,
    demo_roster,
    is_conflict,
)

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "verifarms-bulk"
DEFAULT_PREFIX = "spatial/"
_CONFLICT_MULTIPLIER = 2.6  # area scale for conflict parcels (matches the roster)
_OBSERVED_AT = "2026-06-01T00:00:00Z"

# Approximate agricultural centroids; per-farmer offset keeps parcels distinct.
_COUNTRY_CENTER = {"Kenya": (37.30, -0.50), "Nigeria": (8.52, 12.00)}
_M_PER_DEG_LAT = 111_320.0


def _centroid(f: DemoFarmer) -> tuple[float, float]:
    base_lon, base_lat = _COUNTRY_CENTER.get(f.country, _COUNTRY_CENTER["Kenya"])
    return base_lon + (f.index % 20) * 0.02, base_lat + (f.index // 20) * 0.02


def _square(lon0: float, lat0: float, area_ha: float) -> dict:
    """A square polygon centred at (lon0, lat0) whose geodesic area ≈ ``area_ha``."""
    side_m = math.sqrt(area_ha * 10_000.0)
    half_lat = (side_m / 2) / _M_PER_DEG_LAT
    half_lon = (side_m / 2) / (_M_PER_DEG_LAT * math.cos(math.radians(lat0)))
    ring = [
        [round(lon0 - half_lon, 7), round(lat0 - half_lat, 7)],
        [round(lon0 + half_lon, 7), round(lat0 - half_lat, 7)],
        [round(lon0 + half_lon, 7), round(lat0 + half_lat, 7)],
        [round(lon0 - half_lon, 7), round(lat0 + half_lat, 7)],
        [round(lon0 - half_lon, 7), round(lat0 - half_lat, 7)],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _feature(f: DemoFarmer, conflict_every: int) -> dict:
    lon, lat = _centroid(f)
    area = f.true_land_ha * (_CONFLICT_MULTIPLIER if is_conflict(f.index, conflict_every) else 1.0)
    return {
        "type": "Feature",
        "geometry": _square(lon, lat, area),
        "properties": {
            "farmer_id": f.member_uuid,
            "datetime": _OBSERVED_AT,   # STAC-style temporal stamp
            "source": "geoboundaries",
        },
    }


def build_collections(farmers: int, conflict_every: int, parts: int) -> tuple[list[tuple[str, dict]], list[str]]:
    """Return [(key_suffix, FeatureCollection)] split into ``parts`` objects + conflict ids.

    The last part gets one malformed feature (no geometry) to exercise the audit.
    """
    roster = demo_roster(farmers)
    features = [_feature(f, conflict_every) for f in roster]
    conflicts = [f.member_uuid for f in roster if is_conflict(f.index, conflict_every)]

    # One malformed feature → counted as failed_validation, not a crash.
    features.append({"type": "Feature", "geometry": None,
                     "properties": {"farmer_id": "F-BADGEOM"}})

    parts = max(1, parts)
    chunk = math.ceil(len(features) / parts)
    collections: list[tuple[str, dict]] = []
    for i in range(parts):
        slice_ = features[i * chunk:(i + 1) * chunk]
        if not slice_:
            continue
        collections.append(
            (f"parcels_part{i + 1}.geojson", {"type": "FeatureCollection", "features": slice_})
        )
    return collections, conflicts


def _ensure_bucket(client, bucket: str) -> None:
    from botocore.exceptions import ClientError

    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        logger.info("Creating bucket %r.", bucket)
        client.create_bucket(Bucket=bucket)


def upload(collections, *, bucket: str, prefix: str, endpoint_url: Optional[str]) -> list[str]:
    client = s3_client(endpoint_url)
    _ensure_bucket(client, bucket)
    keys: list[str] = []
    for suffix, collection in collections:
        key = f"{prefix.rstrip('/')}/{suffix}"
        client.put_object(
            Bucket=bucket, Key=key,
            Body=json.dumps(collection).encode("utf-8"),
            ContentType="application/geo+json",
        )
        keys.append(key)
    return keys


def _main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="Seed the demo object store with parcel GeoJSON.")
    p.add_argument("--farmers", type=int, default=DEFAULT_FARMERS)
    p.add_argument("--bucket", default=os.environ.get("BULK_S3_BUCKET", DEFAULT_BUCKET))
    p.add_argument("--prefix", default=os.environ.get("BULK_S3_PREFIX", DEFAULT_PREFIX))
    p.add_argument("--endpoint-url", default=None, help="Override BULK_S3_ENDPOINT_URL.")
    p.add_argument("--conflict-every", type=int, default=DEFAULT_CONFLICT_EVERY)
    p.add_argument("--parts", type=int, default=2, help="Split features across N objects.")
    args = p.parse_args()

    collections, conflicts = build_collections(args.farmers, args.conflict_every, args.parts)
    keys = upload(collections, bucket=args.bucket, prefix=args.prefix, endpoint_url=args.endpoint_url)

    print(json.dumps({
        "bucket": args.bucket,
        "objects": keys,
        "farmers": args.farmers,
        "conflict_members": conflicts,
        "malformed_features": 1,
    }, indent=2))
    print(f"\nUploaded {len(keys)} object(s) to s3://{args.bucket}/{args.prefix}. "
          f"{len(conflicts)} parcels are oversized (conflict). Next:")
    print(f"  python -m app.bulk.s3_connector --bucket {args.bucket} --prefix {args.prefix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
