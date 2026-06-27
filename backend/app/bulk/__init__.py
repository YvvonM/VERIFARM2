"""Bulk + spatial ingestion (Sprint 3 — S3 / Parquet / STAC / GeoJSON).

  spatial    — GeoJSON/STAC → flattened, indexable SpatialMetadata (bbox/area/centroid)
  events     — parse S3 object-created notifications → ObjectRef + routing
  processor  — GeoJSON FeatureCollection → reified bundles + BulkJobAudit
  audit      — BulkJobAudit + Neo4j/in-memory stores (dedicated metadata table)
  spark_job  — distributed Bronze→Silver cleaning (PySpark, lazy; run on a cluster)
"""

from app.bulk.audit import BulkJobAudit, InMemoryAuditStore, Neo4jAuditStore
from app.bulk.events import ObjectRef, parse_s3_event, route_extension
from app.bulk.processor import process_geojson
from app.bulk.spatial import SpatialMetadata, area_hectares, bounding_box, extract_geojson_feature

__all__ = [
    "SpatialMetadata", "area_hectares", "bounding_box", "extract_geojson_feature",
    "parse_s3_event", "route_extension", "ObjectRef",
    "process_geojson", "BulkJobAudit", "InMemoryAuditStore", "Neo4jAuditStore",
]
