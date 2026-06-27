"""verifarms MCP server — read-only egress of the gold layer to LLMs / A2A agents.

  models   — strict Pydantic tool outputs (→ MCP outputSchema)
  service  — read-only graph service (DI; mock / Neo4j read-transactions only)
  server   — FastMCP instance, tools, resources, stdio + SSE transports
"""
