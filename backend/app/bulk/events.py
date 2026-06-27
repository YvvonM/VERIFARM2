"""Event-driven trigger — parse cloud object-created notifications.

A partner uploads a CSV/Parquet/GeoJSON to object storage; the bucket emits an
event (S3 Event Notification → SQS/SNS, or the GCS/Azure equivalent) that lands
on a queue. :func:`parse_s3_event` turns that notification into the object
references the bulk processor needs, and :func:`route_extension` picks the
handler by file type. The queue consumer itself is deployment-specific (SQS poll
/ the RabbitMQ consumer pattern from streaming); this keeps the parsing pure and
testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ObjectRef:
    bucket: str
    key: str

    @property
    def extension(self) -> str:
        return self.key.rsplit(".", 1)[-1].lower() if "." in self.key else ""


# Supported bulk formats → logical handler name.
_ROUTES = {
    "csv": "tabular",
    "parquet": "tabular",
    "geojson": "spatial",
    "json": "spatial",      # treat .json as GeoJSON for spatial uploads
}


def parse_s3_event(event: dict) -> list[ObjectRef]:
    """Extract object references from an S3 Event Notification payload."""
    refs: list[ObjectRef] = []
    for record in event.get("Records", []):
        s3 = record.get("s3", {})
        bucket = s3.get("bucket", {}).get("name")
        key = s3.get("object", {}).get("key")
        if bucket and key:
            # S3 keys are URL-encoded in notifications (spaces → '+', %XX).
            from urllib.parse import unquote_plus

            refs.append(ObjectRef(bucket=bucket, key=unquote_plus(key)))
    return refs


def route_extension(ext: str) -> Optional[str]:
    """Map a file extension to a bulk handler ('tabular' | 'spatial'), or None."""
    return _ROUTES.get(ext.lower())
