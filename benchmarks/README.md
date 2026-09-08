# Benchmarks

Reproducible benchmarks of the Silta native runtime against realistic Python
baselines. They exist to answer architectural questions before the framework
grows, not to produce marketing numbers. Summary tables of every run are in
[RESULTS.md](RESULTS.md); the method is [docs/architecture/performance.md](../docs/architecture/performance.md).

| Directory | Question | Baselines |
| --- | --- | --- |
| [native-runtime/](native-runtime/README.md) | PostgreSQL and ClickHouse reads, one row to 3000 nested rows, `/ping`, the Rust to Python bridge, and an in-memory catalog that isolates serialization | FastAPI (conventional and `ORJSONResponse`), Litestar |
| [mysql-read/](mysql-read/README.md) | Native SQLx/MySQL reads for 1, 100 and 1000 rows | FastAPI with an optimized async MySQL driver |
| [media/](media/README.md) | In-memory binary and image responses without JSON or filesystem I/O | FastAPI |
| [metrics-export/](metrics-export/README.md) | Overhead of the Prometheus and OTLP metrics layer on `/ping` | Silta with metrics off |

## Rules

- Define the question before writing code, and measure Rust-only, Python-only
  and Rust/Python boundary paths separately.
- Compare against realistic baselines, including the optimized configuration a
  careful Python team would ship.
- Validate response bytes across servers before load; equal CPU budgets and
  connection limits; 30 to 60 second points; at least three alternating runs;
  report medians with their spread; record environment details.
- Raw `oha` JSON, per-run CSVs and charts are not committed. Runners write them
  to `results/` (ignored by git); maintainers archive them and share on request.
  Summaries go to [RESULTS.md](RESULTS.md).
- Do not make public performance claims from incomplete runs. Everything here is
  engineering evidence from one machine until the program in the methodology
  runs on a clean Linux host.

## Reporting

Every table in RESULTS.md carries requests per second (median of runs), spread,
p50/p99 latency, CPU cores and CPU milliseconds per thousand requests over the
whole server process tree, and RSS. Startup time and image size are recorded
where relevant.
