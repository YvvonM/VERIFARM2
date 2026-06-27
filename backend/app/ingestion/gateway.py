"""Silver-standard validation gateway (Bronze → Silver).

The single entry point that turns raw, untrusted payloads into validated
:class:`PayloadBundle` objects ready for the graph. It is deliberately
*fault-isolating*: one bad payload is routed to the Dead-Letter Queue and the
rest of the batch proceeds, so ingestion never crashes on malformed input.

Validation (including the authoritative-confidence override) is enforced by the
Pydantic V2 models in :mod:`app.models.reified`; this module only orchestrates
parse-or-quarantine and returns the clean set.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.ingestion.dlq import DeadLetterQueue
from app.models.reified import PayloadBundle

logger = logging.getLogger(__name__)


def process_incoming_batch(
    raw_batches: list[dict[str, Any]],
    dlq: DeadLetterQueue | None = None,
) -> list[PayloadBundle]:
    """Validate a batch of raw payloads, quarantining failures to the DLQ.

    Args:
        raw_batches: Raw payload dicts (Bronze), each expected to shape a
            :class:`PayloadBundle` (institution + farmer + claims).
        dlq: Dead-Letter Queue to receive failures; a default one is created
            when omitted.

    Returns:
        Only the payloads that validated cleanly — ready for Neo4j ingestion.
    """
    dlq = dlq or DeadLetterQueue()
    validated: list[PayloadBundle] = []

    for index, raw in enumerate(raw_batches):
        try:
            # model_validate runs every field + the @model_validator rules,
            # including pinning authoritative-source confidence to 1.0.
            validated.append(PayloadBundle.model_validate(raw))
        except ValidationError as exc:
            # Quarantine and carry on — never abort the batch for one bad row.
            logger.warning("Payload %d failed validation; routed to DLQ.", index)
            dlq.log_failure(raw, str(exc))

    logger.info(
        "Validation gateway: %d/%d payload(s) passed; %d quarantined.",
        len(validated), len(raw_batches), len(raw_batches) - len(validated),
    )
    return validated
