"""SSE event envelopes shared by the copilot and the mock.

The streaming API (`api/chat_stream.py`) maps items shaped like LangGraph's old
``astream_events`` output — ``on_custom_event`` named ``status`` / ``component``
— onto the SSE wire contract. We keep that exact shape (so the API layer is
unchanged) even though there is no LangGraph anymore: these are plain dicts.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4


def custom_event(name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Build a dict matching the ``on_custom_event`` envelope the API maps."""
    return {
        "event": "on_custom_event",
        "name": name,
        "run_id": str(uuid4()),
        "tags": [],
        "metadata": {},
        "data": data,
    }


def status_event(message: str) -> dict[str, Any]:
    """A progress update frame."""
    return custom_event("status", {"message": message})


def component_event(component_type: str, props: dict[str, Any]) -> dict[str, Any]:
    """A GenUI component frame."""
    return custom_event("component", {"componentType": component_type, "props": props})
