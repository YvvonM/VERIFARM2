"""verifarms-mcp-remote — multi-tenant, remote, read-only MCP gateway.

Architecture / lifecycle:

    HTTP POST /mcp  ─►  AuthContextMiddleware (resolve Bearer → SessionContext,
                         set request-scoped ContextVar)  ─►  FastMCP streamable-HTTP
                         handler  ─►  @tool / @resource  ─►  current_session() reads
                         the tenant  ─►  tenancy checks  ─►  read-only service

Auth runs *before* MCP at the ASGI layer, so an unauthenticated request is 401'd
before any tool is reachable; and because the session lives in a ContextVar set
per request, the gateway is **stateless** (no server-side session store) and safe
to run behind a load balancer with many replicas.

Run remote:  uvicorn app.mcp.remote:get_app --factory --port 9000
Or mount on the main API:  app.mount("/mcp", AuthContextMiddleware(remote_mcp.streamable_http_app()))
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from app.mcp.auth import AuthContextMiddleware, current_session
from app.mcp.models import ComplianceStatus, ProvenanceTrace, VerifiedClaimsBundle
from app.mcp.service import SCHEMA_TEXT, get_read_service
from app.mcp.tenancy import AccessDenied, authorize_resource, check_claims_access

# stateless_http=True ⇒ no per-session server state ⇒ horizontally scalable.
remote_mcp = FastMCP(
    "verifarms-mcp-remote",
    instructions=(
        "Multi-tenant, read-only access to the VeriFarms gold layer. You are scoped "
        "to a single organization by your access token; requests for another org's "
        "claims or resources are refused. Load verifarms://session to see your identity."
    ),
    stateless_http=True,
)

_service = get_read_service()


# ---------------------------------------------------------------------------
# Tenant-scoped tools. A union return (`... | AccessDenied`) gives the model a
# safe, structured refusal on a cross-tenant / under-scoped request.
# ---------------------------------------------------------------------------


@remote_mcp.tool()
async def get_verified_claims(target_org: str) -> VerifiedClaimsBundle | AccessDenied:
    """Fetch verified claim bundles for an organization you are authorized to read.

    ``target_org`` MUST equal your authenticated organization — cross-tenant
    extraction returns an ``AccessDenied`` error, not data. Requires the
    'claims:read' scope.
    """
    session = current_session()
    denied = check_claims_access(session, target_org)
    if denied is not None:
        return denied
    return await _service.get_verified_claims(target_org)


@remote_mcp.tool()
async def trace_provenance(claim_id: str) -> ProvenanceTrace | AccessDenied:
    """Trace a claim's lineage — but only for claims your organization attests to.

    Returns ``AccessDenied`` if the claim belongs to another tenant. Requires the
    'claims:read' scope.
    """
    session = current_session()
    if not ("claims:read" in session.scopes or "*" in session.scopes):
        return AccessDenied(error="insufficient_scope", requested_org="<claim>",
                            authorized_org=session.org_id, detail="Missing 'claims:read' scope.")
    trace = await _service.trace_provenance(claim_id)
    if trace is None:
        raise ValueError(f"Claim {claim_id!r} not found.")
    if trace.attested_by_id != session.org_id:
        return AccessDenied(requested_org=trace.attested_by_id, authorized_org=session.org_id,
                            detail="This claim is attested by another tenant.")
    return trace


@remote_mcp.tool()
async def check_compliance_status(entity_name: str) -> ComplianceStatus:
    """Look up an entity's public trust tier (no tenant claim data). Requires auth."""
    current_session()  # must be authenticated, but tier lookups aren't tenant-scoped
    return await _service.check_compliance(entity_name)


# ---------------------------------------------------------------------------
# Resources — context scoping enforced on the dynamic URI.
# ---------------------------------------------------------------------------


@remote_mcp.resource("verifarms://orgs/{org_id}/summary")
async def org_summary(org_id: str) -> str:
    """Dynamic org profile — refused (load rejected) for any org but your own."""
    session = current_session()
    authorize_resource(session, org_id)  # raises PermissionError on cross-tenant → rejected
    summary = await _service.org_summary(org_id)
    if summary is None:
        return f"Organization {org_id!r} not found."
    return (
        f"# {summary.name or org_id} ({org_id})\n"
        f"- tier: {summary.tier} (trust {summary.trust_score:.2f})\n"
        f"- authoritative: {summary.authoritative}\n"
        f"- verified claims: {summary.claim_count}\n"
    )


@remote_mcp.resource("verifarms://session")
def session_info() -> str:
    """Static-per-session: the caller's resolved tenant identity + scopes."""
    s = current_session()
    return f"org_id: {s.org_id}\nscopes: {', '.join(s.scopes) or '(none)'}"


@remote_mcp.resource("verifarms://schema/gold-layer")
def gold_layer_schema() -> str:
    """The gold-layer topology (same for every tenant)."""
    return SCHEMA_TEXT


# ---------------------------------------------------------------------------
# ASGI host — mount the streamable-HTTP app behind the auth gate on FastAPI.
# ---------------------------------------------------------------------------


def get_app():
    """Build the FastAPI host: /mcp = auth gate → FastMCP streamable HTTP."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    mcp_asgi = remote_mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: "FastAPI"):
        # Run the MCP session manager for the lifetime of the host app.
        async with remote_mcp.session_manager.run():
            yield

    app = FastAPI(title="verifarms-mcp-remote", lifespan=lifespan)
    # Auth gate wraps the MCP app and is scoped to the /mcp mount only.
    app.mount("/mcp", AuthContextMiddleware(mcp_asgi))
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(get_app(), host="0.0.0.0", port=int(os.environ.get("MCP_PORT", "9000")))
