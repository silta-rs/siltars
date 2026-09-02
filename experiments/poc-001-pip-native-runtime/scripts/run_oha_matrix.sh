#!/usr/bin/env bash
set -euo pipefail

SILTA_URL="${SILTA_URL:-http://127.0.0.1:8104}"
FASTAPI_URL="${FASTAPI_URL:-http://127.0.0.1:8103}"
REQUESTS="${REQUESTS:-5000}"
CONCURRENCY="${CONCURRENCY:-100}"

if ! command -v oha >/dev/null 2>&1; then
  echo "oha is required. Install with: brew install oha" >&2
  exit 2
fi

run_target() {
  local label="$1"
  local url="$2"

  printf '\n=== %s ===\n' "$label"
  oha -n "$REQUESTS" -c "$CONCURRENCY" --no-tui "$url"
}

run_target "SILTA /ping" "$SILTA_URL/ping"
run_target "SILTA /rates/EUR/USD" "$SILTA_URL/rates/EUR/USD"
run_target "SILTA /rates" "$SILTA_URL/rates"
run_target "FASTAPI /ping" "$FASTAPI_URL/ping"
run_target "FASTAPI /rates/EUR/USD" "$FASTAPI_URL/rates/EUR/USD"
run_target "FASTAPI /rates" "$FASTAPI_URL/rates"
