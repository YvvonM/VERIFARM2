"""Schema-split enforcement — the connector may only publish the reified layer.

The graph has two models (see the README): the **reified** trust layer
``(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)`` that the
agents and Investigator read, and a legacy **gold-layer** shape
``(:Organization)`` / ``[:VERIFIED_BY]`` / ``[:ABOUT]`` that they do NOT read.
New ingestion must write the reified layer only — anything that writes the
gold-layer shape produces data the platform can't see and re-opens the
divergence we already closed.

This module is the publish boundary that makes that a hard rule, two ways:

  * :func:`enforce_reified_contract` — type gate: only strict
    :class:`PayloadBundle` objects may be published (not raw dicts, not
    gold-layer payloads).
  * :func:`assert_reified_only` — text gate: reject any Cypher containing
    gold-layer node labels / relationship types before it can run.

:func:`publish_reified` composes both and is the single entry point the
connector uses instead of touching :class:`GraphIngestionService` directly.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from app.models.reified import PayloadBundle

logger = logging.getLogger(__name__)


class GoldLayerWriteError(ValueError):
    """Raised when an ingestion attempt would write the forbidden gold-layer shape."""


# Gold-layer markers that must never appear in a reified write. Matched
# case-insensitively against the Cypher text. (Reified writes use :Institution /
# :Claim / :Farmer and ATTESTS_TO / BELONGS_TO — none of these tokens.)
_GOLD_LAYER_TOKENS = re.compile(
    r"(:Organization\b|\bVERIFIED_BY\b|:Document\b|\[\s*:ABOUT\b|\[\s*:SCOPED_TO\b|\[\s*:GRANTED\b)",
    re.IGNORECASE,
)


def assert_reified_only(cypher: str) -> str:
    """Return ``cypher`` if it is gold-layer-free; else raise :class:`GoldLayerWriteError`."""
    match = _GOLD_LAYER_TOKENS.search(cypher or "")
    if match:
        raise GoldLayerWriteError(
            f"Refusing to write the gold-layer shape (matched {match.group(0)!r}). "
            f"Ingestion must publish the reified Institution/ATTESTS_TO/Claim/BELONGS_TO model."
        )
    return cypher


def enforce_reified_contract(bundles: Iterable[object]) -> list[PayloadBundle]:
    """Return the bundles as a list iff every item is a strict ``PayloadBundle``.

    Rejects raw dicts and any other shape, so a caller can't smuggle a gold-layer
    payload past the boundary by handing the writer a hand-built dict.
    """
    out: list[PayloadBundle] = []
    for item in bundles:
        if not isinstance(item, PayloadBundle):
            raise GoldLayerWriteError(
                f"Connector may only publish reified PayloadBundle objects; "
                f"got {type(item).__name__}."
            )
        out.append(item)
    return out


def publish_reified(driver, bundles: Iterable[object]) -> int:
    """The single publish boundary: enforce the split, then write. Returns claims written.

    1. Type gate — only PayloadBundles.
    2. Text gate — the writer's own Cypher must be reified (defends against the
       write surface itself ever drifting to a gold-layer statement).
    3. Idempotent reified write via the canonical ``GraphIngestionService``.
    """
    from app.database.graph_ingestion import INGEST_BUNDLES_CYPHER, GraphIngestionService

    safe = enforce_reified_contract(bundles)
    assert_reified_only(INGEST_BUNDLES_CYPHER)  # the only Cypher this path runs

    svc = GraphIngestionService(driver=driver)  # does not own the driver → won't close it
    svc.ensure_constraints()
    written = svc.ingest_payload_bundles(safe)
    logger.info("Published %d reified bundle(s) → %d claim(s).", len(safe), written)

    # Distribution: notify downstream consumers that these claims are now in the
    # gold layer. Best-effort — never let a dead sink fail a successful merge.
    from app.events import publish_claims_merged

    publish_claims_merged(safe)
    return written
