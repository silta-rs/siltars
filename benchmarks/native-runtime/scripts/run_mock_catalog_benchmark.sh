#!/usr/bin/env bash
# Mock catalog benchmark (serialization only), following docs/architecture/performance.md.
# Profile 1, one core: Silta with 1 tokio thread vs FastAPI with 1 uvicorn worker
#   (conventional response path and ORJSONResponse).
# Profile 2, equal CPU budget: two cores per side, Silta with 2 tokio worker
#   threads vs FastAPI ORJSON with 2 uvicorn workers. macOS has no taskset or
#   cgroups, so the budget is set by the number of executors and the actual
#   consumption is measured over each server's process tree, which lets the
#   report show whether the budgets really were equal. Set WORKERS to compare
#   another equal budget (4 vs 4, 10 vs 10).
# Responses are compared by hash across servers before load (validation.txt).
#
# Usage, from experiments/poc-001-pip-native-runtime with the compose PostgreSQL up
# (the FastAPI baselines open a pool at startup even though the mock route never uses it):
#   SILTA_RUNTIME_BIN=../../target/release/silta-runtime scripts/run_mock_catalog_benchmark.sh
# Env: PYTHON (default .venv/bin/python), OUT (default reports/mock-catalog-<date>),
#      DUR (30s), RUNS (3), CONC (50), DATABASE_URL.
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd); cd "$HERE"
BIN=${SILTA_RUNTIME_BIN:-$HERE/../../target/release/silta-runtime}
PYV=${PYTHON:-$HERE/.venv/bin/python}
OUT=${OUT:-$HERE/results/mock-catalog-$(date +%F)}; DUR=${DUR:-30s}; RUNS=${RUNS:-3}; CONC=${CONC:-50}
WORKERS=${WORKERS:-2}
export DATABASE_URL=${DATABASE_URL:-postgresql://silta:silta@127.0.0.1:55432/silta_poc}
mkdir -p "$OUT"; LOG=$OUT/progress.log
say(){ echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
nap(){ perl -e "select(undef,undef,undef,$1)"; }
PIDS=()
cleanup(){ for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill -INT "$p" 2>/dev/null; done; nap 3; for p in "${PIDS[@]:-}"; do [ -n "$p" ] && { pkill -9 -P "$p" 2>/dev/null; kill -9 "$p" 2>/dev/null; }; done; PIDS=(); }
trap 'cleanup' INT TERM EXIT
wait_up(){ curl -s --retry 40 --retry-connrefused --retry-delay 1 -o /dev/null "$1" || say "NOT UP: $1"; }
start_silta(){ # name port threads
  TOKIO_WORKER_THREADS=$3 "$BIN" --host 127.0.0.1 --port "$2" --database-url "$DATABASE_URL" --db-max-connections 4 --db-min-connections 1 >"$OUT/$1.log" 2>&1 &
  PIDS+=("$!"); eval "PID_$1=$!"; wait_up "http://127.0.0.1:$2/ping"
  say "$1: pid $(eval echo \$PID_$1), $3 tokio worker thread(s)"
}
start_fastapi(){ # name port module workers
  $PYV -m uvicorn "$3" --app-dir "$HERE" --host 127.0.0.1 --port "$2" --workers "$4" --no-access-log --log-level warning >"$OUT/$1.log" 2>&1 &
  PIDS+=("$!"); eval "PID_$1=$!"; wait_up "http://127.0.0.1:$2/ping"; nap 2
  say "$1: pid $(eval echo \$PID_$1), $4 worker(s)"
}
validate(){ # ports...
  local n a ref port
  for n in 100 1000 3000 10000; do ref=""; for port in "$@"; do a=$(curl -s "http://127.0.0.1:$port/mock/rates/$n" | shasum | cut -c1-16); [ -z "$ref" ] && ref=$a; echo "count=$n port=$port sha=$a bytes=$(curl -s "http://127.0.0.1:$port/mock/rates/$n" | wc -c | tr -d ' ') $([ "$a" = "$ref" ] && echo same || echo DIFFERS)"; done; done >> "$OUT/validation.txt"
  say "validation: $(grep -c DIFFERS "$OUT/validation.txt") differing responses (0 expected)"
}
run_profile(){ $PYV "$HERE/scripts/bench_program.py" "$1" 2>&1 | tee -a "$LOG" | grep -v '^$'; }

say "=== mock catalog benchmark: DUR=$DUR RUNS=$RUNS CONC=$CONC bin=$BIN, load $(uptime | sed 's/.*load averages://') ==="
say "--- profile 1: one core ---"
start_silta silta1t 8621 1
start_fastapi faconv 8622 baselines.fastapi_db_app:app 1
start_fastapi faorj 8623 baselines.fastapi_db_app_orjson:app 1
validate 8621 8622 8623
cat > "$OUT/config-one-core.json" <<EOF
{"output_dir": "$OUT/one-core", "duration": "$DUR", "runs": $RUNS, "concurrency": $CONC,
 "targets": [
   {"name": "fastapi-conventional", "url": "http://127.0.0.1:8622", "pid": $PID_faconv},
   {"name": "fastapi-orjson", "url": "http://127.0.0.1:8623", "pid": $PID_faorj},
   {"name": "silta-1thread", "url": "http://127.0.0.1:8621", "pid": $PID_silta1t}],
 "cells": [
   {"name": "mock-100", "path": "/mock/rates/100"},
   {"name": "mock-100", "path": "/mock/rates/100"},
   {"name": "mock-1000", "path": "/mock/rates/1000"},
   {"name": "mock-3000", "path": "/mock/rates/3000"},
   {"name": "mock-10000", "path": "/mock/rates/10000"}]}
EOF
run_profile "$OUT/config-one-core.json"
cleanup; nap 3

say "--- profile 2: equal CPU budget, $WORKERS per side ---"
start_silta siltaN 8631 "$WORKERS"
start_fastapi faorjN 8632 baselines.fastapi_db_app_orjson:app "$WORKERS"
validate 8631 8632
cat > "$OUT/config-equal-budget.json" <<EOF
{"output_dir": "$OUT/equal-budget", "duration": "$DUR", "runs": $RUNS, "concurrency": $CONC,
 "targets": [
   {"name": "fastapi-orjson-${WORKERS}workers", "url": "http://127.0.0.1:8632", "pid": $PID_faorjN},
   {"name": "silta-${WORKERS}threads", "url": "http://127.0.0.1:8631", "pid": $PID_siltaN}],
 "cells": [
   {"name": "mock-1000", "path": "/mock/rates/1000"},
   {"name": "mock-3000", "path": "/mock/rates/3000"},
   {"name": "mock-10000", "path": "/mock/rates/10000"}]}
EOF
run_profile "$OUT/config-equal-budget.json"
cleanup
say "=== done, load $(uptime | sed 's/.*load averages://') ==="
