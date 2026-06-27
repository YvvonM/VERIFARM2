"""Intent router — the supervisor's first decision.

Splits a request into the Operational path (vetted, high-stakes tools) or the
Analytical path (free-form Graph-RAG Cypher). A cheap deterministic fast-path
catches the obvious cases for free; everything ambiguous goes to a fast LLM
classification using LangChain ``with_structured_output`` (native structured
output — the model is guaranteed to return a valid :class:`IntentClassification`).
On any failure it defaults to the Analytical path (the more general one), so the
copilot still attempts an answer.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.prompts import ROUTER_PROMPT
from app.agent.qwen_llm import get_llm, get_router_model_name

logger = logging.getLogger(__name__)

Path = Literal["operational", "analytical"]


class IntentClassification(BaseModel):
    """Structured output the router model must return."""

    path: Path = Field(..., description="'operational' for precise single-entity "
                       "lookups, 'analytical' for exploratory/aggregate questions.")
    reason: str = Field(..., description="A short justification for the classification.")


# Aggregate / exploratory cues → analytical.
_ANALYTICAL_CUES = re.compile(
    r"\b(how many|distribution|average|count|list all|which farmers|across|"
    r"more than|over \d|greater than|less than|between|no credit|without|"
    r"top \d|rank|trend|last (month|week|year))\b",
    re.IGNORECASE,
)
# Precise single-entity operational cues (only when paired with an id/entity).
_OPERATIONAL_CUES = re.compile(
    r"\b(eligible|eligibility|trust score|reputation|verified history|"
    r"portfolio stats|my data)\b",
    re.IGNORECASE,
)
_HAS_ID = re.compile(r"\b(F-\w+|ORG-\w+)\b", re.IGNORECASE)


class RouteDecision:
    """The router's verdict."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path: Path = path
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debug aid.
        return f"RouteDecision(path={self.path!r}, reason={self.reason!r})"


def _fast_path(query: str) -> RouteDecision | None:
    """Decide the obvious cases without an LLM call."""
    if _ANALYTICAL_CUES.search(query):
        return RouteDecision("analytical", "Matched an aggregate/exploratory cue.")
    if _OPERATIONAL_CUES.search(query) and _HAS_ID.search(query):
        return RouteDecision("operational", "Precise single-entity request with an id.")
    return None


def classify_intent(query: str) -> RouteDecision:
    """Route a request to the operational or analytical path."""
    fast = _fast_path(query)
    if fast is not None:
        logger.info("Router fast-path: %s (%s)", fast.path, fast.reason)
        return fast

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        classifier = get_llm(model=get_router_model_name()).with_structured_output(
            IntentClassification
        )
        result: IntentClassification = classifier.invoke(
            [SystemMessage(content=ROUTER_PROMPT), HumanMessage(content=query)]
        )
        logger.info("Router LLM: %s (%s)", result.path, result.reason)
        return RouteDecision(result.path, result.reason)
    except Exception:  # noqa: BLE001 - never let routing crash the request.
        logger.warning("Router failed; defaulting to analytical path.", exc_info=True)
        return RouteDecision("analytical", "Router error — defaulted to analytical.")
