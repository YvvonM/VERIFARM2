"""FastAPI application entry point for the GenUI Agricultural Dashboard.

Boots the streaming API (Milestone 3): configures structured logging and CORS,
mounts the SSE chat router, and exposes a health probe. Run directly for local
development, or via ``uvicorn main:app`` in any ASGI host.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
    from pathlib import Path
    # Load from project root, one level up from backend/
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from app.api.chat_stream import router as chat_router
from app.api.ingest import router as ingest_router
from app.api.consent import router as consent_router
from app.api.gold import router as gold_router
from app.api.export import router as export_router
from app.api.investigator import router as investigator_router
from app.api.match import router as match_router
from app.api.profiles import router as profiles_router
from app.database.neo4j_client import close_shared_driver
from app.investigator.worker import start_background_investigator
from app.api.farmers import router as farmers_router
from app.api.onboarding import router as onboarding_router
from app.api.translate import router as translate_router
from app.api.cooperative import router as cooperative_router
from app.api.lender import router as lender_router
from app.api.ai_chat import router as ai_chat_router
from app.api.analytics import router as analytics_router

# ---------------------------------------------------------------------------
# Structured logging.
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("verifarms.api")

# ---------------------------------------------------------------------------
# CORS: allow the local frontend during the demo (comma-separated override).
# ---------------------------------------------------------------------------

#DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,https://scaling-guide-r5x9p5p49jqh54w-5173.app.github.dev"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# Application.
# ---------------------------------------------------------------------------

# Opt-in remote MCP gateway (MCP_REMOTE_ENABLED=true). Mounted at /mcp behind
# its own Bearer auth gate; it is itself 401-safe when no token backend is
# configured, so enabling it without MCP_JWT_SECRET/MCP_AUTH_DEV exposes nothing.
MCP_REMOTE_ENABLED = os.environ.get("MCP_REMOTE_ENABLED", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("VERIFARMS API started. CORS origins: %s", ALLOWED_ORIGINS)
    # Opt-in background data-quality worker (INVESTIGATOR_ENABLED=true).
    investigator_task = start_background_investigator(app)
    if MCP_REMOTE_ENABLED:
        # The streamable-HTTP transport needs its session manager running for the
        # lifetime of the host app; enter it here so the mounted /mcp app works.
        from app.mcp.remote import remote_mcp

        async with remote_mcp.session_manager.run():
            logger.info("Remote MCP gateway mounted at /mcp (auth-gated).")
            yield
    else:
        yield
    if investigator_task is not None:
        investigator_task.cancel()
    close_shared_driver()
    logger.info("VERIFARMS API shutting down.")


app = FastAPI(
    title="VERIFARMS GenUI Streaming API",
    description="Streaming agentic API bridging the supervisor copilot to a GenUI frontend.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(farmers_router)
app.include_router(onboarding_router)
app.include_router(translate_router)
app.include_router(chat_router)
app.include_router(ingest_router)
app.include_router(match_router)
app.include_router(profiles_router)
app.include_router(consent_router)
app.include_router(gold_router)
app.include_router(investigator_router)
app.include_router(export_router)
app.include_router(cooperative_router)
app.include_router(lender_router)
app.include_router(ai_chat_router)
app.include_router(analytics_router)

if MCP_REMOTE_ENABLED:
    # /mcp = Bearer auth gate → FastMCP streamable-HTTP (multi-tenant, read-only).
    from app.mcp.auth import AuthContextMiddleware
    from app.mcp.remote import remote_mcp

    app.mount("/mcp", AuthContextMiddleware(remote_mcp.streamable_http_app()))


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Lightweight liveness probe."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("RELOAD", "true").lower() == "true",
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
