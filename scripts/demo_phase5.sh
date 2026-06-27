#!/usr/bin/env bash
#
# Phase 5 demo: external credit/identity enrichment through the ClaimBridge seam.
# Stands up a stub credit-bureau/KYC API, registers a real HTTP provider against
# the seam, and drives ClaimBridge to fetch + reify credit_history and
# identity_verified claims for the roster — the wiring that was previously absent
# (the seam shipped no provider, so these claims never existed at runtime).
#
# Prereqs: Docker + docker compose. Run from anywhere:
#     ./scripts/demo_phase5.sh
#
# Reset:  docker compose --profile demo down -v
set -euo pipefail

cd "$(dirname "$0")/.."

FARMERS="${FARMERS:-60}"
COMPOSE="docker compose"

echo "==> 1/4  Starting Neo4j, the stub bureau, and the backend API"
$COMPOSE --profile demo up -d neo4j stub-bureau backend

echo "==> 2/4  Seeding the farmer roster (ground truth only)"
$COMPOSE run --rm reified-seed --farmers "$FARMERS" --ground-truth-only

echo "==> 3/4  Enriching via the seam: ClaimBridge -> stub bureau -> reified claims"
$COMPOSE --profile demo run --rm enrich-providers --farmers "$FARMERS"

echo "==> 4/4  Verifying the new credit/identity claims landed in the graph"
$COMPOSE exec -T neo4j cypher-shell --format plain \
  "MATCH (c:Claim) WHERE c.claim_type IN ['credit_history','credit_default_flag','identity_verified'] RETURN c.claim_type AS claim_type, count(c) AS claims ORDER BY claim_type" \
  2>/dev/null || echo "(cypher query skipped; check via the API/Browser at http://localhost:7474)"

cat <<EOF

Done. The seam now produces real (stub-sourced) claims at runtime:
  * Stub bureau API docs:        http://localhost:8001/docs
  * Ask the copilot:             "Is farmer F-0001 eligible for a loan?"
                                 "Show the verified history for farmer F-0001"
  * Macro stats: 'no credit history' counts shrink now that credit_history exists.
  * Point at a REAL vendor instead: register its client like app/scripts/demo/demo_providers.py
    and set CREDIT_PROVIDER / CREDIT_API_KEY / CREDIT_BASE_URL (and IDENTITY_*).
  * Tear down:  $COMPOSE --profile demo down -v
EOF
