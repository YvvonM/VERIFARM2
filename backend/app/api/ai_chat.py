"""Server-side proxy for the lender dashboard's "Ask AI about this farmer" box.

The frontend used to call Featherless (OpenAI-compatible) directly from the
browser, which meant ``FEATHERLESS_API_KEY`` had to be baked into the client
JS bundle — visible to anyone via devtools. This endpoint moves that call
server-side: the frontend posts the farmer profile + conversation history
here, the backend attaches the real key and forwards to Featherless, and the
key never reaches the client.

Deliberately a thin, simple, single-turn proxy — no ReAct loop, no tool
calls, no SSE, matching the original "simple chat box" design. The system
prompt is built here (not trusted from the client) so a caller can't smuggle
arbitrary instructions into it.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.api.security import rate_limit, require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ai",
    tags=["ai"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)

DEFAULT_BASE_URL = "https://api.featherless.ai/v1"
DEFAULT_MODEL = "Qwen/Qwen3-235B-A22B-Thinking-2507"
REQUEST_TIMEOUT_SECONDS = 60.0

SYSTEM_PROMPT_PREFIX = (
    "You are a lending assistant helping a loan officer understand a farmer's "
    "verified profile. Answer questions about this farmer in plain English "
    "under 100 words. Never invent information not in the data. If something "
    "is unverified, say so.\n\nFarmer Profile:\n"
)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskAboutFarmerRequest(BaseModel):
    farmer_profile: dict[str, Any] = Field(
        ..., description="The farmer profile JSON currently loaded in the dashboard."
    )
    messages: list[ChatTurn] = Field(
        ..., min_length=1, description="Conversation history; the last entry is the new question."
    )


class AskAboutFarmerResponse(BaseModel):
    content: str


def _is_configured() -> bool:
    return bool(os.environ.get("FEATHERLESS_API_KEY"))


def _call_featherless(farmer_profile: dict[str, Any], messages: list[ChatTurn]) -> str:
    api_key = os.environ.get("FEATHERLESS_API_KEY")
    base_url = os.environ.get("FEATHERLESS_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("FEATHERLESS_MODEL", DEFAULT_MODEL)

    payload = {
        "model": model,
        "max_tokens": 1000,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT_PREFIX + json.dumps(farmer_profile, indent=2),
            },
            *[{"role": m.role, "content": m.content} for m in messages],
        ],
    }
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"].get("content") or "(no response)"


@router.post("/ask-about-farmer", response_model=AskAboutFarmerResponse)
async def ask_about_farmer(payload: AskAboutFarmerRequest) -> AskAboutFarmerResponse:
    """Answer a loan officer's question about the currently-loaded farmer profile.

    Returns 503 if no ``FEATHERLESS_API_KEY`` is configured server-side, and
    502 if the upstream call fails — never silently fabricates a response.
    """
    if not _is_configured():
        raise HTTPException(
            status_code=503,
            detail="FEATHERLESS_API_KEY is not configured on the server.",
        )
    try:
        content = await run_in_threadpool(_call_featherless, payload.farmer_profile, payload.messages)
    except httpx.HTTPStatusError as exc:
        logger.exception("Featherless call failed.")
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        logger.exception("Featherless call failed.")
        raise HTTPException(status_code=502, detail="Upstream request failed.") from exc

    return AskAboutFarmerResponse(content=content)
