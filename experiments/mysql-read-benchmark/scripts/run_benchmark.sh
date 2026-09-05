#!/usr/bin/env bash
set -euo pipefail

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$EXPERIMENT_DIR/../.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$EXPERIMENT_DIR/results/latest}"
SILTA_PORT="${SILTA_PORT:-8301}"
FASTAPI_PORT="${FASTAPI_PORT:-8302}"
PIDS=()

cleanup() {
  if [[ "${#PIDS[@]}" -eq 0 ]]; then
    return
  fi
  for pid in "${PIDS[@]}"; do
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

cd "$EXPERIMENT_DIR"
docker compose up -d --wait mysql
uv sync --python 3.14
cargo build --manifest-path "$ROOT_DIR/Cargo.toml" --release -p silta-runtime

MYSQL_POOL_SIZE="${MYSQL_POOL_SIZE:-32}" SILTA_PORT="$SILTA_PORT" \
  "$EXPERIMENT_DIR/scripts/run_silta.sh" >"$EXPERIMENT_DIR/silta.log" 2>&1 &
PIDS+=("$!")
MYSQL_POOL_SIZE="${MYSQL_POOL_SIZE:-32}" FASTAPI_PORT="$FASTAPI_PORT" \
  "$EXPERIMENT_DIR/scripts/run_fastapi.sh" >"$EXPERIMENT_DIR/fastapi.log" 2>&1 &
PIDS+=("$!")

for port in "$SILTA_PORT" "$FASTAPI_PORT"; do
  ready=0
  for _ in {1..200}; do
    if curl --silent --fail "http://127.0.0.1:${port}/mysql/events/1" >/dev/null; then
      ready=1
      break
    fi
    sleep 0.1
  done
  if [[ "$ready" != 1 ]]; then
    cat "$EXPERIMENT_DIR/silta.log" >&2
    cat "$EXPERIMENT_DIR/fastapi.log" >&2
    exit 1
  fi
done

for limit in 1 100 1000; do
  for _ in {1..20}; do
    curl --silent --fail "http://127.0.0.1:${SILTA_PORT}/mysql/events/${limit}" >/dev/null
    curl --silent --fail "http://127.0.0.1:${FASTAPI_PORT}/mysql/events/${limit}" >/dev/null
  done
  curl --silent --fail "http://127.0.0.1:${SILTA_PORT}/mysql/events/${limit}" | jq -S . >"/tmp/silta-mysql-${limit}.json"
  curl --silent --fail "http://127.0.0.1:${FASTAPI_PORT}/mysql/events/${limit}" | jq -S . >"/tmp/fastapi-mysql-${limit}.json"
  cmp "/tmp/silta-mysql-${limit}.json" "/tmp/fastapi-mysql-${limit}.json"
done

"$EXPERIMENT_DIR/.venv/bin/python" \
  "$ROOT_DIR/experiments/poc-001-pip-native-runtime/scripts/run_load_curve.py" \
  --silta-url "http://127.0.0.1:${SILTA_PORT}" \
  --fastapi-url "http://127.0.0.1:${FASTAPI_PORT}" \
  --case "GET /mysql/events/1" \
  --case "GET /mysql/events/100" \
  --case "GET /mysql/events/1000" \
  --duration "${BENCH_DURATION:-10s}" \
  --runs "${BENCH_RUNS:-3}" \
  --concurrency "${BENCH_CONCURRENCY:-1,10,25,50,100,200}" \
  --output-dir "$OUTPUT_DIR"

"$EXPERIMENT_DIR/.venv/bin/python" "$EXPERIMENT_DIR/scripts/summarize.py" "$OUTPUT_DIR"
