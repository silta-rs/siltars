#!/usr/bin/env bash
set -euo pipefail

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$EXPERIMENT_DIR/../.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$EXPERIMENT_DIR/results/latest}"
SILTA_PORT="${SILTA_PORT:-8401}"
FASTAPI_PORT="${FASTAPI_PORT:-8402}"
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
uv sync --python 3.14
cargo build --manifest-path "$ROOT_DIR/Cargo.toml" --release -p silta-runtime

SILTA_PORT="$SILTA_PORT" ./scripts/run_silta.sh >silta.log 2>&1 &
PIDS+=("$!")
FASTAPI_PORT="$FASTAPI_PORT" ./scripts/run_fastapi.sh >fastapi.log 2>&1 &
PIDS+=("$!")

for port in "$SILTA_PORT" "$FASTAPI_PORT"; do
  ready=0
  for _ in {1..200}; do
    if curl --silent --fail "http://127.0.0.1:${port}/media/blob/64k" >/dev/null; then
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

verify_response() {
  local port="$1"
  local endpoint="$2"
  local expected_type="$3"
  local expected_size="$4"
  local label="$5"
  local body="/tmp/${label}-${endpoint//\//-}"
  local headers="${body}.headers"

  curl --silent --fail --dump-header "$headers" \
    "http://127.0.0.1:${port}/${endpoint}" >"$body"
  [[ "$(wc -c <"$body" | tr -d ' ')" == "$expected_size" ]]
  tr -d '\r' <"$headers" | grep -Eiq "^content-type: ${expected_type}$"
}

while read -r endpoint expected_type expected_size; do
  verify_response "$SILTA_PORT" "$endpoint" "$expected_type" "$expected_size" silta
  verify_response "$FASTAPI_PORT" "$endpoint" "$expected_type" "$expected_size" fastapi
  cmp "/tmp/silta-${endpoint//\//-}" "/tmp/fastapi-${endpoint//\//-}"
done <<'CASES'
media/blob/64k application/octet-stream 65536
media/blob/1m application/octet-stream 1048576
media/image.bmp image/bmp 786486
CASES

if ! file /tmp/silta-media-image.bmp | grep -q "PC bitmap"; then
  echo "generated image is not recognized as BMP" >&2
  exit 1
fi

echo "verified byte-identical payloads, MIME types, sizes, and BMP structure"

"$EXPERIMENT_DIR/.venv/bin/python" \
  "$ROOT_DIR/experiments/poc-001-pip-native-runtime/scripts/run_load_curve.py" \
  --silta-url "http://127.0.0.1:${SILTA_PORT}" \
  --fastapi-url "http://127.0.0.1:${FASTAPI_PORT}" \
  --case "GET /media/blob/64k" \
  --case "GET /media/blob/1m" \
  --case "GET /media/image.bmp" \
  --duration "${BENCH_DURATION:-10s}" \
  --runs "${BENCH_RUNS:-3}" \
  --concurrency "${BENCH_CONCURRENCY:-1,10,25,50,100}" \
  --output-dir "$OUTPUT_DIR"

"$EXPERIMENT_DIR/.venv/bin/python" "$EXPERIMENT_DIR/scripts/summarize.py" "$OUTPUT_DIR"
