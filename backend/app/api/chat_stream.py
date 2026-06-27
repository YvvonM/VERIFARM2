"""Milestone 3 — SSE endpoint and event-generator engine.

Bridges the supervisor copilot's event stream to a Server-Sent Events response.
The engine maps the agent's ``on_custom_event`` items (status/component) onto the
strict GenUI wire contract, formats each as ``data: <json>\\n\\n``, and guarantees
the stream is always terminated cleanly even when the agent raises mid-flight.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from app.agent.graph import astream_agent_events
from app.api.security import rate_limit, require_api_key
from app.models.ui_schemas import (
    StreamComponentResponse,
    StreamErrorResponse,
    StreamStatusResponse,
)

logger = logging.getLogger(__name__)

# Auth + rate limit on the (costly) LLM stream. EventSource can't set headers, so
# require_api_key also accepts the key as a ?api_key= query param.
router = APIRouter(
    prefix="/api",
    tags=["chat"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)

# SSE sentinel emitted once the stream is complete so clients can close cleanly.
DONE_SENTINEL = "event: end\ndata: [DONE]\n\n"


def _sse(payload: BaseModel) -> str:
    """Serialize a Pydantic envelope into a single SSE message frame."""
    return f"data: {payload.model_dump_json()}\n\n"


async def event_generator(query: str) -> AsyncGenerator[str, None]:
    """Map agent events to validated SSE frames with full error boundaries.

    Recognised event mappings:
        * custom event ``status``    -> :class:`StreamStatusResponse`
        * custom event ``component`` -> :class:`StreamComponentResponse`

    Any other ``astream_events`` items (model token streams, chain start/end,
    etc.) are intentionally ignored — only contract-shaped GenUI events reach
    the client. Validation or runtime failures are converted into a terminal
    :class:`StreamErrorResponse` rather than breaking the SSE connection.
    """
    try:
        async for event in astream_agent_events(query):
            kind = event.get("event")
            name = event.get("name")
            data = event.get("data") or {}

            if kind != "on_custom_event":
                continue

            if name == "status":
                yield _sse(StreamStatusResponse(message=data["message"]))
            elif name == "component":
                yield _sse(
                    StreamComponentResponse(
                        componentType=data["componentType"],
                        props=data["props"],
                    )
                )
            else:
                logger.debug("Ignoring unmapped custom event: %s", name)

    except ValidationError as exc:
        logger.exception("Event failed contract validation for query %r", query)
        yield _sse(
            StreamErrorResponse(message=f"Malformed agent event: {exc.error_count()} issue(s).")
        )
    except Exception:  # noqa: BLE001 - boundary: never leak a traceback to SSE.
        logger.exception("Unhandled error while streaming query %r", query)
        yield _sse(
            StreamErrorResponse(message="Internal error while generating the response.")
        )
    finally:
        yield DONE_SENTINEL


@router.get("/chat")
async def chat(
    query: str = Query(..., min_length=1, description="Natural-language user query."),
) -> StreamingResponse:
    """Stream agent progress + GenUI component payloads as Server-Sent Events."""
    logger.info("Opening SSE stream for query: %r", query)
    return StreamingResponse(
        event_generator(query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering (e.g. nginx) so chunks flush immediately.
            "X-Accel-Buffering": "no",
        },
    )
