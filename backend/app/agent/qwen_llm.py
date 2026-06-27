"""LLM client for the Loan Officer Copilot (Qwen3 served by Featherless).

LangChain is used **only at the LLM/tool layer** — ``langchain_openai.ChatOpenAI``
pointed at Featherless (which is OpenAI-compatible) gives us native ``bind_tools``
and ``with_structured_output`` for clean Pydantic tool calling. Orchestration stays
plain Python: the ReAct loops live in :mod:`app.agent.copilot`, not in a graph
framework.

Two model slots, both env-driven:

  * ``FEATHERLESS_MODEL``        — the main reasoning/Cypher model (default the
    flagship Qwen3, native tool-calling).
  * ``FEATHERLESS_ROUTER_MODEL`` — a smaller/faster model for the intent router;
    falls back to the main model when unset.

When ``FEATHERLESS_API_KEY`` is absent, :func:`is_llm_configured` returns
``False`` and callers fall back to the deterministic mock stream.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.featherless.ai/v1"
DEFAULT_MODEL = "Qwen/Qwen3-235B-A22B-Thinking-2507"
# Vision/multimodal model for OCR (paper-register image → fields). Featherless
# hosts the Qwen2.5-VL family; override with FEATHERLESS_VISION_MODEL.
DEFAULT_VISION_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"

# Low temperature: routing and Cypher generation want determinism, not prose.
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TIMEOUT_SECONDS = 120.0


def is_llm_configured() -> bool:
    """Return whether a Featherless API key is present in the environment."""
    return bool(os.environ.get("FEATHERLESS_API_KEY"))


def get_model_name() -> str:
    """Main reasoning model id (env-overridable)."""
    return os.environ.get("FEATHERLESS_MODEL", DEFAULT_MODEL)


def get_router_model_name() -> str:
    """Fast model id for the intent router; defaults to the main model."""
    return os.environ.get("FEATHERLESS_ROUTER_MODEL", get_model_name())


def get_vision_model_name() -> str:
    """Multimodal model id for OCR vision extraction (env-overridable)."""
    return os.environ.get("FEATHERLESS_VISION_MODEL", DEFAULT_VISION_MODEL)


@lru_cache(maxsize=8)
def get_llm(model: Optional[str] = None, temperature: float = DEFAULT_TEMPERATURE):
    """Build (and cache) a ``ChatOpenAI`` bound to Featherless.

    Cached per (model, temperature). ``langchain_openai`` is imported lazily so
    the module loads even when it (or a key) is absent; the import only fires on
    the first real call.

    Raises:
        RuntimeError: if no API key is configured (gate on
            :func:`is_llm_configured` first).
    """
    api_key = os.environ.get("FEATHERLESS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FEATHERLESS_API_KEY is not set; cannot build the LLM. "
            "Gate calls on is_llm_configured() and fall back to the mock."
        )

    from langchain_openai import ChatOpenAI

    base_url = os.environ.get("FEATHERLESS_BASE_URL", DEFAULT_BASE_URL)
    resolved = model or get_model_name()
    logger.info("Initializing Featherless ChatOpenAI %s at %s.", resolved, base_url)
    return ChatOpenAI(
        model=resolved,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        max_retries=2,
    )
