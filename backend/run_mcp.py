"""Entrypoint for the VeriFarms MCP server.

Loads the project-root .env (so MCP_BACKEND=neo4j picks up NEO4J_URI/
NEO4J_USERNAME/NEO4J_PASSWORD/NEO4J_DATABASE the same way the FastAPI app
does) and starts app.mcp.server over stdio or SSE.

Usage:
    # stdio (Claude Desktop / local agents) -- mock data, no DB required
    python run_mcp.py

    # stdio against the live Aura graph
    MCP_BACKEND=neo4j python run_mcp.py

    # SSE over HTTP (for a remote AI system / external partner)
    MCP_BACKEND=neo4j MCP_TRANSPORT=sse python run_mcp.py
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from app.mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))
