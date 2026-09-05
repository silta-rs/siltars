#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
EXPERIMENT_DIR="$ROOT_DIR/experiments/poc-001-pip-native-runtime"
CONTAINER_NAME="${POSTGRES_CONTAINER:-silta-poc-postgres}"
HOST="${SILTA_HOST:-127.0.0.1}"
PORT="${SILTA_PORT:-8000}"
POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-55432}"
RUNTIME_BIN="${SILTA_RUNTIME_BIN:-$ROOT_DIR/target/debug/silta-runtime}"
DB_MIN_CONNECTIONS="${SILTA_DB_MIN_CONNECTIONS:-1}"
DB_MAX_CONNECTIONS="${SILTA_DB_MAX_CONNECTIONS:-10}"
DB_ACQUIRE_TIMEOUT_MS="${SILTA_DB_ACQUIRE_TIMEOUT_MS:-5000}"
# Optional local ClickHouse for the experimental /ch/* routes (see seed_clickhouse.sh).
CLICKHOUSE_URL="${CLICKHOUSE_URL:-}"
CLICKHOUSE_DATABASE="${CLICKHOUSE_DATABASE:-silta_poc}"
CLICKHOUSE_ARGS=()
if [[ -n "$CLICKHOUSE_URL" ]]; then
  CLICKHOUSE_ARGS=(--clickhouse-url "$CLICKHOUSE_URL" --clickhouse-database "$CLICKHOUSE_DATABASE")
  if [[ -n "${CLICKHOUSE_MAX_THREADS:-}" ]]; then
    CLICKHOUSE_ARGS+=(--clickhouse-max-threads "$CLICKHOUSE_MAX_THREADS")
  fi
fi

if [[ ! -x "$RUNTIME_BIN" ]]; then
  echo "silta-runtime binary not found at $RUNTIME_BIN" >&2
  echo "Run: cargo build -p silta-runtime" >&2
  exit 2
fi

POSTGRES_USER="$(docker exec "$CONTAINER_NAME" printenv POSTGRES_USER)"
POSTGRES_PASSWORD="$(docker exec "$CONTAINER_NAME" printenv POSTGRES_PASSWORD)"
POSTGRES_DB="$(docker exec "$CONTAINER_NAME" printenv POSTGRES_DB)"

DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"

exec "$EXPERIMENT_DIR/.venv/bin/silta" dev "$EXPERIMENT_DIR/silta_app.py:app" \
  --host "$HOST" \
  --port "$PORT" \
  --database-url "$DATABASE_URL" \
  --db-min-connections "$DB_MIN_CONNECTIONS" \
  --db-max-connections "$DB_MAX_CONNECTIONS" \
  --db-acquire-timeout-ms "$DB_ACQUIRE_TIMEOUT_MS" \
  "${CLICKHOUSE_ARGS[@]}" \
  --runtime-bin "$RUNTIME_BIN"
