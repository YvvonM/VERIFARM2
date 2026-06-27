"""Persist OCR claims into the canonical reified graph — the single write path.

This replaces the old ``neo4j_writer.to_cypher`` (which wrote the divergent
``(:Organization)``/``[:VERIFIED_BY]`` gold-layer shape via string-interpolated
Cypher). Instead, an :class:`OCRClaim` is normalized by
:func:`app.verification.claim_bridge.ocr_claim_to_bundle` into the reified
``(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)`` contract and
written by :class:`app.database.graph_ingestion.GraphIngestionService` — fully
parameterized (no injection) and, crucially, **visible to the trust layer,
the Loan Officer Copilot, and the DLQ Investigator**, which all traverse the
reified model.
"""

from __future__ import annotations

import logging
from typing import Optional

from .models import OCRClaim
from .pipeline import process

logger = logging.getLogger(__name__)


def ingest_ocr_claim(
    farmer_id: str,
    claim: OCRClaim,
    institution_id: str,
    institution_name: str,
    institution_type: str = "Cooperative",
    driver=None,
) -> int:
    """Reify and persist an ``OCRClaim``; return the number of claims written.

    The paper register is a non-authoritative institutional attestation: its
    claims are scored *against* ground truth (satellite), not treated as truth.
    Returns 0 when no structured field was extracted (nothing to ingest).
    """
    # Imported here so this module (and the OCR package) stays importable without
    # a live neo4j driver / pydantic at module-load time.
    from app.database.graph_ingestion import GraphIngestionService
    from app.verification.claim_bridge import ocr_claim_to_bundle

    bundle = ocr_claim_to_bundle(
        farmer_id, claim, institution_id, institution_name, institution_type
    )
    if bundle is None:
        logger.warning(
            "OCR document %r produced no structured fields; nothing ingested.",
            claim.document_ref,
        )
        return 0

    svc = GraphIngestionService(driver=driver)
    try:
        svc.ensure_constraints()
        written = svc.ingest_payload_bundles([bundle])
        logger.info("Ingested %d reified OCR claim(s) for farmer %s.", written, farmer_id)
        return written
    finally:
        svc.close()


def process_and_ingest(
    image_path: str,
    document_id: str,
    farmer_id: str,
    institution_id: str,
    institution_name: str,
    institution_type: str = "Cooperative",
    driver=None,
) -> tuple[OCRClaim, int]:
    """Run the vision OCR pipeline and persist the result via the reified path.

    Returns the extracted ``OCRClaim`` and the number of reified claims written.
    """
    claim = process(image_path, document_id, institution_id, institution_name)
    written = ingest_ocr_claim(
        farmer_id, claim, institution_id, institution_name, institution_type, driver
    )
    return claim, written
