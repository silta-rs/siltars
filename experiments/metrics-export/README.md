# Metrics Export Overhead Smoke Test

The [script](benchmark.py) uses a single runtime binary and native `GET /ping`
with keep-alive connections. It compares instrumentation disabled, Prometheus
enabled, and Prometheus plus OTLP export to an unavailable local port. It uses
only the Python standard library and validates every JSON response.

```bash
CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 cargo build --release -j 2 -p silta-runtime
python experiments/metrics-export/benchmark.py \
  --runtime-bin "$PWD/target/release/silta-runtime" \
  --output experiments/metrics-export/results.json
```

Defaults: 16 concurrent connections, 1000 measured requests per connection,
100 warmup requests per connection, five rounds. Mode order rotates by round.
OTLP interval and request timeout are both 100 ms for the outage case.
Prometheus aggregates are enabled, but the load generator does not concurrently
scrape them. Each round starts a fresh runtime.

## Local result, 2026-09-05

The full environment, individual rounds, and medians are in [results.json](results.json).
The build used Rust 1.98.1, release optimization and one codegen unit on a shared
Linux host. All 240,000 measured responses were correct.

| Mode | Median requests/s | Median p50 ms | Median p95 ms | Median p99 ms |
| --- | ---: | ---: | ---: | ---: |
| Off | 45,992 | 0.326 | 0.430 | 0.591 |
| Prometheus | 47,357 | 0.309 | 0.479 | 0.582 |
| Prometheus + unavailable OTLP | 50,957 | 0.287 | 0.433 | 0.595 |

This smoke test did not isolate the instrumentation's CPU overhead. The enabled
modes showing higher throughput is evidence of generator/host noise, not an
optimization claim. Prometheus p95 was higher in this run. The experiment proves
correct responses under this workload and provides a reproducible starting point;
it does not prove zero overhead, production capacity, or equivalence to a bare
Rust server. Dedicated host measurements with a faster independent load generator,
CPU/RSS tracking, sustained scrapes and larger route cardinality remain necessary
for a performance claim.
