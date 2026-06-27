"""Ingestion API — ``POST /ingest/records``.

The gateway for raw farmer records. For each batch it:

  1. Resolves the source adapter from ``source_id`` (the Adapter Pattern).
  2. Maps each raw record onto the standard schema and validates it against
     :class:`~app.models.claims.StandardFarmerClaim`.
  3. Routes any record that fails mapping/validation to the Dead-Letter Queue
     and continues with the rest of the batch (one bad record never aborts it).
  4. Best-effort persists the validated claims to Neo4j.
  5. Returns counts of processed / successful / failed / persisted.

Validation happens *before* anything touches the database, so malformed data
can never reach the graph.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from app.api.security import rate_limit, require_api_key
from app.database import neo4j_client
from app.ingestion.adapters import MappingError, get_adapter, map_raw_record
from app.ingestion.dlq import dead_letter
from app.models.claims import IngestResponse, RecordError, StandardFarmerClaim

logger = logging.getLogger(__name__)

# Auth + rate limit: this router writes into the graph.
router = APIRouter(
    prefix="/ingest",
    tags=["ingestion"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)

# Cap the number of per-record errors echoed in the response body; the full
# detail always lives in the DLQ.
MAX_ERRORS_IN_RESPONSE = 50


class IngestRequest(BaseModel):
    """Incoming ingestion payload: a source plus a batch of raw records."""

    source_id: str = Field(
        ...,
        min_length=1,
        description="Source system, e.g. 'tegemeo_cereals' or 'agrovesto_app'.",
        examples=["tegemeo_cereals"],
    )
    records: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="Array of raw farmer records in the source's native shape.",
    )


def _flatten_validation_error(exc: ValidationError) -> list[str]:
    """Render a Pydantic ValidationError into compact, loggable messages."""
    messages: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        messages.append(f"{loc}: {err['msg']}")
    return messages


@router.post("/records", response_model=IngestResponse)
async def ingest_records(
    payload: IngestRequest,
    persist: bool = Query(
        True, description="Persist validated claims to Neo4j (best-effort)."
    ),
) -> IngestResponse:
    """Validate a batch of raw farmer records and (optionally) persist them.

    Unknown ``source_id`` values return HTTP 422 listing the supported sources.
    Individual record failures are isolated to the DLQ and reported in the
    response without failing the request.
    """
    # --- Resolve the source adapter (Adapter Pattern entry point) -----------
    try:
        adapter = get_adapter(payload.source_id)
    except KeyError as exc:
        # 422: the body is well-formed JSON but names a source we can't handle.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "Ingesting %d record(s) from source %r.",
        len(payload.records),
        payload.source_id,
    )

    valid_claims: list[StandardFarmerClaim] = []
    errors: list[RecordError] = []
    dlq_file: str | None = None

    # --- Map + validate each record independently ---------------------------
    for index, raw in enumerate(payload.records):
        try:
            mapped = map_raw_record(adapter, raw)
            claim = StandardFarmerClaim(**mapped)
        except (MappingError, ValidationError) as exc:
            messages = (
                _flatten_validation_error(exc)
                if isinstance(exc, ValidationError)
                else [str(exc)]
            )
            logger.warning("Record %d from %r rejected: %s",
                           index, payload.source_id, messages)
            path = dead_letter(payload.source_id, index, messages, raw)
            dlq_file = str(path)
            if len(errors) < MAX_ERRORS_IN_RESPONSE:
                errors.append(RecordError(index=index, errors=messages))
            continue

        valid_claims.append(claim)

    # --- Best-effort persistence to Neo4j -----------------------------------
    persisted = 0
    persistence: str = "disabled"
    if persist and valid_claims:
        rows = [claim.to_graph_row() for claim in valid_claims]
        try:
            persisted = neo4j_client.persist_claims(rows)
            persistence = "ok"
        except Exception:  # noqa: BLE001 - never fail validation on a DB outage.
            logger.exception("Neo4j persistence failed; returning validation only.")
            persistence = "failed"
    elif persist and not valid_claims:
        persistence = "skipped"  # nothing valid to write.

    return IngestResponse(
        source_id=payload.source_id,
        total_processed=len(payload.records),
        total_successful=len(valid_claims),
        total_failed=len(payload.records) - len(valid_claims),
        total_persisted=persisted,
        persistence=persistence,  # type: ignore[arg-type]
        dlq_path=dlq_file,
        errors=errors,
    )
