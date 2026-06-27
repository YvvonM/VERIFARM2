"""
Satellite cross-check: NDVI-based cultivated-area proxy.

Compares a farmer's self-reported plot size against a Sentinel-2-derived
vegetated-area estimate around a given coordinate. This is a coarse proxy
-- it estimates "vegetated area near this point" via NDVI thresholding, NOT
precise parcel-boundary segmentation. That limitation must be stated
explicitly wherever this feeds a UI: name the imagery source (Sentinel-2)
rather than implying the figure is an exact parcel measurement.

SETUP / AUTHENTICATION PATHWAYS:
    1. Production / CI (Headless): Set the `EE_SERVICE_ACCOUNT_KEY_JSON` env variable
       containing the stringified JSON credentials. Alternatively, set 
       `EE_SERVICE_ACCOUNT_KEY_PATH` to point to your local JSON key file.
    2. Local Development: If no service account environment variables are found,
       it automatically falls back to your local personal credentials 
       (initialized via `gcloud auth application-default login` or `earthengine authenticate`).
"""

import os
from dotenv import load_dotenv
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import math
import ee


load_dotenv()
EE_SERVICE_ACCOUNT_KEY_JSON = os.getenv("EE_SERVICE_ACCOUNT_KEY_JSON")
EE_SERVICE_ACCOUNT_KEY_PATH = os.getenv("EE_SERVICE_ACCOUNT_KEY_PATH")
EE_PROJECT_ID = os.environ.get("EE_PROJECT_ID", "airflow-gcp-project")


NDVI_VEGETATION_THRESHOLD = 0.3


SENTINEL2_PIXEL_AREA_HA = 0.01  

SEARCH_WINDOW_DAYS = 90


MAX_CLOUD_COVER_PCT = 20

_initialized = False


def _ensure_initialized() -> None:
    """
    Safely initializes Earth Engine using either a service account key string,
    a local service account file path, or by falling back to system-wide personal credentials.
    """
    global _initialized
    if _initialized:
        return

    try:
        
        if EE_SERVICE_ACCOUNT_KEY_JSON:
            key_dict = json.loads(EE_SERVICE_ACCOUNT_KEY_JSON)
            credentials = ee.ServiceAccountCredentials(key_dict['client_email'], key_data=EE_SERVICE_ACCOUNT_KEY_JSON)
            ee.Initialize(credentials=credentials, project=EE_PROJECT_ID)
            print("Earth Engine initialized via Production Service Account Token.")

        # Path 2: Local JSON key file path (Easy Local Testing Alternative)
        elif EE_SERVICE_ACCOUNT_KEY_PATH and os.path.exists(EE_SERVICE_ACCOUNT_KEY_PATH):
            with open(EE_SERVICE_ACCOUNT_KEY_PATH, 'r') as f:
                key_dict = json.load(f)
            credentials = ee.ServiceAccountCredentials(key_dict['client_email'], key_file=EE_SERVICE_ACCOUNT_KEY_PATH)
            ee.Initialize(credentials=credentials, project=EE_PROJECT_ID)
            print(f"Earth Engine initialized via Local Service Account File: {EE_SERVICE_ACCOUNT_KEY_PATH}")

        # Path 3: User/Application Default Credential fallback (Default Local)
        else:
            ee.Initialize(project=EE_PROJECT_ID)
            print("Earth Engine initialized via Default Personal Credentials.")

        _initialized = True

    except Exception as e:
        raise RuntimeError(f"Failed to initialize Google Earth Engine: {str(e)}")


@dataclass
class SatelliteAreaEstimate:
    """
    detected_vegetated_area_ha: Vegetated land (NDVI > 0.3) within a buffer
    sized to the farmer's self-reported plot. This is NOT a parcel boundary
    — it cannot distinguish her plot from adjacent cultivated land. Use it
    as a plausibility check ("is there roughly this much cultivation near
    this coordinate?"), not as exact acreage verification.
    """
    detected_vegetated_area_ha: float
    scene_date: str
    cloud_cover_pct: float
    pixel_count: int


def _buffer_radius_meters_for_hectares(hectares: float) -> float:
    """
    Buffer sized to the self-reported plot, no artificial doubling.
    Assumes roughly circular plot: area = πr² - r = √(area/π).
    Converts ha - m², then m² - r in meters.
    """
    area_sqm = max(hectares, 0.1) * 10_000  # ha - m², floor to avoid zero
    radius_m = math.sqrt(area_sqm / math.pi)
    return radius_m  


def get_satellite_area_estimate(
    latitude: float,
    longitude: float,
    self_reported_hectares: float,
) -> SatelliteAreaEstimate:
    """
    Fetch the most recent reasonably cloud-free Sentinel-2 scene covering
    the given point, compute NDVI, threshold it, and sum vegetated pixel
    area within a buffer sized to the self-reported plot size.

    Raises RuntimeError if no sufficiently cloud-free scene is found in the
    search window -- callers should surface this as "satellite check
    unavailable" rather than silently returning a fabricated number.
    """
    _ensure_initialized()

    point = ee.Geometry.Point([longitude, latitude])
    radius_m = _buffer_radius_meters_for_hectares(self_reported_hectares)
    region = point.buffer(radius_m)

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=SEARCH_WINDOW_DAYS)

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(str(start_date), str(end_date))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_COVER_PCT))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    image = collection.first()

    # .getInfo() forces evaluation -- this is the point where a "no scene
    # found" condition actually surfaces, since Earth Engine's API is lazy.
    image_info = image.getInfo()
    if image_info is None:
        raise RuntimeError(
            f"No Sentinel-2 scene with <{MAX_CLOUD_COVER_PCT}% cloud cover "
            f"found within {SEARCH_WINDOW_DAYS} days for ({latitude}, {longitude})."
        )

    nir = image.select("B8")
    red = image.select("B4")
    ndvi = nir.subtract(red).divide(nir.add(red)).rename("NDVI")

    vegetated_mask = ndvi.gt(NDVI_VEGETATION_THRESHOLD)

    pixel_area = ee.Image.pixelArea()
    vegetated_area = vegetated_mask.multiply(pixel_area)

    area_stats = vegetated_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=10,  # Sentinel-2 10m bands
        maxPixels=1e8,
    )

    total_area_sqm = area_stats.get("NDVI").getInfo() or 0.0
    detected_hectares = total_area_sqm / 10_000.0

    scene_props = image_info.get("properties", {})
    scene_date = scene_props.get("PRODUCT_ID", "unknown")
    cloud_cover = scene_props.get("CLOUDY_PIXEL_PERCENTAGE", -1.0)

    return SatelliteAreaEstimate(
        detected_vegetated_area_ha=round(detected_hectares, 3),
        scene_date=str(scene_date),
        cloud_cover_pct=float(cloud_cover),
        pixel_count=int(total_area_sqm / (10 * 10)),
    )


def compute_discrepancy_pct(self_reported_ha: float, detected_ha: float) -> float:
    """
    abs(self_reported - detected) / self_reported * 100. Guards against
    division by zero for a malformed self-reported value of 0.
    """
    if self_reported_ha <= 0:
        return 0.0
    return round(abs(self_reported_ha - detected_ha) / self_reported_ha * 100, 2)


if __name__ == "__main__":
    # Kirinyaga County, Kenya
    test_lat = -0.6590
    test_lon = 37.3050
    test_self_reported_ha = 2.0

    print(f"Running satellite cross-check for ({test_lat}, {test_lon})...")
    result = get_satellite_area_estimate(
        latitude=test_lat,
        longitude=test_lon,
        self_reported_hectares=test_self_reported_ha,
    )
    print(result)

    discrepancy = compute_discrepancy_pct(test_self_reported_ha, result.detected_vegetated_area_ha)
    print(f"Self-reported: {test_self_reported_ha} ha")
    print(f"Satellite-detected (vegetated): {result.detected_vegetated_area_ha} ha")
    print(f"Discrepancy: {discrepancy}%")
