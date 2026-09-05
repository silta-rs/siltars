# MySQL read benchmark

This alpha experiment compares the native Silta SQLx/MySQL path with an
optimized single-worker FastAPI baseline using `asyncmy` server-side prepared
statements, `uvloop`, `httptools`, and `orjson`.

Both applications execute the same fixed indexed SQL and return the same JSON
for 1, 100, and 1,000 rows. The dataset contains 100,000 deterministic rows. The
runner warms both paths and verifies response equality before collecting load
curves.

## Run

Requirements: Docker Desktop, Rust, `uv`, `oha`, `curl`, and `jq`.

```bash
cd experiments/mysql-read-benchmark
./scripts/run_benchmark.sh
```

The default run uses three 10-second samples per concurrency level. For a
short smoke test:

```bash
BENCH_DURATION=2s BENCH_RUNS=1 BENCH_CONCURRENCY=1,25,100 ./scripts/run_benchmark.sh
```

Results, raw `oha` JSON, CSV, and SVG charts are written to `results/latest`.

## MySQL configuration

The dedicated MySQL 8.4 container uses a 1 GiB InnoDB buffer pool, 256 maximum
connections, cached threads and table metadata, SSD-oriented I/O capacity, and
durable redo/binlog flush settings. These settings prevent an undersized
default buffer pool from dominating a read benchmark while retaining durable
defaults appropriate for later write tests.

This is an alpha engineering experiment on one machine, not a general
performance claim. Run the full profile several times on an otherwise idle
host before publishing comparisons.
