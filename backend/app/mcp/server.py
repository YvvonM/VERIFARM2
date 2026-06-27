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

import asyncio
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from app.mcp.models import (
    ComplianceStatus,
    CooperativePortfolio,
    EligibilityRuleOutcome,
    EligibleFarmersResult,
    EligibleFarmerSummary,
    FarmerEligibilityResult,
    ProvenanceTrace,
    VerificationSource,
    VerificationSourcesResult,
    VerifiedClaimsBundle,
    VerifiedHistoryResult,
)
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
# Farmer / portfolio / eligibility tools — call existing app.database.* /
# app.api.lender functions directly via app.database.neo4j_client.get_driver(),
# rather than through the GraphReadService abstraction above. No new Cypher is
# written here; every Cypher statement these tools execute already exists
# elsewhere in the codebase and is read-only by construction (match_engine,
# trust_graph, profile_queries, consumer_queries, app.api.lender never write).
# ---------------------------------------------------------------------------

_driver = None  # lazy singleton; created on first tool call, not at import time.


def _get_shared_driver():
    global _driver
    if _driver is None:
        from app.database.neo4j_client import get_driver

        _driver = get_driver()
    return _driver


@mcp.tool()
async def get_eligible_farmers(
    crop_type: Optional[str] = None,
    region: Optional[str] = None,
    min_land_hectares: Optional[float] = None,
    min_trust_score: float = 0.5,
    product_type: Optional[str] = None,
) -> EligibleFarmersResult:
    """Find farmers whose verified claims clear the given thresholds.

    Filters on crop type, region, minimum verified land size, and the minimum
    trust score an attesting institution must clear (claims with a
    self-reported/unapproved source never count — see app.database.trust_graph).
    ``product_type`` optionally narrows to a specific catalog product id (e.g.
    'smallholder_crop_loan'); every farmer's ``matched_products`` lists which
    catalog products they are currently eligible for. Never returns phone_number.
    """

    def _work() -> EligibleFarmersResult:
        from app.api.lender import _query_eligible_farmers
        from app.database import match_engine
        from app.services.product_catalog import get_product, list_products

        driver = _get_shared_driver()
        total, rows = _query_eligible_farmers(
            driver, min_trust_score, crop_type, region, min_land_hectares, skip=0, limit=50
        )

        if product_type:
            try:
                products = [get_product(product_type)]
            except KeyError:
                products = []
        else:
            products = list_products()

        farmers: list[EligibleFarmerSummary] = []
        for row in rows:
            sources = row.get("verification_sources") or []
            trust = max((s.get("source_trust", 0.0) for s in sources), default=None)
            matched = [
                p.product_id
                for p in products
                if match_engine.evaluate_product(driver, row["farmer_id"], p)["eligible"]
            ]
            farmers.append(
                EligibleFarmerSummary(
                    farmer_id=row["farmer_id"],
                    cooperative_name=row.get("cooperative_name"),
                    crop_types=[c for c in (row.get("crop_types") or []) if c],
                    verified_land_hectares=row.get("verified_land_hectares"),
                    trust_score=trust,
                    matched_products=matched,
                )
            )
        return EligibleFarmersResult(total=total, farmers=farmers)

    return await asyncio.to_thread(_work)


@mcp.tool()
async def get_farmer_verified_history(farmer_id: str, requesting_institution_id: str) -> VerifiedHistoryResult:
    """Fetch a farmer's verified claim history, gated on consent.

    Requires ``requesting_institution_id`` to hold an APPROVED [:GRANTED_ACCESS]
    grant to ``farmer_id`` (see app.database.consent). When no such grant
    exists, this returns ``consent_granted=False`` and NO history data at
    all — never an empty-but-present history. The consent gate is never
    bypassed, including for the calling institution's own benefit.
    """

    def _work() -> VerifiedHistoryResult:
        from app.database.profile_queries import get_verified_history_gated

        driver = _get_shared_driver()
        profile = get_verified_history_gated(driver, requesting_institution_id, farmer_id)
        if profile is None:
            return VerifiedHistoryResult(
                farmer_id=farmer_id,
                consent_granted=False,
                message="consent not granted",
            )
        # Strip phone_number explicitly -- farmer_id and phone must never travel together.
        history = profile.get("verified_history") or {}
        return VerifiedHistoryResult(
            farmer_id=farmer_id, consent_granted=True, verified_history=history
        )

    return await asyncio.to_thread(_work)


@mcp.tool()
async def get_cooperative_portfolio(cooperative_id: str) -> CooperativePortfolio:
    """Anonymized portfolio aggregate for a cooperative/off-taker institution.

    Member counts, total verified hectares, unverified-member count, and
    missing-credit-history count — never a per-farmer id or phone number (see
    app.database.consumer_queries.get_cooperative_stats, which this calls).
    """

    def _work() -> CooperativePortfolio:
        from app.database.consumer_queries import get_cooperative_stats

        driver = _get_shared_driver()
        stats = get_cooperative_stats(driver, cooperative_id)
        if stats is None:
            return CooperativePortfolio(institution_id=cooperative_id, found=False)
        return CooperativePortfolio(found=True, **stats)

    return await asyncio.to_thread(_work)


@mcp.tool()
async def check_farmer_eligibility(farmer_id: str, product_id: str) -> FarmerEligibilityResult:
    """Evaluate one farmer against one financial product's eligibility rules.

    Runs the existing data-driven MATCH engine (app.database.match_engine) —
    no eligibility logic is duplicated here. Returns a 404-shaped
    ``farmer_found=False`` result rather than raising when the farmer is
    unknown; an unknown ``product_id`` raises ``ValueError`` (caller error).
    """

    def _work() -> FarmerEligibilityResult:
        from app.database import match_engine
        from app.services.product_catalog import get_product

        driver = _get_shared_driver()
        try:
            product = get_product(product_id)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        if not match_engine.farmer_exists(driver, farmer_id):
            return FarmerEligibilityResult(farmer_id=farmer_id, product_id=product_id, farmer_found=False)

        result = match_engine.evaluate_product(driver, farmer_id, product)
        return FarmerEligibilityResult(
            farmer_id=farmer_id,
            product_id=product_id,
            farmer_found=True,
            eligible=result["eligible"],
            rule_breakdown=[EligibilityRuleOutcome(**r) for r in result["rule_breakdown"]],
        )

    return await asyncio.to_thread(_work)


@mcp.tool()
async def get_verification_sources(farmer_id: str) -> VerificationSourcesResult:
    """List every verified claim source backing a farmer's profile.

    For each claim_type the farmer has, returns every sufficiently-trusted
    attestation (app.database.trust_graph.verify_claim) — institution name,
    trust score, whether it is authoritative/corroborated, and when it was
    observed. Never includes phone_number, gender, or ethnicity.
    """

    def _work() -> VerificationSourcesResult:
        from app.database.profile_queries import get_verified_history
        from app.database.trust_graph import verify_claim

        driver = _get_shared_driver()
        profile = get_verified_history(driver, farmer_id)
        claim_types = list((profile or {}).get("verified_history") or {})

        sources: list[VerificationSource] = []
        for claim_type in claim_types:
            for row in verify_claim(driver, farmer_id, claim_type, min_trust_score=0.0):
                sources.append(
                    VerificationSource(
                        claim_type=row["claim_type"],
                        value=row.get("value"),
                        value_numeric=row.get("value_numeric"),
                        attested_by=row.get("attested_by"),
                        institution_trust=row.get("institution_trust", 0.0),
                        authoritative=row.get("authoritative", False),
                        corroborated=row.get("corroborated", False),
                        observed_at=str(row.get("observed_at")) if row.get("observed_at") else None,
                    )
                )
        return VerificationSourcesResult(farmer_id=farmer_id, sources=sources)

    return await asyncio.to_thread(_work)


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
