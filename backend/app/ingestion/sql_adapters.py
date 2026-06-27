"""External SQL-source adapters → canonical :class:`PayloadBundle`.

Each external stakeholder exposes farmer data in their own table shape. An
adapter is the thin translation layer that validates those raw rows against a
**strict Pydantic model** (the trust boundary — malformed rows are rejected here,
never reaching the graph) and maps the survivors onto our reified contract,
turning one wide, source-specific row into a
:class:`~app.models.reified.PayloadBundle` of typed :class:`Claim` nodes.

Adding a new stakeholder is a new row-model + mapper here; nothing downstream
(schema-split enforcement, graph ingestion, analytics) changes.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.ingestion.adapters import ACRES_TO_HECTARES  # 1 acre = 0.404686 ha
from app.models.reified import Claim, Farmer, Institution, PayloadBundle

logger = logging.getLogger(__name__)

# Static identity for this stakeholder. Reuses the institution id used elsewhere
# in the codebase so Tegemeo is a single node across every ingestion path.
TEGEMEO_INSTITUTION = Institution(
    institution_id="ORG-TEGEMEO",
    name="Tegemeo Cereals",
    is_authoritative=False,
    # Farmers consented to Tegemeo when they registered / delivered, so Tegemeo
    # gets a standing grant at ingestion and needs no separate consent request.
    consent_at_source=True,
)


class TegemeoRegistryRow(BaseModel):
    """Strict schema for one raw row from Tegemeo's member registry.

    ``member_uuid`` is required (a row with no farmer identity is meaningless and
    is rejected). The two metrics are optional and *leniently* coerced: a dirty
    cell becomes ``None`` rather than dropping the whole farmer — bad data in one
    column shouldn't lose a valid registration.
    """

    model_config = ConfigDict(extra="ignore")  # tolerate extra selected columns

    member_uuid: str = Field(..., min_length=1)
    farm_acres: Optional[float] = None
    harvest_delivered_kg: Optional[float] = None

    @field_validator("member_uuid", mode="before")
    @classmethod
    def _stringify_uuid(cls, v):
        # DB may hand back a UUID/int — normalize to the string ids the graph uses.
        return str(v) if v is not None else v

    @field_validator("farm_acres", "harvest_delivered_kg", mode="before")
    @classmethod
    def _lenient_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            logger.warning("Non-numeric metric %r; treating as null.", v)
            return None


def _claim_id(institution_id: str, farmer_id: str, claim_type: str) -> str:
    """Deterministic, current-state claim id for a registry mirror.

    No time component: each (institution, farmer, claim_type) maps to ONE claim
    node, so re-syncing a source updates the value in place (via the writer's
    ``SET``) rather than appending a new node every run — i.e. the pull is
    idempotent. (Use a time-nonced id instead when temporal history matters.)
    """
    raw = "|".join((institution_id, farmer_id, claim_type))
    return "claim_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class MappingResult:
    """Outcome of mapping a batch of raw rows.

    ``rejected`` carries the strict-validation failures (schema-mapping errors)
    so the orchestrator can alert on them instead of letting them vanish into a
    log line. ``skipped_no_metric`` counts valid-but-empty rows (not a failure).
    """

    bundles: list[PayloadBundle] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    skipped_no_metric: int = 0


def map_registry_rows(raw_sql_rows: list[dict]) -> MappingResult:
    """Validate Tegemeo rows (strict Pydantic) and map survivors to bundles.

    Each raw row looks like
    ``{"member_uuid": "123", "farm_acres": 2.5, "harvest_delivered_kg": 500}`` and
    is expanded into up to two claims (``land_size_hectares`` from acres,
    ``production_volume_kg``). Rows that fail validation are collected in
    ``rejected`` (a schema-mapping failure → alertable); empty rows are counted
    but not treated as failures. Claim ids are deterministic → idempotent re-sync.
    """
    inst_id = TEGEMEO_INSTITUTION.institution_id
    result = MappingResult()

    for index, raw in enumerate(raw_sql_rows):
        try:
            row = TegemeoRegistryRow.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Row %d failed validation: %s", index, exc.errors())
            result.rejected.append({"index": index, "error": exc.errors()})
            continue

        claims: list[Claim] = []
        if row.farm_acres is not None:
            claims.append(
                Claim(
                    claim_id=_claim_id(inst_id, row.member_uuid, "land_size_hectares"),
                    claim_type="land_size_hectares",
                    value_numeric=round(row.farm_acres * ACRES_TO_HECTARES, 4),
                    confidence=0.7,
                )
            )
        if row.harvest_delivered_kg is not None:
            claims.append(
                Claim(
                    claim_id=_claim_id(inst_id, row.member_uuid, "production_volume_kg"),
                    claim_type="production_volume_kg",
                    value_numeric=row.harvest_delivered_kg,
                    confidence=0.8,
                )
            )

        if not claims:
            result.skipped_no_metric += 1
            continue

        result.bundles.append(
            PayloadBundle(
                institution=TEGEMEO_INSTITUTION,
                farmer=Farmer(farmer_id=row.member_uuid),
                claims=claims,
            )
        )

    logger.info(
        "Mapped %d row(s) → %d bundle(s), %d rejected, %d empty.",
        len(raw_sql_rows), len(result.bundles), len(result.rejected), result.skipped_no_metric,
    )
    return result


def extract_and_map_tegemeo_data(raw_sql_rows: list[dict]) -> list[PayloadBundle]:
    """Backward-compatible wrapper: return just the mapped bundles."""
    return map_registry_rows(raw_sql_rows).bundles
