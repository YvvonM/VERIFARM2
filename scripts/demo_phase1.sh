#!/usr/bin/env bash
#
# Phase 1 demo: stand up the cooperative Postgres source, seed it (roster-aligned
# with the reified trust layer), pull it into Neo4j via the CDC connector, and
# show the introduced land-size conflicts get flagged by the DLQ Investigator.
#
# Prereqs: Docker + docker compose. Run from anywhere:
#     ./scripts/demo_phase1.sh
#
# Reset everything afterwards with:
#     docker compose --profile demo down -v
set -euo pipefail

cd "$(dirname "$0")/.."

FARMERS="${FARMERS:-60}"
COMPOSE="docker compose"
API="http://localhost:8000"

echo "==> 1/5  Starting Neo4j, the demo cooperative Postgres, and the backend API"
$COMPOSE --profile demo up -d neo4j coop-postgres backend

echo "==> 2/5  Seeding ground truth only (satellite land size; no static coop claims)"
# --ground-truth-only so the LIVE Postgres connector is the sole source of
# cooperative claims and therefore the sole conflict source in this demo.
$COMPOSE run --rm reified-seed --farmers "$FARMERS" --ground-truth-only

echo "==> 3/5  Seeding the cooperative Postgres source ($FARMERS members, F-0001..)"
$COMPOSE --profile demo run --rm coop-seed --farmers "$FARMERS"

echo "==> 4/5  Running the CDC connector: Postgres -> reified claims in Neo4j"
$COMPOSE --profile demo run --rm coop-sync --once

echo "==> 5/5  Asking the DLQ Investigator to flag the conflicts"
# Backend auth is open by default (no VERIFARMS_API_KEY); add -H "X-API-Key: ..."
# if you set one. The endpoint runs one investigation pass and returns flags.
if command -v curl >/dev/null 2>&1; then
  # Give the backend a moment to be ready.
  for _ in $(seq 1 20); do
    curl -fsS "$API/health" >/dev/null 2>&1 && break || sleep 2
  done
  echo "--- POST /api/v1/investigator/run ---"
  curl -fsS -X POST "$API/api/v1/investigator/run" || echo "(investigator run call failed; is the backend up?)"
  echo
  echo "--- GET /api/v1/investigator/flags ---"
  curl -fsS "$API/api/v1/investigator/flags" || true
  echo
else
  echo "curl not found — hit these yourself:"
  echo "  POST $API/api/v1/investigator/run"
  echo "  GET  $API/api/v1/investigator/flags"
fi

cat <<EOF

Done. Things to try:
  * Re-run the connector — it's idempotent (claim ids are deterministic, no nonce):
      $COMPOSE --profile demo run --rm coop-sync --once
  * Demonstrate incremental CDC (only the changed row is re-pulled):
      $COMPOSE --profile demo run --rm coop-seed --touch F-0005
      $COMPOSE --profile demo run --rm coop-sync --once     # watermark fetches just F-0005
  * Ask the copilot:  "Show the verified history for farmer F-0005"
  * Tear down:  $COMPOSE --profile demo down -v
EOF
