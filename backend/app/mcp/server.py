"""verifarms-mcp-server — exposes the verified-claims gold layer to LLMs / agents.

FastMCP turns each ``@mcp.tool()`` function into an MCP tool definition the LLM
discovers and calls:

  * the **function name** → tool name;
  * the **docstring** → the tool's human/LLM-readable description;
  * the **parameter type hints** → the input JSON Schema (Pydantic does the
    conversion under the hood — ``org_id: str`` becomes ``{"type": "string"}``);
  * the **return annotation** (a Pydantic model) → the structured ``outputSchema``,
    and the returned instance is emitted as a clean structured-content block.

So accurate type hints + docstrings ARE the contract the model reasons over —
there is no separate schema to maintain.

Run it:
    # stdio (Claude Desktop / local agents)
    MCP_BACKEND=neo4j python -m app.mcp.server
    # SSE over HTTP (mount on a FastAPI/Starlette app) — see build_sse_app()
    MCP_TRANSPORT=sse python -m app.mcp.server
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from app.mcp.models import ComplianceStatus, ProvenanceTrace, VerifiedClaimsBundle
from app.mcp.service import SCHEMA_TEXT, get_read_service

mcp = FastMCP(
    "verifarms-mcp-server",
    instructions=(
        "Read-only access to the VeriFarms verified-claims gold layer. Use the tools "
        "to fetch an organization's verified claims, trace a claim's provenance, or check "
        "an entity's compliance/trust tier. Load verifarms://schema/gold-layer first to "
        "understand the graph. This server cannot modify data."
    ),
)

# Dependency-injected, read-only service (mock by default; neo4j via MCP_BACKEND).
_service = get_read_service()


# ---------------------------------------------------------------------------
# Tools (read-only).
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_verified_claims(org_id: str) -> VerifiedClaimsBundle:
    """Fetch the verified claim bundles an organization attests to.

    Returns every reified claim (land size, production volume, credit history, …)
    that the organization identified by ``org_id`` (e.g. 'ORG-TEGEMEO') has
    attested, each with its value, confidence, attesting-source trust, and whether
    the source is authoritative. Use this to ground answers about what an
    organization has verified about its farmers.
    """
    return await _service.get_verified_claims(org_id)


@mcp.tool()
async def trace_provenance(claim_id: str) -> ProvenanceTrace:
    """Trace a verified claim's lineage back to its original source system.

    Given a ``claim_id``, returns the attesting institution, the original source
    system the claim came from (e.g. 'sentinel2:<scene>', 'tegemeo_cereals:registry'),
    when it was observed, and an ordered lineage (source → attestation → subject).
    Use this to answer "where did this number come from and can I trust it?".
    """
    trace = await _service.trace_provenance(claim_id)
    if trace is None:
        raise ValueError(f"Claim {claim_id!r} not found.")
    return trace


@mcp.tool()
async def check_compliance_status(entity_name: str) -> ComplianceStatus:
    """Look up an entity's aggregated trust tier / compliance status.

    Accepts an institution id or name (e.g. 'ORG-TEGEMEO' or 'Tegemeo Cereals')
    and returns its trust tier — 'authoritative' | 'trusted' | 'provisional' |
    'unverified' — its trust score, and a boolean 'verified' flag. Use this for a
    quick safety/eligibility gate before relying on an entity's attestations.
    """
    return await _service.check_compliance(entity_name)


# ---------------------------------------------------------------------------
# Resources (context injection).
# ---------------------------------------------------------------------------


@mcp.resource("verifarms://schema/gold-layer")
def gold_layer_schema() -> str:
    """Static: node/edge topology of the gold layer, for the agent to read first."""
    return SCHEMA_TEXT


@mcp.resource("verifarms://orgs/{org_id}/summary")
async def org_summary(org_id: str) -> str:
    """Dynamic: a concise overview profile of one organization for context."""
    summary = await _service.org_summary(org_id)
    if summary is None:
        return f"Organization {org_id!r} not found in the gold layer."
    return (
        f"# {summary.name or summary.org_id} ({summary.org_id})\n"
        f"- type: {summary.type}\n"
        f"- trust_score: {summary.trust_score:.2f}  (tier: {summary.tier})\n"
        f"- authoritative: {summary.authoritative}\n"
        f"- verified claims: {summary.claim_count}\n"
    )


# ---------------------------------------------------------------------------
# Transports.
# ---------------------------------------------------------------------------


def build_sse_app():
    """Return an ASGI app for SSE transport — mount on FastAPI/Starlette.

        from app.mcp.server import build_sse_app
        app.mount("/mcp", build_sse_app())   # FastAPI
    """
    return mcp.sse_app()


if __name__ == "__main__":
    # stdio for local agents/Claude Desktop; set MCP_TRANSPORT=sse for HTTP.
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))
