# VERIFARMS

**Farmer Verification & GenUI Agricultural Dashboard for fintech orgs.**

VERIFARMS turns a graph of farmer registry data (Tegemeo — Kenya, and Agrovesto
— Nigeria) into a conversational, generative-UI dashboard. A user asks a
natural-language question; a supervisor agent (an intent router over vetted tools
+ a free-form Graph-RAG Cypher path) queries Neo4j, shapes the result into typed
UI component payloads, and streams both progress updates and rendered components
to the frontend over Server-Sent Events. LangChain drives the LLM/tool layer
(`ChatOpenAI` + `bind_tools`); the ReAct loops are plain Python (no LangGraph).

## Architecture

```
 Next.js GenUI  ── GET /api/chat (SSE) ──►  FastAPI Streaming API
   (frontend)   ◄── status + component ────   (backend / supervisor copilot)
                       chunks                        │
                                                     ▼
                                              Neo4j Graph DB
                                                     ▲
                                                     │ batch ingest
                                              Synthetic data pipeline
```

## Milestone status

| # | Milestone | Area | Status |
|---|-----------|------|--------|
| 1 | Data Engineering & Graph Modeling | `data-pipeline/` | ✅ Implemented |
| — | Schema unification: single reified model, no gold-layer `VERIFIED_BY`/`Organization`-as-verifier shape | `backend/app/schemas/graph_schema.py`, `database/neo4j_client.py` | ✅ Implemented |
| — | Ingestion API & Dynamic Validator | `backend/app/ingestion/`, `backend/app/api/ingest.py` | ✅ Implemented (writes reified bundles via `claim_bridge`, not the old `VERIFIED_BY` row format) |
| — | Silver gateway: reified `PayloadBundle` validation + DLQ | `backend/app/ingestion/gateway.py`, `dlq.py` | ✅ Implemented |
| — | `Claim.source_category` enum (no `self_reported`); unsourced figures are `PendingClaim` | `backend/app/models/reified.py`, `database/trust_graph.py` | ✅ Implemented |
| — | `CORROBORATED_BY` cross-source agreement + trust-traversal ranking | `backend/app/database/graph_ingestion.py`, `trust_graph.py` | ✅ Implemented |
| — | Cooperative-first onboarding (`POST /api/v1/cooperative/onboard`) | `backend/app/api/cooperative.py` | ✅ Implemented |
| — | Lender query layer (`GET /api/v1/lender/eligible-farmers`) | `backend/app/api/lender.py` | ✅ Implemented |
| — | `Institution.can_originate_claims` / `minimum_onboarding_trust` | `backend/app/models/reified.py`, `database/graph_ingestion.py` | ✅ Implemented |
| — | Structured `ConsentScope` (`single_institution`\|`category`\|`universal`), replacing freetext `scope` | `backend/app/models/consent.py`, `database/consent.py` | ✅ Implemented |
| — | Neo4j Infra & Idempotent Reified Ingestion | `docker-compose.yml`, `backend/app/database/graph_ingestion.py` | ✅ Implemented |
| — | Dynamic Trust Traversal & Generalized Reputation | `backend/app/database/trust_graph.py` | ✅ Implemented (analytics-only) |
| — | Verification sources (Sentinel-2 NDVI, paper-register OCR) | `backend/app/verification/` | ✅ Implemented |
| — | MATCH engine (financial eligibility rules) | `backend/app/api/match.py`, `database/match_engine.py` | ✅ Implemented |
| — | Farmer consent & data-access control | `backend/app/api/consent.py`, `database/consent.py` | ✅ Implemented |
| — | Gold consumer APIs (loan officer / farmer / macro) | `backend/app/api/gold.py`, `profiles.py` | ✅ Implemented |
| 2 | Loan Officer Copilot (supervisor + ReAct; LangChain LLM layer + Featherless/Qwen3) | `backend/app/agent/` | ✅ Implemented (mock fallback when no key) |
| — | Autonomous DLQ Investigator (background data-quality agent) | `backend/app/investigator/`, `backend/app/api/investigator.py` | ✅ Implemented |
| 3 | Streaming API Layer (SSE) | `backend/app/api/`, `backend/main.py` | ✅ Implemented |
| 4 | React/Next.js GenUI Interface | `frontend/` | ✅ Copilot chat + cooperative onboarding (`/cooperative/onboard`) + partner portal (`/partner`, `/partner/search`, `/partner/download`); `Insight` GenUI component implemented; shared `PortalNav` links all three. `npm run build` passes (compiles, lints, type-checks, prerenders all 6 routes). No `src/components/ui` Shadcn primitives are actually present yet despite earlier docs implying otherwise — every page uses plain Tailwind. |
| — | `legacy-frontend-prototype/` (formerly `chris frontend/`, renamed to drop the illegal space) | `legacy-frontend-prototype/` | ⬜ Unreferenced Vite/React prototype, kept for reference, not wired into the build |
| — | MCP server (`verifarms-mcp-server`) — 8 read-only tools over the gold layer | `backend/app/mcp/`, `backend/run_mcp.py` | ✅ Implemented — see "MCP server" section below |
| — | Partner Portal (dashboard, search, CSV/JSON download) | `frontend/src/app/partner/` | ✅ Implemented |
| 5 | Open-source docs & demo scripts | this file | 🟡 In progress |

> **Verification note.** The backend modules above compile and were exercised
> end-to-end at the API/model layer (FastAPI + Pydantic V2) with the graph layer
> faked. The Cypher itself is reviewed but, except where noted, has not been
> re-run against a live Neo4j since the reified-schema consolidation.

## Project structure

```
.
├── .env                          # Featherless API key + Neo4j credentials (git-ignored)
├── .gitignore
├── docker-compose.yml            # Local Neo4j 5 + APOC (no-auth dev instance)
├── README.md
│
├── data-pipeline/                # Milestone 1: Data Engineering & Graph Modeling
│   ├── requirements.txt          # faker, pandas, neo4j, python-dotenv
│   ├── raw/                      # Git-ignored; original/generated CSVs land here
│   ├── schemas/                  # OpenSPP / FAO data-standard mappings
│   ├── generate_synthetic.py     # Faker generator → SyntheticDataset (1k farmers)
│   └── neo4j_loader.py           # Idempotent UNWIND batch ingestion into Neo4j
│
├── backend/                      # Agent, streaming, ingestion, trust & consumer APIs
│   ├── requirements.txt
│   ├── main.py                   # FastAPI app: CORS, lifespan, /health, routers, uvicorn boot
│   └── app/
│       ├── api/
│       │   ├── chat_stream.py    # SSE engine + GET /api/chat endpoint
│       │   ├── ingest.py         # POST /ingest/records (adapter + DLQ + persist)
│       │   ├── match.py          # POST /match/{farmer_id} — financial eligibility
│       │   ├── profiles.py       # GET /api/v1/profiles/{id}/verified-history
│       │   ├── consent.py        # POST /api/v1/consent/{request,resolve,source-grant}
│       │   ├── gold.py           # Gold consumer routes: loan-officer / farmer / macro
│       │   └── investigator.py   # POST /run + GET /flags for the DLQ Investigator
│       ├── investigator/         # Autonomous DLQ Investigator (data-quality agent)
│       │   ├── policy.py         # Deterministic resolution policy (pure, testable)
│       │   ├── graph_ops.py      # Conflict discovery (w/ ids) + flag persistence Cypher
│       │   ├── investigator.py   # DLQInvestigator orchestration + optional LLM narration
│       │   └── worker.py         # Background loop (FastAPI task) + standalone CLI
│       ├── ingestion/
│       │   ├── adapters.py       # Config-driven source adapters (Adapter Pattern)
│       │   ├── sql_adapters.py   # External SQL rows → PayloadBundle (e.g. Tegemeo)
│       │   ├── gateway.py        # process_incoming_batch: validate-or-quarantine (Silver)
│       │   └── dlq.py            # Dead-Letter Queue (function + DeadLetterQueue class → JSONL)
│       ├── verification/         # Verification sources that emit reified claims
│       │   ├── ndvi_crosscheck.py    # Sentinel-2 NDVI cultivated-area proxy (Earth Engine)
│       │   ├── ocr_preprocessor.py   # Tesseract paper-register OCR → OCRClaim
│       │   ├── claim_bridge.py       # Facts → reified bundles + ClaimBridge (credit/identity seam)
│       │   ├── providers/            # External integration seam (no mock data)
│       │   │   ├── types.py          #   Pydantic API contracts (Credit/Identity results)
│       │   │   ├── base.py           #   async Protocol interfaces
│       │   │   └── factory.py        #   env-driven factory; raises NotConfigured
│       │   └── ocr/                  # Featherless-vision OCR pipeline
│       │       ├── pipeline.py       #   image → OCRClaim (Qwen vision)
│       │       └── ingest.py         #   OCRClaim → claim_bridge → GraphIngestionService (reified)
│       ├── agent/                # Loan Officer Copilot — supervisor + ReAct (LangChain LLM layer)
│       │   ├── graph.py          # SSE stream entrypoint: delegates to copilot, else mock
│       │   ├── copilot.py        # Supervisor: router → operational/analytical ReAct → synthesis
│       │   ├── router.py         # Intent router (fast-path + fast-LLM): operational vs analytical
│       │   ├── tools.py          # Operational path: vetted tools (Pydantic args + OpenAI specs)
│       │   ├── cypher_tool.py    # Analytical path: CypherExecutionTool (query + rationale)
│       │   ├── cypher_guard.py   # Read-only validation + bounded exec for free-form Cypher
│       │   ├── render.py         # Deterministic result → BarChart/Table component
│       │   ├── events.py         # SSE status/component envelope helpers
│       │   ├── prompts.py        # Router / operational / analytical / synthesis prompts
│       │   └── qwen_llm.py       # Featherless (OpenAI-compatible) client + chat_completion
│       ├── models/
│       │   ├── ui_schemas.py     # Pydantic v2 SSE envelopes + BarChartProps
│       │   ├── claims.py         # StandardFarmerClaim + ingestion response models
│       │   ├── reified.py        # Institution / Farmer / Claim / PayloadBundle (canonical)
│       │   ├── products.py       # FinancialProduct + eligibility rules + match models
│       │   ├── profiles.py       # FarmerProfileResponse (verified-history)
│       │   ├── consent.py        # Access-request / resolution / source-consent models
│       │   └── consumer.py       # Farmer-view + macro-stats response models
│       ├── services/
│       │   └── product_catalog.py  # Declarative FinancialProduct catalog
│       └── database/
│           ├── neo4j_client.py       # Legacy VERIFIED_BY edge path + shared driver helpers
│           ├── graph_ingestion.py    # GraphIngestionService — single reified write surface
│           ├── trust_graph.py        # Reified traversal + reputation (read/analytics only)
│           ├── match_engine.py       # Eligibility Cypher + evaluator
│           ├── profile_queries.py    # Verified-history aggregation (+ consent-gated variant)
│           └── consumer_queries.py   # Farmer-view + macro portfolio queries
│
└── frontend/                     # Milestone 4: React/Next.js GenUI Interface
    ├── package.json
    ├── tailwind.config.ts
    └── src/
        ├── app/                  # page.tsx, layout.tsx, globals.css
        ├── components/
        │   ├── ui/               # Shadcn primitives
        │   ├── charts/           # Recharts wrappers (BarChart, PieChart, …)
        │   └── genui/
        │       └── ComponentRegistry.tsx  # Maps backend types → React components
        └── lib/
            ├── sse_client.ts     # Consumes/parses the SSE stream
            └── utils.ts          # Tailwind class merge helpers
```

## Graph schema

> **Status note (unified):** earlier drafts of this README described a
> "gold-layer" shape — `(:Claim)-[:VERIFIED_BY]->(:Organization)` — as a
> separate, parallel schema alongside a "reified" one. That divergence has
> been resolved: the reified model below
> (`(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)`) is now
> the **only** mechanism for trust/verification anywhere in this codebase.
> `VERIFIED_BY` and "`Organization` as claim verifier" no longer exist in any
> code path — see `app/schemas/graph_schema.py` for the single source of
> truth. `Organization` is retained only as a **registry-layer** node
> (membership, transactions, demographics) and carries no claim/verification
> data; trust traversal and eligibility never read it.

### Two layers, one schema file

1. **Reified trust layer** — the only layer used for verification, trust
   scoring, and lending eligibility.
2. **Registry layer** — demographic/base records (location, crops,
   transactions, cooperative membership) used for portfolio analytics, never
   for trust decisions.

### Reified trust layer

| Label | Key properties | Notes |
|---|---|---|
| `Institution` | `id`, `name`, `type`, `is_authoritative`, `trust_score`, `can_originate_claims`, `minimum_onboarding_trust`, `consent_at_source` | The attesting actor — a cooperative, off-taker, government registry, satellite feed, or lender. `can_originate_claims` is true only for sources allowed to attest (cooperative\|off_taker\|government\|remote_sensing); lenders are always false. `minimum_onboarding_trust` (default `0.5`) caps a freshly-onboarded institution's trust until an authoritative source corroborates it — prevents a fake cooperative from self-verifying its own farmers. |
| `Claim` | `id`, `claim_type`, `value_numeric`/`value_string`, `unit`, `source_category`, `confidence`, `timestamp` | A single verified assertion. `source_category` is **required**, one of `cooperative\|off_taker\|government\|remote_sensing\|field_officer` — there is no `self_reported` member. A figure with no qualifying external source is never a `Claim`. |
| `PendingClaim` | `id`, `claim_type`, `value_numeric`/`value_string`, `status` (fixed `unverified`), `submitted_at` | A farmer's own self-report (or any unsourced figure). Structurally invisible to trust traversal — there is no query path from `VERIFY_CLAIM_QUERY` or the MATCH engine into this label. |
| `Farmer` | `id`, `phone_number`, `verified` | `verified` is a **cached convenience flag only** (e.g. for fast list rendering) — never the source of truth for trust traversal or eligibility, which always re-derive from `Claim`/`Institution.trust_score`. |

Relationships: `(Institution)-[:ATTESTS_TO]->(Claim)-[:BELONGS_TO]->(Farmer)`,
`(Claim)-[:CONFLICTS_WITH]->(Claim)`, `(Claim)-[:CORROBORATED_BY]->(Claim)`
(two independent sources agreeing within tolerance — ranks above
single-source claims in trust traversal), `(Institution)-[:GRANTED_ACCESS
{status, basis, scope, granted_at}]->(Farmer)` (consent; `scope` is the
structured `ConsentScope` enum — `single_institution`\|`category`\|`universal`
— not freetext).

### Registry layer

| Label | Key properties | Notes |
|---|---|---|
| `Farmer` | `id`, `name`, `phone`, `location`, `country`, `verified`, `consent_signed` | Shares the `id` space with the reified `Farmer` above — one node, two property sets. |
| `FarmHolding` | `id`, `size_hectares`, `latitude`, `longitude`, `soil_type` | `size_hectares` here is the self-reported figure; a competing satellite-derived figure lives as a separate reified `Claim`, never a second property on this node. |
| `CropCycle` | `id`, `crop_type`, `season`, `planted_at`, `harvest_estimate_tons`, `status` | |
| `Transaction` | `id`, `type` (`INPUT_LOAN`\|`GRAIN_SALE`), `amount`, `date`, `status` | |
| `Organization` | `id`, `name`, `type`, `org_role` | Membership/demographics only — no `reputation_score` (that lives on the mirrored `Institution.trust_score`) and no claim-verifier role. |

### Relationships

```
(:Farmer)-[:OWNS]->(:FarmHolding)
(:FarmHolding)-[:HAS_CYCLE]->(:CropCycle)
(:Farmer)-[:EXECUTED]->(:Transaction)
(:Transaction)-[:BELONGS_TO]->(:Organization)
(:Farmer)-[:MEMBER_OF]->(:Organization)

# New: claim layer
(:Claim)-[:ABOUT]->(:Farmer)
(:Claim)-[:ABOUT]->(:FarmHolding)
(:Claim)-[:VERIFIED_BY {confidence: float, method: string, date: date}]->(:Organization)
(:Claim)-[:DERIVED_FROM]->(:Document)
(:Claim)-[:CONFLICTS_WITH]->(:Claim)

# New: consent layer
(:Farmer)-[:GRANTED]->(:ConsentGrant)
(:ConsentGrant)-[:SCOPED_TO]->(:Organization)

# New: off-taker production verification, distinguished from
# cooperative self-reported figures per the proposal's strength table
(:Claim)-[:SUPPORTED_BY]->(:Transaction)
```

**Why `VERIFIED_BY` carries `confidence`/`method`/`date` as edge properties, matching the proposal's own example** —
`(:Farmer)-[:VERIFIED_BY {confidence: 0.97, method: "delivery_record", date}]->(:OffTaker)` —
rather than putting those fields on `Claim` alone: the edge is what a trust-traversal query actually filters on (*"has this farmer's production been verified by a source I trust?"* = walk `Claim-[:VERIFIED_BY]->Organization` filtered by `confidence` and the org's `reputation_score`). Keeping `confidence`/`method`/`date` on the edge keeps that query a single hop with no extra property lookup.

**Why `CONFLICTS_WITH` is its own relationship rather than a property** — anomaly/conflict detection (e.g. self-reported vs. satellite land size) is named explicitly as an AI/ML role in the proposal: *"flagging for review rather than silently picking one."* A `CONFLICTS_WITH` edge between two `Claim` nodes about the same `FarmHolding` makes that flag a graph fact a loan officer's query can surface directly, rather than logic buried in application code.

**Why off-taker delivery records and cooperative self-reports stay distinguishable** — the proposal's strength table rates off-taker delivery records *medium-strong* and cooperative-only figures *weak (flags mismatches, doesn't confirm)*. `SUPPORTED_BY` links a production `Claim` to the actual `Transaction` (grain sale) that backs it; a claim with no `SUPPORTED_BY` edge and no off-taker `VERIFIED_BY` edge is visibly weaker in any query without needing a separate "strength" field to maintain.



Schemas align with the **OpenSPP** registry and **FAO Farmer Registry** core
concepts (registrant / agricultural holding / crop production cycle /
entitlement / service provider).

> **Two graph models, by layer.** The schema above is the **gold-layer
> contract** — the single source of truth lives at
> `backend/app/schemas/graph_schema.py`:
> `Organization` + `(:Claim)-[:VERIFIED_BY]->(:Organization)` + `Document` /
> `ConsentGrant`. The **backend trust, verification, consent and consumer
> services** use the consolidated **reified** model —
> `(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)` with consent
> on `[:GRANTED_ACCESS]` edges (see the sections below). Reconciling the two
> documents into one canonical schema is tracked as open work.

## Ingestion API (`POST /ingest/records`)

The write side of the platform: a configuration-driven **Adapter Pattern**
gateway that normalizes heterogeneous third-party records into a strict
`StandardFarmerClaim`, quarantines bad records in a Dead-Letter Queue, and
idempotently upserts the survivors into Neo4j.

**Flow:** resolve adapter by `source_id` → map raw keys + convert units →
validate with Pydantic → on failure, append to the DLQ and keep going → persist
valid claims to the graph (best-effort) → return counts.

Add a new source by registering a `SourceAdapter` in
`backend/app/ingestion/adapters.py` — no other code changes. Each adapter maps
the source's native keys onto the standard schema and can apply a unit
conversion `factor` (e.g. `farm_size_acres` → `land_size_hectares` × `0.404686`).

```bash
curl -X POST "http://localhost:8000/ingest/records" \
  -H "Content-Type: application/json" \
  -d '{
        "source_id": "tegemeo_cereals",
        "records": [
          {"reg_no": "T-100", "farmer": "Jane Wanjiru", "county": "Nakuru",
           "crop": "Maize", "farm_size_acres": 5, "harvest_kg": 6000,
           "verification_score": 0.92}
        ]
      }'
```

```jsonc
// Response
{"source_id": "tegemeo_cereals", "total_processed": 1, "total_successful": 1,
 "total_failed": 0, "total_persisted": 1, "persistence": "ok",
 "dlq_path": null, "errors": []}
```

Pass `?persist=false` to validate without writing to Neo4j. Records that fail
validation are appended (with their original payload and the reason) to the DLQ
JSONL file — `backend/dlq/ingest_dlq.jsonl` by default, override with `DLQ_PATH`.

**Graph model (claim path).** Distinct from the synthetic-pipeline model above,
ingestion writes a verification edge keyed on the farmer and verifier:

```
(:Farmer)-[:VERIFIED_BY {land_size_hectares, production_volume_kg,
                         confidence_score, source_id, timestamp}]->(:Cooperative | :OffTaker)
```

The verifier label (`Cooperative` for Tegemeo, `OffTaker` for Agrovesto) is
chosen per-row via `apoc.merge.node`, which is why the local stack ships with
APOC enabled. `MERGE` on both nodes and the relationship makes re-ingestion
idempotent. `neo4j_client.py` is also runnable standalone (`python -m
app.database.neo4j_client`) for a one-claim smoke test.

## Dynamic trust traversal & generalized reputation

`backend/app/database/trust_graph.py` is the **intent-agnostic** trust layer. It
does not know in advance which metrics stakeholders will ask for (yield, land
size, organic certification, credit history, ...) or which data sources will
exist tomorrow — and it never needs a schema change to support a new one.

### Schema decision: reify the claim

Each metric is a **`(:Claim)` node**, not a property on the `[:VERIFIED_BY]` edge:

```
(:Institution)-[:ATTESTS_TO]->(:Claim {claim_type, value_numeric, value_string,
                                        unit, confidence, source_id, timestamp})-[:BELONGS_TO]->(:Farmer)
```

> **Schema consolidation.** All reified writes now go through a single surface,
> `GraphIngestionService.ingest_bundles` (`database/graph_ingestion.py`), which
> persists this exact shape from validated `PayloadBundle` objects. `trust_graph.py`
> is **read/analytics only** — its former write helpers were removed. Ground truth
> is a plain `is_authoritative: true` flag on the `:Institution` (the older
> `:GroundTruth` label was dropped). Claim direction is `(:Claim)-[:BELONGS_TO]->(:Farmer)`.

Why reification over edge-properties, for *unbounded* `claim_type`:

- **`claim_type` is a value, so it is indexable and parameterizable.** An edge
  property would make the metric a *key*; dynamic-key access (`r[$claim_type]`)
  works but can't use a schema index and degrades to a scan.
- **Per-claim provenance** — each metric carries its own confidence, unit,
  timestamp and source, instead of exploding into parallel key families.
- **Ground-truth cross-checking** is one clean pattern over `Claim` nodes.
- **Temporal history / n-ary facts** are just more nodes and edges.
- **A new metric or data source is new *data*, never a migration.**

Cost is one extra hop and more nodes — negligible with a `claim_type` index, and
far outweighed by the flexibility the requirement demands. Reserve
edge-properties for a small, fixed set of always-present attributes. The full
rationale lives in `trust_graph.SCHEMA_NOTE`.

### Part 1 — intent-agnostic traversal (`VERIFY_CLAIM_QUERY`)

Verify *any* metric for a farmer, returning the value only when backed by an
institution whose global reputation clears the threshold. Nothing is hardcoded:

```cypher
MATCH (inst:Institution)
      -[:ATTESTS_TO]->(c:Claim {claim_type: $claim_type})
      -[:BELONGS_TO]->(f:Farmer {id: $farmer_id})
WHERE coalesce(inst.trust_score, 0.0) >= $min_trust_score
RETURN c.value_string, c.value_numeric, c.confidence, c.timestamp,
       inst.name, inst.trust_score,
       coalesce(inst.is_authoritative, false) AS authoritative
ORDER BY authoritative DESC, inst.trust_score DESC, c.timestamp DESC
```

Switching `$claim_type` from `'land_size_hectares'` to `'organic_certified'`
needs no query or schema change.

### Part 2 — generalized reputation (`RECALCULATE_REPUTATION_QUERY`)

Recompute an institution's global trust score against ground truth, with **no
data source hardcoded**. "Ground truth" is any `:Institution` carrying
`is_authoritative: true` (satellite, government registry, ...).
For each of the institution's claims it finds the corresponding authoritative
claim on the same farmer + same `claim_type`, then:

- numeric claims → percentage variance vs the authoritative value;
- categorical/boolean claims → exact value match.

Agreement within `$acceptable_variance_percentage` earns `+$reward`;
disagreement earns `-$penalty`. Per-comparison deltas are **averaged** (not
summed) so the update is bounded regardless of how many farmers an institution
covers, then clamped to `[0, 1]`. Institutions with no ground-truth overlap keep
their score.

```python
from app.database.neo4j_client import get_driver
from app.database import trust_graph as tg
from app.database.graph_ingestion import GraphIngestionService

driver = get_driver()
GraphIngestionService(driver).ensure_constraints()   # constraints live with the writer now

# Part 1
tg.verify_claim(driver, farmer_id="F-123", claim_type="land_size_hectares",
                min_trust_score=0.4)

# Part 2 (penalties heavier than rewards by default)
tg.recalculate_reputation(driver, institution_id="ORG-AGROVESTO",
                          acceptable_variance_percentage=5.0, reward=0.05, penalty=0.10)
```

Reputation feeds straight back into traversal: once an institution is penalized
below `$min_trust_score`, its claims stop appearing in Part 1 — a closed trust
loop. Both queries are parameterized end-to-end. (They were verified against a
live Neo4j in an earlier iteration; the reified-schema consolidation since then —
edge-direction flip and `value`/`observed_at` → `value_string`/`timestamp` —
is reviewed but unrun against a live instance.)

## Silver standard: validation gateway & Dead-Letter Queue

Bronze → Silver. `ingestion/gateway.py:process_incoming_batch(raw_batches)`
parses each raw payload into a strict reified `PayloadBundle`
(`models/reified.py`), routes anything that fails Pydantic V2 validation to the
`DeadLetterQueue` (`ingestion/dlq.py` → `dlq_logs.jsonl`), and returns only the
clean bundles — one bad payload never aborts the batch.

The `PayloadBundle` validator enforces a key rule: **if the attesting institution
is `is_authoritative=True`, every linked claim's `confidence` is overridden to
`1.0`** (a ground-truth source is, by definition, maximally confident). Verified
bundles are written by `GraphIngestionService.ingest_bundles`, the single reified
write surface, which `MERGE`s `(:Institution)-[:ATTESTS_TO]->(:Claim)-[:BELONGS_TO]->(:Farmer)`
idempotently and seeds each institution's `trust_score`.

Verification sources feed this path through `verification/claim_bridge.py`, which
converts a Sentinel-2 NDVI estimate, a paper-register `OCRClaim`, or a
`StandardFarmerClaim` into `PayloadBundle`s — with the satellite marked
authoritative (ground truth for reputation scoring).

## Autonomous DLQ Investigator (data-quality agent)

Validation quarantines *malformed* payloads, but the subtler debt is **valid
payloads that disagree** — a cooperative's self-reported 5 ha against the
satellite's 2 ha for the same farmer. The Investigator (`app/investigator/`) is a
background worker that keeps the gold layer pristine without a human steward
eyeballing every record:

1. **Discover** every metric that has an authoritative (ground-truth) claim to
   check against (`graph_ops.list_authoritative_claim_types`).
2. **Detect** reported claims whose relative variance from ground truth exceeds
   the threshold — returned *with claim ids* plus the attesting source's
   `trust_score` and last reputation-pass counters, in one round trip.
3. **Cross-reference** the source's broader track record: its agreement rate and
   how many of its claims currently contradict ground truth across all farmers
   (`count_source_conflicts`).
4. **Recommend** a resolution — `policy.recommend(...)` is a **pure, deterministic
   function** so every verdict is reproducible and auditable. It returns an
   `action` (`TRUST_GROUND_TRUTH` / `PENALIZE_SOURCE` / `FLAG_FOR_REVIEW` /
   `INSUFFICIENT_DATA`), a `severity`, a `confidence`, and a rationale. A
   low-trust or repeat-offender source is penalized; a normally-reliable source
   disagreeing in isolation is escalated to a human instead of auto-resolved.
5. **Flag** the specific Claim nodes as a graph fact: a
   `(:Claim)-[:CONFLICTS_WITH]->(:Claim)` edge plus `flag_action` / `flag_severity`
   / `flag_confidence` / `flag_rationale` stamped on the reported claim, so a loan
   officer's query surfaces "this figure is disputed" directly.

> **Where the LLM fits.** The verdict is always the deterministic policy's — you
> don't want a model inventing data-quality decisions. When `FEATHERLESS_API_KEY`
> is set, Featherless/Qwen3 *only rephrases the rationale* for a human steward;
> with no key it silently keeps the computed rationale, so the agent is fully
> functional offline.

**Run it.** As an in-process background loop, set `INVESTIGATOR_ENABLED=true`
(tune `INVESTIGATOR_INTERVAL_SECONDS`, `INVESTIGATOR_VARIANCE_THRESHOLD`) and it
starts from the FastAPI lifespan. Standalone:

```bash
python -m app.investigator.worker --once                 # single pass, prints JSON
python -m app.investigator.worker --interval 300         # loop every 5 min
python -m app.investigator.worker --once --no-flag --no-llm   # dry run, no writes
```

Or drive it over HTTP: `POST /api/v1/investigator/run?variance_threshold=0.2`
runs a pass and returns a summary (counts by action/severity + the validation
DLQ depth); `GET /api/v1/investigator/flags` lists the flagged claims, worst
variance first.

## MATCH engine — financial eligibility (`POST /match/{farmer_id}`)

A data-driven rules engine connecting verified farmers to loan products. A
`FinancialProduct` (`services/product_catalog.py`) declares a `min_trust_score`
(institution-reputation bar) and a dict of per-metric `eligibility_rules`
(`min` / `max` / `min_confidence`). `match_engine.py` compiles those into one
parameterized Cypher query that checks the farmer's claims **only against
attestations from sufficiently-trusted institutions** and returns eligibility
plus a per-rule breakdown. Adding a product is a catalog entry — no query change.

## Farmer consent & data-access control

The farmer is the gatekeeper of their own data. Two graph concepts:

- `(:Institution)-[:REQUESTED_ACCESS]->(:DataAccessRequest {status})-[:TO_FARMER]->(:Farmer)`
  — the immutable **audit trail** (`PENDING → APPROVED | DENIED`).
- `(:Institution)-[:GRANTED_ACCESS {status:'APPROVED', basis}]->(:Farmer)` — the
  **active capability edge**, created on approval and deleted on denial (so a
  denial is a real-time revocation).

Endpoints (`api/consent.py`): `POST /api/v1/consent/request`, `.../resolve`
(the simulated USSD/SMS farmer interface), and `.../source-grant`. The read path
(`profile_queries.get_verified_history_gated`) **requires** an `APPROVED`
`[:GRANTED_ACCESS]` edge before any claim is traversed — no grant, zero rows, no
data leaves the database.

**Collection-time consent.** Institutions that already obtained consent when they
collected the data (`Institution.consent_at_source=True`, e.g. Tegemeo) get a
standing `[:GRANTED_ACCESS {basis:'COLLECTION'}]` edge provisioned automatically
at ingestion — they never need the request/resolve handshake. The gate is
basis-agnostic, so explicit and collection grants both unlock the read. Consent
is always per-`(institution, farmer)`.

## Gold consumer APIs — one graph, three lenses

| Consumer | Endpoint | Shape |
|---|---|---|
| Financial (loan officer) | `GET /api/v1/loan-officer/farmer/{farmer_id}` and `GET /api/v1/profiles/{farmer_id}/verified-history` | `verified_history` keyed by `claim_type`, ground-truth at index 0 |
| Data owner (farmer) | `GET /api/v1/farmer/{farmer_id}/my-data` | Plain-language `Verified`/`Unverified`, who's viewing; no confidence decimals |
| Macro (analytics) | `GET /api/v1/macro/cooperative/{institution_id}/stats` | Anonymized aggregates only — **no `farmer_id` / `phone`** |

Aggregation is pushed to Cypher (`profile_queries.py`, `consumer_queries.py`).
The verified-history query groups by `claim_type` and sorts attestations
authoritative-first then by descending `trust_score`. The farmer-view and macro
queries are written to avoid Cartesian explosions — independent `CALL {}`
subqueries for the farmer view, and a `DISTINCT` member set tested with cheap
`EXISTS {}` subqueries for the macro stats.

## External integration — inbound connectors & outbound export

The platform is a hub: external systems are *ingested* into the reified graph
(the system of record), and downstream systems *consume* it through an export
API. Both ends normalize on the same contracts.

**Inbound — pooled async pull from an external SQL registry.**
`ingestion/connectors/postgres.py` holds a **pooled async engine** (SQLAlchemy 2.0
+ asyncpg, `pool_pre_ping` + `pool_recycle` for resiliency to dropped
connections); `connectors/cooperative_sync.py` runs the pipeline
`rows → sql_adapters (strict Pydantic) → PayloadBundle → reified_guard.publish_reified`.
Properties:
- **Strict validation** — raw rows are validated against `TegemeoRegistryRow`
  (Pydantic) at the boundary; malformed rows are dropped, never written.
- **Schema-split enforced** — the connector *cannot* touch the writer directly; it
  publishes only through `ingestion/reified_guard.py`, whose type gate rejects
  anything but a reified `PayloadBundle` and whose text gate rejects any Cypher
  carrying gold-layer tokens (`:Organization`, `VERIFIED_BY`, `:ABOUT`, …).
- **Idempotent** — deterministic claim ids → re-syncing updates in place.
- **Refuses to fabricate** — no `COOP_PG_DSN` ⇒ `SourceNotConfigured`, clean exit.

Integration tests (`tests/test_connector_integration.py`, testcontainers Postgres)
cover reified-bundle generation, idempotency, full-pool dispose recovery, and
`pool_pre_ping` reconnect after a server-side connection drop; the schema-split
gates have a fast unit test (`tests/test_reified_guard.py`).

**Orchestration, secrets & CDC.** Credentials are resolved through a secrets seam
(`app/secrets/`, `SECRETS_BACKEND=env|vault|aws`) — `.env` is the dev default but
deprecated for external sources in favour of Vault / AWS Secrets Manager. The sync
is a **CDC** pull: a `Neo4jWatermarkStore` (`ingestion/watermark.py`) tracks the
max `updated_at` per source in `(:SyncState)`, so each run fetches only new rows
(verified: a full pull of 4 rows → an incremental pull of 1 → picks up a new row
without reprocessing history). Failures are routed, not swallowed — connection
timeouts, schema-mapping rejections (`sql_adapters` strict validation), and
schema-split violations are classified and alerted via `ingestion/observability.py`
(`ALERT_WEBHOOK_URL`, Slack-compatible). A **Dagster** orchestrator
(`app/orchestration/definitions.py`) schedules the sync every 15 min with retries
and a run-failure sensor wired to the same alerting:

```bash
docker compose --profile orchestration up dagster   # UI at http://localhost:3000
```

The orchestrator is a thin trigger; the CDC/state/alerting logic lives in plain,
tested Python (`tests/test_sprint2_core.py`).

**API adapter pattern — ERPs / FMIS / on-demand registries** (`app/clients/`). A
resilient async HTTP client (`http_client.py`, httpx) with automatic retries +
exponential backoff, 429 `Retry-After` handling, and pluggable auth
(`BearerAuth` / `OAuth2ClientCredentials`, re-auth on 401). FMIS GraphQL sources
use a minimal query fragment (no over-fetch) and a **strict Pydantic** projection
(`fmis.py`) that drops unneeded fields before mapping to a reified bundle. Public
registries (land authority, certifier) are queried **on demand during a claim's
verification phase** (`verification/registry_lookup.py`) rather than batch-pulled,
and an **idempotent cache** (`clients/cache.py`, memory or Redis,
`REGISTRY_CACHE_BACKEND`) stops identical lookups from spamming external APIs
under high-volume ingestion. Verified: retry/backoff/429/re-auth via httpx
`MockTransport` and cache idempotency (`tests/test_http_client.py`,
`tests/test_registry_cache.py`).

**High-throughput streaming — IoT / telemetry** (`app/streaming/`). An
`aio_pika` RabbitMQ consumer (`consumer.py`) isolates ingestion workers from the
raw MQTT firehose. Diverse sensor payloads are `normalize`d into a standardized
`TelemetryReading` (epoch/ISO timestamps, aliases; late events and duplicate
timestamps handled). A `MicroBatcher` buffers readings and flushes on size **or**
a time window, then `aggregate_readings` collapses the window to **one claim per
(farmer, metric)** (the mean) — cutting write IOPS and node count. **Exactly-once**
comes from manual ack *after* commit + a dedup store (`STREAM_DEDUP_BACKEND`,
memory/Redis) that drops already-committed message ids, plus deterministic claim
ids so re-delivery is idempotent. Verified live against RabbitMQ: 5 msgs (one a
duplicate) → micro-batched → `4 new, 1 duplicate skipped` → F-9001 soil = mean(40,44)
= 42.0 in the graph, re-runs don't double. Compose: `docker compose --profile
streaming up` (RabbitMQ + `telemetry-consumer`). Core tested in `tests/test_streaming.py`.

**Bulk storage & spatial — S3 / Parquet / STAC / GeoJSON** (`app/bulk/`).
Event-driven: `events.parse_s3_event` turns an S3 object-created notification into
object refs + routes by extension. `spatial.py` extracts **indexable** spatial
metadata from GeoJSON/STAC — geodesic area (hectares, spherical-excess, no GIS
dep), bounding box, centroid, temporal — flattening geometry to float/string
properties the graph can query. `processor.process_geojson` validates features,
maps each parcel to a reified `land_size_hectares` (+ `parcel_bbox`) claim through
the schema-split guard, and tallies a `BulkJobAudit` (succeeded / failed-validation
/ rejected) into a `(:BulkJobAudit)` metadata node. For multi-GB backfills,
`spark_job.run_bronze_to_silver` does distributed cleaning + schema enforcement
(PySpark, run on a cluster — kept out of the API image). Verified live: a parcel
→ `land_size_hectares = 123.89 ha` + bbox string in the graph, audit `1 ok / 1
invalid`. Tests: `tests/test_bulk_spatial.py`, `tests/test_bulk.py`.

```bash
COOP_PG_DSN=postgresql://user:pass@host:5432/registry \
  python -m app.ingestion.connectors.cooperative_sync --once        # or --interval 900
# wired into compose behind the "connectors" profile:
docker compose --profile connectors run --rm coop-sync --once
```

**Outbound — let downstream systems consume the verified graph** (`api/export.py`,
read-only over the reified layer; verified claims + source/trust, never PII):

| Endpoint | Shape |
|---|---|
| `GET /api/v1/export/claims?claim_type=&min_trust_score=&since=&offset=&limit=` | paginated JSON page (`next_offset` cursor) |
| `GET /api/v1/export/claims.ndjson?...` | streamed NDJSON for bulk ETL |
| `GET /api/v1/export/farmer/{id}/claims` | one farmer's verified claims |

**Access control & rate limiting** (`api/security.py`, applied as router-level
dependencies on every export route): set `EXPORT_API_KEY` to require an
`X-API-Key` header (401 otherwise; open when unset for dev), and
`EXPORT_RATE_LIMIT_PER_MIN` (default 120) to cap requests per key/IP (429 on
exceed) so downstream load can't overwhelm the database. Verified live:
no key → 401, valid key → 200, burst past the limit → 429.

**Event publishing (push, not poll)** — `app/events/` emits a `claim.verified`
event the moment a claim is merged into the gold layer (hooked into
`reified_guard.publish_reified`). Backends via `EVENT_BACKEND`: `none` (default,
no-op), `webhook` (POST to `EVENT_WEBHOOK_URLS`), or `redis` (PUBLISH to a Redis
Pub/Sub channel). The event payload mirrors the export schema (flat, provenance-
stamped, a stable `claim_id` for dedupe — no graph internals) and publishing is
best-effort, so a dead subscriber never fails the ingestion that produced it.

## MCP server — read-only access for external AI systems

`backend/app/mcp/server.py` exposes the verified-claims gold layer to any
MCP-compatible client (Claude Desktop, an external agent framework, a
partner's own AI system) over the Model Context Protocol, using
[`FastMCP`](https://github.com/modelcontextprotocol/python-sdk). It is
**read-only end to end**: every tool calls an existing read-only function
(`app.database.match_engine`, `trust_graph`, `profile_queries`,
`consumer_queries`, `app.api.lender`) — there is no write path, no `CREATE`/
`MERGE`/`SET`/`DELETE` anywhere a tool can reach.

### Starting it

```bash
cd backend

# stdio, mock data (no DB needed) — for local agents / Claude Desktop
python run_mcp.py

# stdio against the live graph (reads NEO4J_URI/USERNAME/PASSWORD/DATABASE
# from the project-root .env, same as the FastAPI app)
MCP_BACKEND=neo4j python run_mcp.py

# SSE over HTTP — for a remote AI system / partner integration
MCP_BACKEND=neo4j MCP_TRANSPORT=sse python run_mcp.py
```

`MCP_BACKEND` only gates the original three org-level tools (below); the five
farmer/portfolio/eligibility tools always call `get_driver()` directly and
therefore always hit the live graph regardless of `MCP_BACKEND`.

### Tools exposed

Org-level (via the injected `GraphReadService`, mock-by-default):
- `get_verified_claims(org_id)` — every claim an institution attests to.
- `trace_provenance(claim_id)` — a claim's lineage back to its source system.
- `check_compliance_status(entity_name)` — an institution's trust tier.

Farmer / portfolio / eligibility (direct `get_driver()` call-through, no new
Cypher — every query already existed elsewhere in the codebase):
- `get_eligible_farmers(crop_type, region, min_land_hectares, min_trust_score, product_type)`
  — calls `app.api.lender._query_eligible_farmers` + `match_engine.evaluate_product`.
- `get_farmer_verified_history(farmer_id, requesting_institution_id)` — calls
  `profile_queries.get_verified_history_gated`. **No `GRANTED_ACCESS` grant ⇒
  `consent_granted: false` and no history data at all** — never an empty-but-
  present history. The gate is never bypassed.
- `get_cooperative_portfolio(cooperative_id)` — calls
  `consumer_queries.get_cooperative_stats`. Anonymized aggregate only.
- `check_farmer_eligibility(farmer_id, product_id)` — calls
  `match_engine.farmer_exists` + `evaluate_product` directly; no eligibility
  logic is duplicated.
- `get_verification_sources(farmer_id)` — calls
  `trust_graph.verify_claim` per claim_type the farmer has.

**Non-negotiables enforced on every tool above:** read-only (no write surface
exists to reach); `farmer_id` and `phone_number` are never both present in a
single response (`VerifiedHistoryResult`/`EligibleFarmerSummary`/etc. either
omit `phone_number` entirely or, where the underlying query returns it
incidentally, the tool strips it before building the response); `gender`/
`ethnicity` are never queried or returned (consistent with
`EXCLUDED_FROM_SCORING`); consent denial returns no data, never empty data.

Verified live against the Aura graph during development: a correct
`requesting_institution_id` returned the farmer's full verified history; an
arbitrary, non-granted institution id returned `consent_granted: false` with
`verified_history: null` — the gate held.

## SSE event contract

Every chunk is a single SSE frame: `data: <json>\n\n`.

```jsonc
// Status update
{"type": "status", "message": "Executing Neo4j Cypher query for Nakuru county..."}

// UI component
{"type": "component", "componentType": "BarChart",
 "props": {"data": [...], "xKey": "region", "yKey": "yield"}}

// Terminal error (boundary-guarded)
{"type": "error", "message": "Internal error while generating the response."}
```

The stream is terminated with an `event: end` / `data: [DONE]` sentinel.

## Getting started

### Prerequisites
- Python 3.11+
- Node.js 18+ (for the frontend, Milestone 4)
- Docker (for the local Neo4j instance)

### 1. Configure environment
Copy your credentials into `.env` (git-ignored):

```dotenv
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password

# Featherless AI (OpenAI-compatible) serves the Qwen3 agent model.
# Leave FEATHERLESS_API_KEY empty to run the deterministic mock agent.
FEATHERLESS_API_KEY=
FEATHERLESS_BASE_URL=https://api.featherless.ai/v1
FEATHERLESS_MODEL=Qwen/Qwen3-235B-A22B-Thinking-2507
```

### Quickstart with Docker (API + Neo4j)

The fastest path: `docker compose up --build` brings up Neo4j (with APOC) and the
backend API together. The backend image (`backend/Dockerfile`) installs the OCR
system deps (`tesseract-ocr`, `libglib2.0-0`), runs uvicorn as a non-root user,
and waits for Neo4j to be healthy. `FEATHERLESS_*` and `CORS_ORIGINS` are read
from the root `.env`.

```bash
docker compose up --build          # API on :8000, Neo4j on :7474/:7687
curl http://localhost:8000/health  # {"status":"ok"}
docker compose up -d neo4j         # or: just the database, run the API locally
```

Seed the graph (one-off services behind the `seed` profile):

```bash
# Registry layer (base 5-node model) — demographics / portfolio / analytical queries
docker compose run --rm loader --farmers 200 --reset

# Reified trust layer (Institutions + Claims + deliberate conflicts) —
# operational tools (trust score, eligibility, verified history) + DLQ Investigator
docker compose run --rm reified-seed --farmers 60
```

After seeding: the analytical path answers e.g. *"how many farmers per country?"*,
the operational tools answer *"what is ORG-TEGEMEO's trust score?"*, and
`POST /api/v1/investigator/run` flags the satellite-vs-cooperative land-size
conflicts.

### 2. Data pipeline (Milestone 1)

```bash
pip install -r data-pipeline/requirements.txt

# Optional: dump synthetic CSVs for inspection
python data-pipeline/generate_synthetic.py --farmers 1000

# Generate + idempotently ingest into Neo4j (requires a running Neo4j)
python data-pipeline/neo4j_loader.py --farmers 1000 --reset
```

`neo4j_loader.py` applies uniqueness constraints before `MERGE`-based `UNWIND`
batch ingestion, so re-running it is safe (no duplicates).

### 3. Backend streaming API (Milestone 3)

```bash
pip install -r backend/requirements.txt
cd backend && python main.py        # serves on http://localhost:8000
```

Test the stream:

```bash
curl -N "http://localhost:8000/api/chat?query=maize%20yield%20by%20region"
```

You'll see status frames, then a validated component frame, then `[DONE]`.

## Loan Officer Copilot — supervisor architecture (Milestone 2)

The chat agent is a **supervisor with transparent ReAct loops**. LangChain is used
only at the LLM/tool layer — `langchain_openai.ChatOpenAI` (pointed at Featherless)
with `bind_tools` and `with_structured_output` for native Pydantic tool calling —
while the orchestration stays a plain Python `for`-loop (no LangGraph), so the
control flow is easy to read and debug. It deliberately gets the pros of both a
vetted-tool agent and a pure Graph-RAG agent by routing between them:

```
query ── Intent Router ─┬─► Operational path  (vetted, high-stakes tools)
                        └─► Analytical path   (free-form, read-only Cypher)
                                     │
                                     ▼
                deterministic render (BarChart/Table) → Insight synthesis
```

1. **Intent Router** (`agent/router.py`) — a cheap deterministic fast-path
   handles obvious cases; everything ambiguous goes to a fast LLM classification.
   On any error it defaults to the analytical path. Buckets a request as:
   - **Operational** — precise, single-entity lookups answered exactly by
     hardcoded, optimized functions (`agent/tools.py`): one farmer's eligibility
     for a named product, one farmer's verified history, an institution's trust
     score, a cooperative's portfolio stats. The model only picks the tool and
     supplies Pydantic-validated arguments — no Cypher, no injection surface.
   - **Analytical** — exploratory/aggregate questions ("which farmers have over
     2 ha verified but no credit history?") answered by the Graph-RAG agent using
     the single `CypherExecutionTool` (`agent/cypher_tool.py`). The LLM must
     return both the **query and its rationale**; execution goes through
     `cypher_guard` (word-boundary read-only checks, comment stripping, stacked-
     statement rejection, a forced read transaction, and a row cap) — strictly
     safer than a naive keyword scan.
2. **Deterministic render** (`agent/render.py`) — gathered rows become a
   `BarChart`/`Table` component; the model never fabricates chart data.
3. **Insight synthesis** — a final LLM pass turns the raw results into a concise,
   business-readable answer, streamed as an `Insight` component on top of the data.

Every stage streams the same `status`/`component` SSE envelopes, so
`api/chat_stream.py` is unchanged. With no `FEATHERLESS_API_KEY`, `graph.py`
falls back to the deterministic mock stream. The model is env-driven
(`FEATHERLESS_MODEL`, optional faster `FEATHERLESS_ROUTER_MODEL` for the router).

> **Frontend note.** The new `Insight` component (plain-language answer) joins
> `BarChart`/`Table` in the GenUI contract; the frontend `ComponentRegistry`
> (skeleton) needs a renderer entry for it.

### 4. Frontend (Milestone 4)

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

CORS in the backend defaults to allowing `http://localhost:3000` (override with
the `CORS_ORIGINS` env var).
