#!/usr/bin/env bash
#
# Phase 3 demo: the bulk-spatial pipeline over an S3-compatible object store.
# Stand up MinIO, upload roster-aligned parcel GeoJSON, run the S3 connector to
# extract spatial metadata (bbox + geodesic area) into reified claims, and show
# the per-object audit + the conflicts the oversized parcels introduce.
#
# Prereqs: Docker + docker compose. Run from anywhere:
#     ./scripts/demo_phase3.sh
#
# Reset:  docker compose --profile demo down -v
set -euo pipefail

cd "$(dirname "$0")/.."

FARMERS="${FARMERS:-60}"
COMPOSE="docker compose"

echo "==> 1/4  Starting Neo4j, MinIO, and the backend API"
$COMPOSE --profile demo up -d neo4j minio backend

echo "==> 2/4  Seeding the farmer roster (ground truth only, for the parcels to attach to)"
$COMPOSE run --rm reified-seed --farmers "$FARMERS" --ground-truth-only

echo "==> 3/4  Uploading roster-aligned parcel GeoJSON to MinIO"
$COMPOSE --profile demo run --rm spatial-seed --farmers "$FARMERS"

echo "==> 4/4  Running the S3 connector: parcels -> bbox + geodesic area -> claims"
$COMPOSE --profile demo run --rm spatial-process

echo
echo "--- BulkJobAudit rows (per uploaded object) ---"
$COMPOSE exec -T neo4j cypher-shell --format plain \
  "MATCH (a:BulkJobAudit) RETURN a.object_key AS object, a.total_rows AS rows, a.succeeded AS ok, a.failed_validation AS failed ORDER BY object" \
  2>/dev/null || echo "(cypher query skipped; check via the API/Browser at http://localhost:7474)"

echo
echo "--- spatial claims now in the graph ---"
$COMPOSE exec -T neo4j cypher-shell --format plain \
  "MATCH (c:Claim) WHERE c.source_id STARTS WITH 's3://' RETURN c.claim_type AS metric, count(c) AS claims ORDER BY metric" \
  2>/dev/null || true

cat <<EOF

Done. Things to try:
  * Flag the oversized-parcel conflicts vs satellite truth:
      curl -fsS -X POST http://localhost:8000/api/v1/investigator/run
  * Inspect objects in the MinIO console:  http://localhost:9001  (minioadmin/minioadmin)
  * Re-run the connector — claims update in place (deterministic ids):
      $COMPOSE --profile demo run --rm spatial-process
  * Tear down:  $COMPOSE --profile demo down -v
EOF
