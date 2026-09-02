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

## Local Snapshot

Environment:

- macOS local development machine.
- Existing Docker PostgreSQL container: `fpcurhub-postgres-1`.
- `public.rates`: 26,827 rows at measurement time.
- PostgreSQL `max_connections`: 20.
- Benchmark tool: `oha 1.16.0`.
- Requests: 5,000.
- Concurrency: 100.
- Silta runtime: release build, `db_max_connections = 10`.
- FastAPI baseline: uvicorn, uvloop, httptools, asyncpg pool max size 10,
  access logs disabled.

Measured results:

| Target | Requests/sec | p50 | p95 | p99 | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| Silta `/ping` | 106,615 | 0.77 ms | 1.72 ms | 2.68 ms | 100% |
| FastAPI `/ping` | 44,769 | 2.08 ms | 2.49 ms | 11.08 ms | 100% |
| Silta `/rates/EUR/USD` | 7,187 | 13.33 ms | 17.35 ms | 22.83 ms | 100% |
| FastAPI `/rates/EUR/USD` | 7,474 | 11.56 ms | 25.39 ms | 33.13 ms | 100% |
| Silta `/rates` | 5,532 | 17.33 ms | 21.19 ms | 23.34 ms | 100% |
| FastAPI `/rates` | 3,555 | 26.97 ms | 35.03 ms | 51.47 ms | 100% |

Interpretation:

- Rust HTTP/router/JSON overhead is already much lower on `/ping`.
- Silta is faster on the larger JSON response path `/rates`.
- FastAPI is slightly faster on the single-row DB path, so the next optimization
  target is database driver and pool overhead, not HTTP routing.
- PostgreSQL pool sizing is a hard local bottleneck. The local container has
  only 20 allowed connections; setting the runtime pool too high causes
  connection starvation and 500 responses from pool acquire timeout.
