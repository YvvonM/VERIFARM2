#!/usr/bin/env bash
#
# Phase 4 demo: Redis-backed DURABLE telemetry dedup. Phase 2 showed in-batch
# dedup (in-memory, lost on restart); here the committed-message-id set lives in
# Redis, so exactly-once survives a consumer restart: re-publishing the same
# readings after a restart is fully skipped as duplicates.
#
# Prereqs: Docker + docker compose. Run from anywhere:
#     ./scripts/demo_phase4.sh
#
# Reset:  docker compose --profile demo down -v
set -euo pipefail

cd "$(dirname "$0")/.."

FARMERS="${FARMERS:-30}"
COMPOSE="docker compose"

# Point the consumer at Redis for durable dedup (the compose service reads these).
export STREAM_DEDUP_BACKEND=redis
export REDIS_URL="redis://redis:6379/0"

echo "==> 1/6  Starting Neo4j, Redis, RabbitMQ, and the consumer (dedup backend=redis)"
$COMPOSE --profile streaming up -d neo4j redis rabbitmq telemetry-consumer

echo "==> 2/6  Seeding the farmer roster (ground truth only)"
$COMPOSE run --rm reified-seed --farmers "$FARMERS" --ground-truth-only

echo "==> 3/6  Round 1: publishing telemetry"
$COMPOSE --profile streaming run --rm telemetry-producer --farmers "$FARMERS"
sleep 9

echo "==> 4/6  Restarting the consumer (in-memory dedup would forget; Redis must remember)"
$COMPOSE --profile streaming restart telemetry-consumer
sleep 5

echo "==> 5/6  Round 2: re-publishing the SAME readings (same message ids)"
$COMPOSE --profile streaming run --rm telemetry-producer --farmers "$FARMERS"
sleep 9

echo "==> 6/6  Flush log — round 2 should show ~0 new, all duplicates skipped"
echo "--- all 'Flushed' lines (round 1 then round 2) ---"
$COMPOSE --profile streaming logs --tail=80 telemetry-consumer 2>/dev/null | grep -iE "Flushed" || \
  echo "(no flush line yet; re-check: $COMPOSE --profile streaming logs telemetry-consumer)"

echo
echo "--- committed message ids persisted in Redis ---"
$COMPOSE exec -T redis redis-cli SCARD verifarms:committed_telemetry 2>/dev/null || true

cat <<EOF

The point: after the restart, round 2's flush logs '... 0 new, N duplicate(s)
skipped' — the dedup set was read back from Redis, not lost with the process.
The same REDIS_URL also backs REGISTRY_CACHE_BACKEND=redis and EVENT_BACKEND=redis.

  * Inspect Redis:   $COMPOSE exec -T redis redis-cli SMEMBERS verifarms:committed_telemetry | head
  * Tear down:       $COMPOSE --profile demo down -v
EOF
