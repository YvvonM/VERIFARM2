"""Pydantic v2 models for the ingestion API (Milestone: Ingestion & Validation).

The :class:`StandardFarmerClaim` is the canonical, normalized representation of
a single farmer verification claim *after* a source-specific adapter has mapped
raw third-party keys onto our schema. Every raw record from any source
(``tegemeo_cereals``, ``agrovesto_app``, ...) must validate against this model
before it is allowed anywhere near the graph database.

The remaining models describe the ingestion *response* contract: per-record
failures (which also feed the Dead-Letter Queue) and the batch-level summary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# The canonical claim.
# ---------------------------------------------------------------------------


class StandardFarmerClaim(BaseModel):
    """A single, fully-normalized farmer verification claim.

    This is the strict target schema for the configuration-driven adapter. A
    claim links a *farmer* to the *verifier* (an off-taker or a cooperative)
    that vouched for them. ``app.verification.claim_bridge.standard_claim_to_bundle``
    reifies this into the canonical
    ``(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)`` shape —
    there is no ``[:VERIFIED_BY]`` edge in this codebase.

    ``extra="forbid"`` makes the model reject any unmapped keys, so a broken
    adapter surfaces immediately as a validation error rather than silently
    writing junk to the graph.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # --- Identity -----------------------------------------------------------
    farmer_id: str = Field(
        ..., min_length=1, description="Stable natural key for the farmer (MERGE key)."
    )
    farmer_name: str = Field(..., min_length=1, description="Farmer's full name.")
    national_id: Optional[str] = Field(
        None, description="Government ID / NIN, if provided by the source."
    )
    phone: Optional[str] = Field(None, description="Contact phone number.")

    # --- Location -----------------------------------------------------------
    region: Optional[str] = Field(
        None, description="County / state / district of the holding."
    )
    country: str = Field(..., min_length=1, description="Country of the holding.")

    # --- Production claim ----------------------------------------------------
    crop_type: str = Field(..., min_length=1, description="Primary crop claimed.")
    land_size_hectares: float = Field(
        ..., gt=0, description="Holding size in hectares (post-conversion)."
    )
    production_volume_kg: float = Field(
        ..., ge=0, description="Claimed/expected production volume in kilograms."
    )

    # --- Verifier (off-taker or cooperative) --------------------------------
    verifier_id: str = Field(
        ..., min_length=1, description="Stable key for the verifying organization."
    )
    verifier_name: str = Field(
        ..., min_length=1, description="Human-readable verifier name."
    )
    verifier_type: Literal["OffTaker", "Cooperative"] = Field(
        ..., description="Graph label to apply to the verifier node."
    )

    # --- Provenance ---------------------------------------------------------
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Source-reported confidence in the claim."
    )
    source_id: str = Field(..., min_length=1, description="Originating source system.")
    claim_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the claim was ingested (UTC).",
    )

    def to_graph_row(self) -> dict[str, Any]:
        """Serialize into a Neo4j-friendly ``UNWIND`` row (JSON scalar types)."""
        row = self.model_dump()
        # Cypher's datetime() wants an ISO-8601 string, not a Python datetime.
        row["claim_timestamp"] = self.claim_timestamp.isoformat()
        return row


# ---------------------------------------------------------------------------
# Ingestion response contract.
# ---------------------------------------------------------------------------


class RecordError(BaseModel):
    """A single rejected record, surfaced in the response and the DLQ."""

    index: int = Field(..., description="Position of the record in the input batch.")
    errors: list[str] = Field(..., description="Human-readable validation messages.")


class IngestResponse(BaseModel):
    """Batch-level summary returned by ``POST /ingest/records``."""

    source_id: str
    total_processed: int = Field(..., description="Records received in the batch.")
    total_successful: int = Field(..., description="Records that validated cleanly.")
    total_failed: int = Field(..., description="Records routed to the DLQ.")
    total_persisted: int = Field(
        0, description="Validated records written to Neo4j (0 if persistence off)."
    )
    persistence: Literal["disabled", "ok", "skipped", "failed"] = Field(
        ..., description="Outcome of the graph-persistence step."
    )
    dlq_path: Optional[str] = Field(
        None, description="File the failed records were appended to, if any."
    )
    errors: list[RecordError] = Field(
        default_factory=list, description="Per-record validation failures."
    )
