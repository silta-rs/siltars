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
DB_MAX_CONNECTIONS="${SILTA_DB_MAX_CONNECTIONS:-10}"
# Benchmark runs start with a warm pool: opening connections through the Docker
# network during the first seconds of a load test distorts the early points.
DB_MIN_CONNECTIONS="${SILTA_DB_MIN_CONNECTIONS:-$DB_MAX_CONNECTIONS}"
DB_ACQUIRE_TIMEOUT_MS="${SILTA_DB_ACQUIRE_TIMEOUT_MS:-5000}"

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
  --runtime-bin "$RUNTIME_BIN"
