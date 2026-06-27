"""DLQInvestigator — the orchestrator of the data-quality agent.

One pass (:meth:`investigate_once`):

  1. Discover which metrics have ground truth to check against.
  2. For each, find reported claims whose variance from ground truth exceeds the
     threshold (the "Dead-Letter Queue" of suspect facts in the gold layer).
  3. For each conflict, assemble the source's reputation + cross-referenced
     history, run the deterministic :mod:`policy` to get a calculated
     recommendation, optionally have Featherless rephrase the rationale for
     humans, and flag the specific Claim nodes as a graph fact.

The verdict (action/severity/confidence) is always the deterministic policy's;
the LLM only ever touches wording, and silently no-ops when unconfigured — so
the agent is fully functional without an API key.
"""

from __future__ import annotations

import logging
from typing import Optional

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE, get_shared_driver
from app.investigator import graph_ops
from app.investigator.policy import recommend
from app.models.investigation import (
    ConflictInvestigation,
    Recommendation,
    SourceHistory,
)

logger = logging.getLogger(__name__)

# Default relative-variance threshold above which a discrepancy is investigated.
DEFAULT_VARIANCE_THRESHOLD = 0.20


class InvestigationReport:
    """Summary of one investigation pass."""

    def __init__(self, investigations: list[ConflictInvestigation]) -> None:
        self.investigations = investigations

    @property
    def total(self) -> int:
        return len(self.investigations)

    def to_dict(self) -> dict:
        from collections import Counter

        by_action = Counter(i.recommendation.action.value for i in self.investigations)
        by_severity = Counter(i.recommendation.severity.value for i in self.investigations)
        return {
            "total_conflicts": self.total,
            "by_action": dict(by_action),
            "by_severity": dict(by_severity),
            "investigations": [i.model_dump(mode="json") for i in self.investigations],
        }


class DLQInvestigator:
    """Background data-quality worker over the reified trust graph."""

    def __init__(
        self,
        driver: Optional[Driver] = None,
        variance_threshold: float = DEFAULT_VARIANCE_THRESHOLD,
        database: str = DEFAULT_DATABASE,
        use_llm: bool = True,
    ) -> None:
        self._driver = driver or get_shared_driver()
        self._threshold = variance_threshold
        self._database = database
        self._use_llm = use_llm

    # -- public API ---------------------------------------------------------

    def investigate_once(
        self,
        claim_types: Optional[list[str]] = None,
        flag: bool = True,
    ) -> InvestigationReport:
        """Run one full pass; optionally persist flags. Returns a report."""
        types = claim_types or graph_ops.list_authoritative_claim_types(
            self._driver, self._database
        )
        logger.info("Investigator scanning %d claim type(s): %s", len(types), types)

        # Cross-referenced "rap sheet" per source, memoized within this pass.
        prior_conflicts_cache: dict[str, int] = {}
        investigations: list[ConflictInvestigation] = []

        for claim_type in types:
            for row in graph_ops.find_conflicts(self._driver, claim_type, self._threshold, self._database):
                investigation = self._investigate_row(row, prior_conflicts_cache)
                if flag:
                    flagged = graph_ops.flag_conflict(self._driver, investigation, self._database)
                    logger.info(
                        "Flagged claim %s [%s, conf %.2f] — %s",
                        flagged, investigation.recommendation.action.value,
                        investigation.recommendation.confidence, claim_type,
                    )
                investigations.append(investigation)

        logger.info("Investigation pass complete: %d conflict(s).", len(investigations))
        return InvestigationReport(investigations)

    # -- internals ----------------------------------------------------------

    def _investigate_row(self, row: dict, prior_cache: dict[str, int]) -> ConflictInvestigation:
        """Turn one raw conflict row into a fully-reasoned investigation."""
        source_id = row["reported_by_id"]
        if source_id not in prior_cache:
            prior_cache[source_id] = graph_ops.count_source_conflicts(
                self._driver, source_id, self._threshold, self._database
            )

        source = SourceHistory(
            institution_id=source_id,
            institution_name=row.get("reported_by"),
            trust_score=row["source_trust_score"],
            comparisons=row["source_comparisons"],
            agreements=row["source_agreements"],
            prior_conflicts=prior_cache[source_id],
        )

        recommendation = recommend(
            variance=row["variance"],
            source=source,
            authoritative_value=row["authoritative_value"],
            reported_value=row["reported_value"],
            claim_type=row["claim_type"],
        )
        recommendation = self._maybe_narrate(recommendation, row, source)

        return ConflictInvestigation(
            farmer_id=row["farmer_id"],
            claim_type=row["claim_type"],
            authoritative_claim_id=row["authoritative_claim_id"],
            authoritative_value=row["authoritative_value"],
            authoritative_source=row.get("authoritative_source"),
            reported_claim_id=row["reported_claim_id"],
            reported_value=row["reported_value"],
            variance=row["variance"],
            source=source,
            recommendation=recommendation,
        )

    def _maybe_narrate(
        self, rec: Recommendation, row: dict, source: SourceHistory
    ) -> Recommendation:
        """Optionally let Featherless rephrase the rationale (verdict unchanged)."""
        if not self._use_llm:
            return rec
        try:
            from app.agent.qwen_llm import get_llm, is_llm_configured

            if not is_llm_configured():
                return rec
            from langchain_core.messages import HumanMessage, SystemMessage

            prompt = (
                "Rewrite this data-quality finding as one or two clear sentences for a "
                "data steward. Keep every number and the recommended action exactly as "
                "given; do not change the decision. Finding:\n"
                f"- metric: {row['claim_type']}\n"
                f"- ground truth: {row['authoritative_value']} (source: {row.get('authoritative_source')})\n"
                f"- reported: {row['reported_value']} by {source.institution_name} "
                f"(trust {source.trust_score:.2f}, {source.prior_conflicts} prior conflicts)\n"
                f"- variance: {round(row['variance'] * 100)}%\n"
                f"- recommended action: {rec.action.value} (severity {rec.severity.value})"
            )
            ai = get_llm(temperature=0.3).invoke([
                SystemMessage(content="You are a precise data-quality assistant."),
                HumanMessage(content=prompt),
            ])
            text = (ai.content or "").strip()
            if text:
                return rec.model_copy(update={"rationale": text})
        except Exception:  # noqa: BLE001 - narration is best-effort, never fatal.
            logger.warning("LLM narration failed; keeping deterministic rationale.", exc_info=True)
        return rec
