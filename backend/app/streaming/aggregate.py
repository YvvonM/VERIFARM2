"""Aggregate a window of telemetry readings into reified bundles.

A 5-minute window of high-frequency ticks collapses to **one claim per
(farmer, metric)** — the windowed mean — instead of one claim per tick. Claim
ids are deterministic (per institution+farmer+metric, no time component), so each
window updates the current-state claim in place: low write IOPS, idempotent, and
no node explosion. The sensor network is a non-authoritative attesting source.
"""

from __future__ import annotations

import hashlib
from statistics import mean
from typing import Iterable

from app.models.reified import Claim, Farmer, Institution, PayloadBundle
from app.streaming.models import TelemetryReading

IOT_INSTITUTION_ID = "IOT-SENSORNET"
IOT_INSTITUTION_NAME = "IoT Sensor Network"


def _claim_id(institution_id: str, farmer_id: str, metric: str) -> str:
    raw = "|".join((institution_id, farmer_id, metric))
    return "claim_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def aggregate_readings(
    readings: Iterable[TelemetryReading],
    *,
    institution_id: str = IOT_INSTITUTION_ID,
    institution_name: str = IOT_INSTITUTION_NAME,
) -> list[PayloadBundle]:
    """Group readings by farmer→metric, average each, build one bundle per farmer."""
    by_farmer: dict[str, dict[str, list[TelemetryReading]]] = {}
    for r in readings:
        by_farmer.setdefault(r.farmer_id, {}).setdefault(r.metric, []).append(r)

    bundles: list[PayloadBundle] = []
    for farmer_id, metrics in by_farmer.items():
        claims: list[Claim] = []
        for metric, rs in metrics.items():
            latest = max(rs, key=lambda x: x.observed_at)
            claims.append(Claim(
                claim_id=_claim_id(institution_id, farmer_id, metric),
                claim_type=metric,
                value_numeric=round(mean(x.value for x in rs), 4),
                unit=latest.unit,
                confidence=0.7,
                source_id=institution_id.lower(),
                source_category="remote_sensing",
                timestamp=latest.observed_at,
            ))
        bundles.append(PayloadBundle(
            institution=Institution(
                institution_id=institution_id, name=institution_name,
                type="SensorNetwork", is_authoritative=False, consent_at_source=True,
            ),
            farmer=Farmer(farmer_id=farmer_id),
            claims=claims,
        ))
    return bundles
