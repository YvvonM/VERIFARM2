"""Agent stream entrypoint (plain Python — no LangGraph).

Kept as the stable import surface for the SSE layer (`api/chat_stream.py` imports
:func:`astream_agent_events`) across the migration off LangGraph. When a
Featherless key is configured it delegates to the supervisor copilot
(:mod:`app.agent.copilot`); otherwise it serves the deterministic mock so the app
runs end-to-end without credentials. ``build_component`` is re-exported from
:mod:`app.agent.render` for backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from app.agent.events import component_event, status_event
from app.agent.qwen_llm import is_llm_configured
from app.agent.render import build_component  # re-export
from app.models.ui_schemas import BarChartProps

__all__ = ["astream_agent_events", "mock_astream_events", "build_component"]

logger = logging.getLogger(__name__)

SIMULATED_DB_LATENCY = 1.0

MOCK_YIELD_DATA: list[dict[str, Any]] = [
    {"region": "Nakuru", "country": "Kenya", "farmers": 312, "yield": 2.6},
    {"region": "Uasin Gishu", "country": "Kenya", "farmers": 288, "yield": 2.9},
    {"region": "Kano", "country": "Nigeria", "farmers": 241, "yield": 1.9},
    {"region": "Kaduna", "country": "Nigeria", "farmers": 159, "yield": 2.1},
]


async def astream_agent_events(query: str) -> AsyncGenerator[dict[str, Any], None]:
    """Yield status/component event envelopes for ``query`` (copilot or mock)."""
    if is_llm_configured():
        from app.agent.copilot import stream_copilot  # lazy: keeps this import light

        async for event in stream_copilot(query):
            yield event
    else:
        logger.info("FEATHERLESS_API_KEY unset — serving mock agent stream.")
        async for event in mock_astream_events(query):
            yield event


async def mock_astream_events(query: str) -> AsyncGenerator[dict[str, Any], None]:
    """Deterministic fallback stream: status frames + a BarChart + an Insight."""
    logger.info("Mock agent received query: %r", query)

    yield status_event("Routing your question...")
    await asyncio.sleep(0.2)
    yield status_event("Executing Neo4j Cypher query for regional yields...")
    await asyncio.sleep(SIMULATED_DB_LATENCY)
    yield status_event(f"Retrieved {len(MOCK_YIELD_DATA)} regional yield aggregates.")
    await asyncio.sleep(0.2)

    yield status_event("Structuring the results...")
    props = BarChartProps(data=MOCK_YIELD_DATA, xKey="region", yKey="yield")
    yield component_event("BarChart", props.model_dump())

    yield status_event("Synthesizing the answer...")
    yield component_event(
        "Insight",
        {
            "text": (
                "Uasin Gishu leads at 2.9 t/ha, followed by Nakuru (2.6). The Nigerian "
                "regions trail (Kaduna 2.1, Kano 1.9). [mock — set FEATHERLESS_API_KEY for live data]"
            ),
            "title": "Copilot answer",
        },
    )
    logger.info("Mock agent finished for query: %r", query)
