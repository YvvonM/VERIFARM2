"""S3 / MinIO object-store connector for the bulk-spatial pipeline.

The missing "deployment-specific consumer" that :mod:`app.bulk.events` describes:
it actually *fetches* objects from an S3-compatible store and feeds them to the
pure processor (:func:`app.bulk.processor.process_geojson`). One ``boto3`` client
talks to either real AWS S3 or a local MinIO (set ``BULK_S3_ENDPOINT_URL``).

Like the Postgres connector and the provider seam, it **refuses to invent a
source**: with no bucket configured it raises :class:`SourceNotConfigured` rather
than guessing. ``boto3`` is imported lazily so the backend boots without it.

    BULK_S3_BUCKET        verifarms-bulk
    BULK_S3_PREFIX        spatial/
    BULK_S3_ENDPOINT_URL  http://minio:9000        (omit for real AWS S3)
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from app.bulk.audit import BulkJobAudit
from app.bulk.events import ObjectRef, route_extension
from app.bulk.processor import process_geojson

logger = logging.getLogger(__name__)

DEFAULT_BUCKET_ENV = "BULK_S3_BUCKET"
DEFAULT_PREFIX = "spatial/"

# A spatial partner uploading parcel boundaries is a non-authoritative source.
DEFAULT_INSTITUTION_ID = "ORG-GEOPARTNER"
DEFAULT_INSTITUTION_NAME = "GeoBoundaries Partner"


class SourceNotConfigured(RuntimeError):
    """Raised when no object-store bucket is configured."""


def _resolve_bucket(bucket: Optional[str]) -> str:
    resolved = bucket or os.environ.get(DEFAULT_BUCKET_ENV)
    if not resolved:
        raise SourceNotConfigured(
            f"No bulk bucket configured; set {DEFAULT_BUCKET_ENV} or pass --bucket."
        )
    return resolved


def s3_client(endpoint_url: Optional[str] = None):
    """Build a boto3 S3 client for AWS or a MinIO endpoint (path-style addressing)."""
    import boto3
    from botocore.client import Config

    endpoint = endpoint_url or os.environ.get("BULK_S3_ENDPOINT_URL") or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        # MinIO needs path-style + s3v4; harmless against real AWS.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def list_keys(bucket: str, prefix: str = DEFAULT_PREFIX, *, client=None) -> list[str]:
    """List object keys under ``prefix`` (paginated)."""
    client = client or s3_client()
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            keys.append(obj["Key"])
    return keys


def fetch_object(bucket: str, key: str, *, client=None) -> bytes:
    """Download one object's bytes."""
    client = client or s3_client()
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def process_key(
    ref: ObjectRef,
    *,
    client=None,
    institution_id: str = DEFAULT_INSTITUTION_ID,
    institution_name: str = DEFAULT_INSTITUTION_NAME,
    driver=None,
    audit_store=None,
) -> Optional[BulkJobAudit]:
    """Fetch + route + process a single object. Returns its audit (None if skipped).

    Only spatial formats (geojson/json) are handled here; STAC items are valid
    GeoJSON Features, so STAC FeatureCollections flow through the same path.
    """
    handler = route_extension(ref.extension)
    if handler != "spatial":
        logger.info("Skipping %s (handler=%s, not spatial).", ref.key, handler)
        return None

    raw = fetch_object(ref.bucket, ref.key, client=client)
    doc = json.loads(raw)
    audit = process_geojson(
        doc,
        source=f"s3://{ref.bucket}/{ref.key}",
        institution_id=institution_id,
        institution_name=institution_name,
        object_key=ref.key,
        driver=driver,
        audit_store=audit_store,
    )
    logger.info(
        "Processed %s: %d rows, %d ok, %d failed, %d rejected.",
        ref.key, audit.total_rows, audit.succeeded, audit.failed_validation, audit.rejected,
    )
    return audit


def process_prefix(
    bucket: Optional[str] = None,
    prefix: str = DEFAULT_PREFIX,
    *,
    institution_id: str = DEFAULT_INSTITUTION_ID,
    institution_name: str = DEFAULT_INSTITUTION_NAME,
    driver=None,
    audit_store=None,
) -> list[BulkJobAudit]:
    """Process every spatial object under ``prefix``. Returns the per-object audits."""
    bucket = _resolve_bucket(bucket)
    client = s3_client()

    # Reuse the audit store across objects so all jobs land in one place.
    if audit_store is None and driver is not None:
        from app.bulk.audit import Neo4jAuditStore

        audit_store = Neo4jAuditStore(driver)

    audits: list[BulkJobAudit] = []
    for key in list_keys(bucket, prefix, client=client):
        audit = process_key(
            ObjectRef(bucket=bucket, key=key),
            client=client,
            institution_id=institution_id,
            institution_name=institution_name,
            driver=driver,
            audit_store=audit_store,
        )
        if audit is not None:
            audits.append(audit)
    return audits


def _main() -> int:
    import argparse

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="Fetch + process spatial objects from S3/MinIO into the graph.")
    p.add_argument("--bucket", default=None, help="Override BULK_S3_BUCKET.")
    p.add_argument("--prefix", default=os.environ.get("BULK_S3_PREFIX", DEFAULT_PREFIX))
    p.add_argument("--institution-id", default=DEFAULT_INSTITUTION_ID)
    p.add_argument("--institution-name", default=DEFAULT_INSTITUTION_NAME)
    args = p.parse_args()

    from app.database.neo4j_client import get_driver

    driver = get_driver()
    try:
        audits = process_prefix(
            bucket=args.bucket,
            prefix=args.prefix,
            institution_id=args.institution_id,
            institution_name=args.institution_name,
            driver=driver,
        )
    except SourceNotConfigured as exc:
        logger.error("Not configured: %s", exc)
        return 2
    finally:
        driver.close()

    import json as _json

    totals = {
        "objects": len(audits),
        "rows": sum(a.total_rows for a in audits),
        "succeeded": sum(a.succeeded for a in audits),
        "failed_validation": sum(a.failed_validation for a in audits),
        "rejected": sum(a.rejected for a in audits),
    }
    print(_json.dumps(totals, indent=2))
    print(f"\nWrote {totals['succeeded']} spatial claim-bundle(s) across {totals['objects']} object(s). "
          "Each parcel → a geodesic land_size_hectares + a parcel_bbox claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
