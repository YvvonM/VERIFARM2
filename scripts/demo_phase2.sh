#!/usr/bin/env bash
#
# Phase 2 demo: the IoT telemetry streaming pipeline. Stand up RabbitMQ + the
# consumer, seed the farmer roster, publish sensor readings (with deliberate
# duplicates and a vendor dialect), and show the consumer collapse each window
# into one averaged claim per (farmer, metric) while skipping duplicates.
#
# Prereqs: Docker + docker compose. Run from anywhere:
#     ./scripts/demo_phase2.sh
#
# Reset:  docker compose --profile streaming down -v
set -euo pipefail

cd "$(dirname "$0")/.."

FARMERS="${FARMERS:-60}"
COMPOSE="docker compose"

echo "==> 1/4  Starting Neo4j, RabbitMQ, and the telemetry consumer"
$COMPOSE --profile streaming up -d neo4j rabbitmq telemetry-consumer

echo "==> 2/4  Seeding the farmer roster (ground truth only; gives the IoT claims farmers to attach to)"
$COMPOSE run --rm reified-seed --farmers "$FARMERS" --ground-truth-only

echo "==> 3/4  Publishing telemetry (uniques + duplicates + a vendor dialect)"
$COMPOSE --profile streaming run --rm telemetry-producer --farmers "$FARMERS"

echo "==> 4/4  Waiting for the consumer's window to flush (max-age 5s) ..."
sleep 9

echo "--- consumer flush log (windowed mean + dedup) ---"
# The 'Flushed N msg(s): X new, Y duplicate(s) skipped, Z claim(s) written' line
# is the proof: Z ~= farmers x metrics (aggregation), Y > 0 (exactly-once dedup).
$COMPOSE --profile streaming logs --tail=40 telemetry-consumer 2>/dev/null | grep -iE "flush|duplicate" || \
  echo "(no flush line yet — give it a few more seconds and re-check: $COMPOSE --profile streaming logs telemetry-consumer)"

echo
echo "--- IoT claims now in the graph (one mean per farmer/metric) ---"
$COMPOSE exec -T neo4j cypher-shell --format plain \
  "MATCH (c:Claim) WHERE c.source_id = 'iot-sensornet' RETURN c.claim_type AS metric, count(c) AS claims ORDER BY metric" \
  2>/dev/null || echo "(cypher query skipped; check via the API/Browser at http://localhost:7474)"

cat <<EOF

Done. Things to try:
  * Re-publish — claims update in place (deterministic ids), no node explosion:
      $COMPOSE --profile streaming run --rm telemetry-producer --farmers $FARMERS
  * Crank the duplicate rate to see more dedup:
      $COMPOSE --profile streaming run --rm telemetry-producer --farmers $FARMERS --dup-rate 0.5
  * Ask the copilot:  "Show the verified history for farmer F-0001"
  * Tear down:  $COMPOSE --profile streaming down -v
EOF
