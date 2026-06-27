"""Spatial metadata extraction for GeoJSON + STAC.

Flattens geometry into the simple float/string properties the graph can index
efficiently — a bounding box, a geodesic area in hectares, a centroid, and a
temporal stamp — instead of storing raw coordinate arrays the graph can't query.

Area uses the standard spherical-excess ring formula (WGS84 radius), so it needs
no GIS dependency (shapely/geos); it's an approximation, accurate to well within
a percent at field scale.
"""

from __future__ import annotations

from math import radians, sin
from typing import Any, Iterator, Optional

from pydantic import BaseModel

EARTH_RADIUS_M = 6378137.0  # WGS84 equatorial radius


class SpatialMetadata(BaseModel):
    """Flattened, indexable spatial summary of a geometry."""

    geometry_type: str
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    centroid_lon: float
    centroid_lat: float
    area_hectares: float
    observed_at: Optional[str] = None

    def bbox_string(self) -> str:
        return f"{self.min_lon},{self.min_lat},{self.max_lon},{self.max_lat}"


def _exterior_rings(geometry: dict) -> list[list[list[float]]]:
    """Return exterior rings; holes are handled separately in area()."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if gtype == "Polygon":
        return [coords[0]] if coords else []
    if gtype == "MultiPolygon":
        return [poly[0] for poly in coords if poly]
    return []


def _all_positions(geometry: dict) -> Iterator[tuple[float, float]]:
    """Yield every (lon, lat) in the geometry, regardless of type/nesting."""
    def walk(node: Any):
        if (
            isinstance(node, (list, tuple))
            and len(node) >= 2
            and all(isinstance(c, (int, float)) for c in node[:2])
        ):
            yield (float(node[0]), float(node[1]))
        elif isinstance(node, (list, tuple)):
            for child in node:
                yield from walk(child)

    yield from walk(geometry.get("coordinates", []))


def bounding_box(geometry: dict) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) over all positions."""
    lons, lats = [], []
    for lon, lat in _all_positions(geometry):
        lons.append(lon)
        lats.append(lat)
    if not lons:
        raise ValueError("Geometry has no coordinates.")
    return min(lons), min(lats), max(lons), max(lats)


def _ring_area_m2(ring: list[list[float]]) -> float:
    if len(ring) < 4:
        return 0.0
    if ring[0] != ring[-1]:
        ring = ring + [ring[0]]
    total = 0.0
    for i in range(len(ring) - 1):
        lon1, lat1 = radians(ring[i][0]), radians(ring[i][1])
        lon2, lat2 = radians(ring[i + 1][0]), radians(ring[i + 1][1])
        total += (lon2 - lon1) * (2 + sin(lat1) + sin(lat2))
    return abs(total * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0)


def area_hectares(geometry: dict) -> float:
    """Geodesic area in hectares (exterior rings minus holes)."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    m2 = 0.0
    polygons: list[list[list[list[float]]]]
    if gtype == "Polygon":
        polygons = [coords]
    elif gtype == "MultiPolygon":
        polygons = coords
    else:
        return 0.0  # points/lines have no area
    for rings in polygons:
        if not rings:
            continue
        m2 += _ring_area_m2(rings[0])               # exterior
        for hole in rings[1:]:                      # subtract holes
            m2 -= _ring_area_m2(hole)
    return round(max(0.0, m2) / 10_000.0, 4)


def _centroid(geometry: dict) -> tuple[float, float]:
    positions = list(_all_positions(geometry))
    n = len(positions)
    return (sum(p[0] for p in positions) / n, sum(p[1] for p in positions) / n)


def extract_geometry(geometry: dict, *, observed_at: Optional[str] = None) -> SpatialMetadata:
    """Flatten a GeoJSON geometry into :class:`SpatialMetadata`."""
    min_lon, min_lat, max_lon, max_lat = bounding_box(geometry)
    clon, clat = _centroid(geometry)
    return SpatialMetadata(
        geometry_type=geometry.get("type", "unknown"),
        min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat,
        centroid_lon=round(clon, 6), centroid_lat=round(clat, 6),
        area_hectares=area_hectares(geometry),
        observed_at=observed_at,
    )


def extract_geojson_feature(feature: dict) -> SpatialMetadata:
    """Extract from a GeoJSON Feature (datetime read from properties if present)."""
    props = feature.get("properties") or {}
    return extract_geometry(feature["geometry"], observed_at=props.get("datetime"))


def extract_stac_item(item: dict) -> SpatialMetadata:
    """Extract from a STAC Item (uses its declared bbox when available)."""
    props = item.get("properties") or {}
    observed_at = props.get("datetime") or props.get("start_datetime")
    geometry = item.get("geometry") or {}
    meta = extract_geometry(geometry, observed_at=observed_at)
    bbox = item.get("bbox")
    if bbox and len(bbox) >= 4:  # prefer the catalog's declared bbox
        meta.min_lon, meta.min_lat, meta.max_lon, meta.max_lat = (
            float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        )
    return meta
