"""Loan Officer Copilot — supervisor architecture; transparent ReAct loops.

    query ── Intent Router ──► Operational path (vetted tools)
                          └──► Analytical path (free-form Graph-RAG Cypher)
                                       │
                                       ▼
                          deterministic render → Insight synthesis

LangChain is used only at the LLM/tool layer (``ChatOpenAI`` + ``bind_tools``);
the orchestration is a plain Python ``for``-loop ReAct cycle, kept transparent and
easy to debug — no graph framework. A request is routed
(:func:`app.agent.router.classify_intent`) to one of two loops:

  * **Operational** — high-stakes single-entity lookups answered by hardcoded
    tools (:mod:`app.agent.tools`); the model only picks the tool + args.
  * **Analytical** — exploratory/aggregate questions answered by LLM-authored,
    read-only Cypher (:class:`CypherExecutionTool`, guarded by ``cypher_guard``).

Gathered rows are rendered **deterministically** into a GenUI component and the
conversation is synthesized into a plain-language Insight. :func:`stream_copilot`
yields the same ``status`` / ``component`` event envelopes the SSE layer consumes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from app.agent.cypher_tool import CypherExecutionTool, execute_read_only_cypher
from app.agent.events import component_event, status_event
from app.agent.prompts import ANALYTICAL_PROMPT, OPERATIONAL_PROMPT, SYNTHESIS_PROMPT
from app.agent.qwen_llm import get_llm
from app.agent.render import build_component
from app.agent.router import classify_intent
from app.agent.tools import TOOLS, TOOLS_BY_NAME

logger = logging.getLogger(__name__)

# Max tool-calling rounds per path before forcing synthesis.
MAX_STEPS = 4


# ---------------------------------------------------------------------------
# Operational path — vetted tools.
# ---------------------------------------------------------------------------


def run_operational(query: str) -> tuple[Any, list[Any]]:
    """ReAct loop over the vetted tools. Returns (render_data, messages)."""
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    llm = get_llm().bind_tools(TOOLS)
    messages: list[Any] = [
        SystemMessage(content=OPERATIONAL_PROMPT),
        HumanMessage(content=query),
    ]
    render_data: Any = None

    for _ in range(MAX_STEPS):
        ai = llm.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            break
        for call in ai.tool_calls:
            name, args = call["name"], call.get("args", {})
            tool = TOOLS_BY_NAME.get(name)
            if tool is None:
                result: Any = {"error": f"Unknown tool {name!r}."}
            else:
                try:
                    result = tool.invoke(args)
                except Exception as exc:  # noqa: BLE001 - feed error back to model.
                    logger.exception("Operational tool %s failed.", name)
                    result = {"error": f"{type(exc).__name__}: {exc}"}
            render_data = result
            messages.append(
                ToolMessage(content=json.dumps(result, default=str), tool_call_id=call["id"])
            )

    return render_data, messages


# ---------------------------------------------------------------------------
# Analytical path — free-form, read-only Cypher (Graph-RAG).
# ---------------------------------------------------------------------------


def run_analytical(query: str) -> tuple[Any, list[Any], str | None]:
    """ReAct loop over the Cypher tool. Returns (render_data, messages, last_cypher)."""
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    llm = get_llm().bind_tools([CypherExecutionTool])
    messages: list[Any] = [
        SystemMessage(content=ANALYTICAL_PROMPT),
        HumanMessage(content=query),
    ]
    render_data: Any = None
    last_cypher: str | None = None

    for _ in range(MAX_STEPS):
        ai = llm.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            break
        for call in ai.tool_calls:
            try:
                validated = CypherExecutionTool(**call.get("args", {}))
                last_cypher = validated.query
                result: Any = execute_read_only_cypher(validated)
            except Exception as exc:  # noqa: BLE001 - bad args -> feed error back.
                result = [{"error": f"Invalid tool arguments: {exc}"}]
            render_data = result
            messages.append(
                ToolMessage(content=json.dumps(result, default=str), tool_call_id=call["id"])
            )

    return render_data, messages, last_cypher


# ---------------------------------------------------------------------------
# Synthesis.
# ---------------------------------------------------------------------------


def synthesize(messages: list[Any]) -> str:
    """Turn the gathered tool results into a concise business insight."""
    from langchain_core.messages import HumanMessage

    convo = messages + [HumanMessage(content=SYNTHESIS_PROMPT)]
    ai = get_llm(temperature=0.3).invoke(convo)
    return (ai.content or "").strip() or "No answer could be generated."


# ---------------------------------------------------------------------------
# Streaming entrypoint — the supervisor.
# ---------------------------------------------------------------------------


async def stream_copilot(query: str) -> AsyncGenerator[dict[str, Any], None]:
    """Run the supervisor and yield status/component event envelopes."""
    logger.info("Copilot received query: %r", query)

    yield status_event("Routing your question...")
    decision = await asyncio.to_thread(classify_intent, query)
    yield status_event(f"Routed to the {decision.path} path — {decision.reason}")

    if decision.path == "operational":
        yield status_event("Running vetted lookup tools...")
        render_data, messages = await asyncio.to_thread(run_operational, query)
    else:
        yield status_event("Generating a read-only Cypher query...")
        render_data, messages, cypher = await asyncio.to_thread(run_analytical, query)
        if cypher:
            yield status_event(f"Executed Cypher: {cypher}")

    # Deterministic data component (never fabricated by the model).
    yield status_event("Structuring the results...")
    component_type, props = build_component(render_data)
    yield component_event(component_type, props.model_dump())

    # Natural-language insight on top.
    yield status_event("Synthesizing the answer...")
    insight = await asyncio.to_thread(synthesize, messages)
    yield component_event("Insight", {"text": insight, "title": "Copilot answer"})

    logger.info("Copilot finished for query: %r", query)
