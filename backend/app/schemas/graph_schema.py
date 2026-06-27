"""
Single source of truth for the VeriFarm graph schema — two coexisting layers.

This file used to document a "gold-layer" shape built around
``(:Claim)-[:VERIFIED_BY]->(:Organization)``. That shape has been removed.
Trust/verification claims are now reified ONLY as::

    (:Institution)-[:ATTESTS_TO]->(:Claim {claim_type, value_numeric, ...})-[:BELONGS_TO]->(:Farmer)

This matches the write path in :mod:`app.database.graph_ingestion` and the
read path in :mod:`app.database.trust_graph` / :mod:`app.database.profile_queries`
/ :mod:`app.database.match_engine`. Nothing in the codebase should write or read
``VERIFIED_BY`` or treat ``Organization`` as a claim verifier — ``Organization``
nodes are retained only for the REGISTRY layer below (membership, transactions,
demographics), which carries no per-claim provenance and is never used for
trust traversal or eligibility.

Cooperatives are the primary verification entry point (see
``POST /api/v1/cooperative/onboard``): a cooperative's existing member records
become pre-verified Claims attested by the cooperative's Institution node, not
self-reported by the farmer.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Reified trust layer — the ONLY mechanism for verification / trust traversal.
# ---------------------------------------------------------------------------

# Approved provenance for a Claim. A claim with no qualifying external source
# never enters this enum — it stays a PendingClaim (status: unverified) and is
# invisible to trust traversal. "self_reported" is deliberately absent.
SOURCE_CATEGORIES: list[str] = [
    "cooperative",
    "off_taker",
    "government",
    "remote_sensing",
    "field_officer",
]

CONSENT_SCOPES: list[str] = ["single_institution", "category", "universal"]

REIFIED_NODE_SCHEMA: dict[str, dict[str, str]] = {
    "Institution": {
        "id": "string, unique",
        "name": "string",
        "type": "string, e.g. Cooperative|OffTaker|Satellite|GovernmentRegistry|Lender",
        "is_authoritative": "boolean — ground-truth source (satellite, government registry)",
        "trust_score": "float, 0.0-1.0, global reputation; recomputed vs ground truth",
        "can_originate_claims": "boolean — true for cooperative|off_taker|government|remote_sensing; false for lenders",
        "minimum_onboarding_trust": "float, 0.0-1.0 — seed trust (0.5) until corroborated by an authoritative source",
        "consent_at_source": "boolean — true when farmers already consented at collection time",
    },
    "Claim": {
        "id": "string, unique",
        "claim_type": "string VALUE, e.g. land_size_hectares|production_volume_kg|credit_history",
        "value_numeric": "float, nullable",
        "value_string": "string, nullable",
        "unit": "string, nullable",
        "source_category": "string, enum: " + "|".join(SOURCE_CATEGORIES) + " (required; no self_reported)",
        "confidence": "float, 0.0-1.0",
        "timestamp": "datetime (ISO 8601)",
    },
    "PendingClaim": {
        "id": "string, unique",
        "claim_type": "string",
        "value_numeric": "float, nullable",
        "value_string": "string, nullable",
        "status": "string, fixed: unverified — never read by trust traversal",
        "submitted_at": "datetime (ISO 8601)",
    },
    "Farmer": {
        "id": "string, unique",
        "phone_number": "string, nullable",
        "verified": "boolean — CACHED/COMPUTED CONVENIENCE FLAG ONLY. Never the source of truth "
        "for trust traversal or eligibility; those always re-check Claim/Institution.trust_score.",
    },
}

REIFIED_RELATIONSHIP_SCHEMA: list[tuple[str, str, str]] = [
    ("Institution", "ATTESTS_TO", "Claim"),
    ("Claim", "BELONGS_TO", "Farmer"),
    ("Claim", "CONFLICTS_WITH", "Claim"),
    # A production-volume claim backed by a real off-taker sale (registry
    # layer) -- the one deliberate cross-layer edge in the schema.
    ("Claim", "SUPPORTED_BY", "Transaction"),
    # Corroboration: two independent sources agree on the same claim (e.g.
    # cooperative land size within 15% of satellite land size). Corroborated
    # claims rank above single-source claims in trust traversal output.
    ("Claim", "CORROBORATED_BY", "Claim"),
    # A farmer's unverified self-report can disagree with a verified Claim;
    # tracked for audit, but PendingClaim itself never enters trust traversal.
    ("PendingClaim", "CONFLICTS_WITH", "Claim"),
    ("PendingClaim", "BELONGS_TO", "Farmer"),
    ("Institution", "GRANTED_ACCESS", "Farmer"),
    ("Institution", "REQUESTED_ACCESS", "DataAccessRequest"),
    ("DataAccessRequest", "TO_FARMER", "Farmer"),
]

REIFIED_RELATIONSHIP_PROPERTIES: dict[tuple[str, str, str], dict[str, str]] = {
    ("Institution", "GRANTED_ACCESS", "Farmer"): {
        "status": "string, enum: APPROVED",
        "basis": "string, e.g. COLLECTION|REQUEST",
        "scope": "string, enum: " + "|".join(CONSENT_SCOPES),
        "granted_at": "datetime (ISO 8601)",
    },
}

# ---------------------------------------------------------------------------
# Registry layer — synthetic/demographic base records. NEVER used for trust
# traversal or eligibility; no Claim or VERIFIED_BY-style edge lives here.
# ---------------------------------------------------------------------------

REGISTRY_NODE_SCHEMA: dict[str, dict[str, str]] = {
    "Farmer": {
        "id": "string, unique",
        "name": "string",
        "phone": "string",
        "location": "string",
        "country": "string",
        "verified": "boolean (cached convenience flag — see REIFIED_NODE_SCHEMA note)",
        "consent_signed": "boolean (coarse flag; per-institution detail lives in GRANTED_ACCESS)",
    },
    "FarmHolding": {
        "id": "string, unique",
        "size_hectares": "float (self-reported figure)",
        "latitude": "float",
        "longitude": "float",
        "soil_type": "string",
    },
    "CropCycle": {
        "id": "string, unique",
        "crop_type": "string",
        "season": "string",
        "planted_at": "date",
        "harvest_estimate_tons": "float",
        "status": "string",
    },
    "Transaction": {
        "id": "string, unique",
        "type": "string, enum: INPUT_LOAN|GRAIN_SALE",
        "amount": "float",
        "date": "date",
        "status": "string",
    },
    "Organization": {
        "id": "string, unique",
        "name": "string",
        "type": "string, e.g. Tegemeo|Agrovesto",
        "org_role": "string, enum: off_taker|cooperative|lender|mobile_money_provider",
    },
}

REGISTRY_RELATIONSHIP_SCHEMA: list[tuple[str, str, str]] = [
    ("Farmer", "OWNS", "FarmHolding"),
    ("FarmHolding", "HAS_CYCLE", "CropCycle"),
    ("Farmer", "EXECUTED", "Transaction"),
    ("Transaction", "BELONGS_TO", "Organization"),
    ("Farmer", "MEMBER_OF", "Organization"),
]

REGISTRY_RELATIONSHIP_PROPERTIES: dict[tuple[str, str, str], dict[str, str]] = {}

# ---------------------------------------------------------------------------
# Combined view (back-compat name for callers that want "everything").
# ---------------------------------------------------------------------------

# Merge per-label (Farmer is declared in both layers; its property set is the
# union, never one layer's dict clobbering the other's).
NODE_SCHEMA: dict[str, dict[str, str]] = {}
for _label, _props in {**REGISTRY_NODE_SCHEMA, **REIFIED_NODE_SCHEMA}.items():
    NODE_SCHEMA[_label] = {
        **REGISTRY_NODE_SCHEMA.get(_label, {}),
        **REIFIED_NODE_SCHEMA.get(_label, {}),
    }
del _label, _props
RELATIONSHIP_SCHEMA: list[tuple[str, str, str]] = (
    REGISTRY_RELATIONSHIP_SCHEMA + REIFIED_RELATIONSHIP_SCHEMA
)
RELATIONSHIP_PROPERTIES: dict[tuple[str, str, str], dict[str, str]] = {
    **REGISTRY_RELATIONSHIP_PROPERTIES,
    **REIFIED_RELATIONSHIP_PROPERTIES,
}

# Fields deliberately excluded from any scoring-relevant node/relationship,
# per the proposal's responsible-AI section. Not enforced by the type system
# below (Neo4j won't stop you adding a property at write time), but flagged
# here so Cypher generation and risk-scoring prompts never reference them.
EXCLUDED_FROM_SCORING: list[str] = ["gender", "ethnicity"]


def render_schema_for_prompt() -> str:
    """
    Render the schema as compact text for injection into the NL->Cypher
    system prompt. Keep this terse -- token budget matters and verbose
    schema dumps invite the model to hallucinate properties that "sound"
    plausible from over-explanation.
    """
    lines = ["NODES:"]
    for label, props in NODE_SCHEMA.items():
        prop_names = ", ".join(props.keys())
        lines.append(f"  ({label} {{{prop_names}}})")

    lines.append("\nRELATIONSHIPS:")
    for start, rel, end in RELATIONSHIP_SCHEMA:
        rel_props = RELATIONSHIP_PROPERTIES.get((start, rel, end))
        if rel_props:
            prop_str = ", ".join(rel_props.keys())
            lines.append(f"  ({start})-[:{rel} {{{prop_str}}}]->({end})")
        else:
            lines.append(f"  ({start})-[:{rel}]->({end})")

    return "\n".join(lines)


@dataclass
class SchemaValidationResult:
    is_valid: bool
    unknown_node_labels: list[str] = field(default_factory=list)
    unknown_relationship_types: list[str] = field(default_factory=list)
    unknown_relationship_properties: list[str] = field(default_factory=list)


def validate_node_labels(labels_used: list[str]) -> SchemaValidationResult:
    """
    Cheap static check: do the node labels referenced in a generated Cypher
    query actually exist in our schema? This is NOT a substitute for running
    against live Neo4j, but it catches obvious hallucinations (e.g. the LLM
    inventing a `:LoanOfficer` node) before you waste a round-trip to the DB.
    """
    known = set(NODE_SCHEMA.keys())
    unknown = [label for label in labels_used if label not in known]
    return SchemaValidationResult(
        is_valid=len(unknown) == 0,
        unknown_node_labels=unknown,
    )


def validate_relationship_types(rel_types_used: list[str]) -> SchemaValidationResult:
    """
    Cheap static check on relationship types specifically (distinct from
    node labels, since both use Cypher's `:Token` syntax and generate_cypher's
    label extractor doesn't distinguish them). Catches a hallucinated
    relationship like `:VERIFIED_DIRECTLY_BY` that sounds plausible but
    doesn't exist.
    """
    known = {rel for _, rel, _ in RELATIONSHIP_SCHEMA}
    unknown = [r for r in rel_types_used if r not in known]
    return SchemaValidationResult(
        is_valid=len(unknown) == 0,
        unknown_relationship_types=unknown,
    )


def get_relationship_properties(start_label: str, rel_type: str, end_label: str) -> dict[str, str]:
    """
    Look up the expected properties for a specific relationship triple.
    Returns an empty dict if the relationship carries no properties (true
    for most relationships in this schema) or doesn't exist at all.
    """
    return RELATIONSHIP_PROPERTIES.get((start_label, rel_type, end_label), {})
