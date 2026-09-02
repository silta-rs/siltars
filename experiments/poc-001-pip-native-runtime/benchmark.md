# Benchmark Plan

This experiment compares a Silta native endpoint against realistic Python async
baselines.

It must not publish claims such as "dozens of times faster" until results are
reproducible across environments.

## Tools

Use one benchmark tool consistently across all targets.

Recommended:

```bash
oha -z 30s -c 100 http://127.0.0.1:8000/ping
```

Alternative:

```bash
wrk -t4 -c100 -d30s http://127.0.0.1:8000/ping
```

Fallback built into this repository:

```bash
python scripts/bench_http.py \
  --label fastapi-ping \
  --url http://127.0.0.1:8101/ping \
  --requests 1000 \
  --concurrency 50 \
  --output results/fastapi-ping.json
```

This fallback is useful for local smoke testing, but `oha` or `wrk` should be
preferred for serious benchmark runs.

## Targets

### Silta Native Endpoint

Run:

```bash
cargo build -p silta-runtime --release
SILTA_RUNTIME_BIN="$PWD/../../target/release/silta-runtime" \
  SILTA_PORT=8104 \
  ./scripts/run_silta_native.sh
```

Benchmark:

```bash
python scripts/bench_http.py \
  --label silta-ping \
  --url http://127.0.0.1:8104/ping \
  --requests 1000 \
  --concurrency 50 \
  --output results/silta-ping.json
```

Silta with PostgreSQL:

```bash
python scripts/bench_http.py \
  --label silta-db-rates \
  --url http://127.0.0.1:8104/rates \
  --requests 1000 \
  --concurrency 50 \
  --output results/silta-db-rates.json
```

### FastAPI Baseline

Run:

```bash
python -m uvicorn baselines.fastapi_app:app \
  --host 127.0.0.1 \
  --port 8101 \
  --loop uvloop \
  --http httptools
```

Benchmark:

```bash
oha -z 30s -c 100 http://127.0.0.1:8101/ping
```

FastAPI with PostgreSQL:

```bash
./scripts/run_fastapi_rates_baseline.sh
```

Benchmark:

```bash
python scripts/bench_http.py \
  --label fastapi-db-rates \
  --url http://127.0.0.1:8103/rates \
  --requests 1000 \
  --concurrency 50 \
  --output results/fastapi-db-rates.json
```

This baseline uses the existing local `fpcurhub-postgres-1` container and reads
from `public.rates`.

### Litestar Baseline

Run:

```bash
litestar --app baselines.litestar_app:app run \
  --host 127.0.0.1 \
  --port 8102
```

Benchmark:

```bash
oha -z 30s -c 100 http://127.0.0.1:8102/ping
```

## Measurements

Record:

- Requests per second.
- p50 latency.
- p95 latency.
- p99 latency.
- Error count.
- RSS memory.
- CPU usage.
- Startup time.
- Python version.
- Silta version or commit.
- OS.
- CPU model.
- RAM.

## Process

1. Run each server with one worker unless the test explicitly measures
   multi-worker behavior.
2. Warm up each target before recording results.
3. Run each benchmark at least three times.
4. Capture memory and CPU while the benchmark is running.
5. Record the exact command used.
6. Keep raw benchmark output.

## Interpretation

The useful comparison is not just framework overhead. The real Silta question
is whether endpoints configured from Python can execute through native Rust
modules without Python on the hot path.

The minimum benchmark matrix should eventually include:

- Rust-only endpoint.
- Python handler endpoint.
- Rust endpoint configured from Python.
- Rust -> Python -> Rust endpoint.
- CRUD plus PostgreSQL endpoint.

## Performance Gate

Compare measured output:

```bash
python scripts/compare_results.py \
  --silta results/silta-ping.json \
  --fastapi results/fastapi-ping.json \
  --min-speedup 1.01
```

This gate proves only the measured workload. It must not be turned into a public
claim without repeated, reproducible runs.
