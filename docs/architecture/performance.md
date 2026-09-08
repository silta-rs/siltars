# Performance

Silta's performance goal is architectural: keep common backend infrastructure on
the native Rust hot path and enter Python only when application logic requires
it.

The project does not make production performance claims yet. POC benchmark
snapshots may be summarized in `benchmarks/RESULTS.md` as engineering evidence, but they
must state their limitations and reproduction steps.

## Principles

- Measure before publishing claims.
- Keep benchmarks reproducible and checked into the repository.
- Compare against realistic Python stacks and Rust baselines.
- Separate cold start, steady-state latency, throughput, and memory footprint.
- Track Python boundary crossings explicitly.
- Avoid optimizing code paths that the final architecture may not use.

## Prioritized Benchmark Program

The program below orders database experiments by product value and by how well
they isolate Silta's native execution advantage. Expected advantages are
hypotheses, not performance claims.

| Priority | Database and configuration | Workload | Hypothesis |
| ---: | --- | --- | --- |
| 1 | PostgreSQL on Linux; warm data; pools of 8, 16, 32 and 64 connections; indexed filtering and ordering | Product catalog, order list or audit log returning 100 to 1,000 nested records with cursor pagination | Native row decoding and response construction should avoid large Python object graphs and produce a durable advantage. |
| 2 | The same PostgreSQL; uniformly random keys and a separate hot-key distribution; acquire-ping modes measured independently | User profile, settings or current price | Isolate and remove the current limitation on one-row reads before making broader database claims. |
| 3 | ClickHouse ordered by tenant and time; `max_threads` 1, 2 and 4; bounded concurrent queries | 1,000 to 10,000 events or prepared time series for a dashboard | Large result handling should favor the native path; expensive database aggregation leaves less application overhead to remove. |
| 4 | PostgreSQL and ClickHouse; chunked reads; bounded concurrent exports | Streaming CSV and NDJSON exports from 100,000 to 1,000,000 rows | Measure memory, time to first byte and the effect of exports on p99 latency of normal routes. |
| 5 | Redis; identical `MGET` or pipeline batches in both implementations | Batch prices, feature flags or catalog enrichment | A fast store exposes application overhead, but a native Silta adapter does not exist yet. Both baselines must use equivalent batching because [pipelining reduces round trips](https://redis.io/docs/latest/develop/using-commands/pipelining/). |
| 6 | SQLite on a local file; read-heavy load; rollback journal and WAL profiles when writes are present | Reference data and edge-service configuration | No database network exchange makes this a separate application class. Tests must model SQLite's single writer and WAL checkpoint behavior; a native Silta adapter does not exist yet. See [SQLite WAL concurrency](https://www.sqlite.org/wal.html#concurrency). |

MySQL remains a control workload. The existing
[MySQL experiment](../../benchmarks/mysql-read/README.md) already
uses MySQL 8.4, a 1 GiB buffer pool, a warm 32-connection pool, and an optimized
FastAPI baseline with `asyncmy`, prepared statements and direct ORJSON
responses. Before expanding it, profile pool acquisition and acquire ping, then
replace fixed first-row reads with indexed filters and cursor pagination.

## Current Evidence

The existing
[ClickHouse alpha report](../../benchmarks/RESULTS.md)
contains a result up to 5.14x for 1,000 rows. It is directional evidence only:
the host was running other work, each point lasted six seconds and each point
was measured once. It must not be presented as a prediction for a clean Linux
comparison.

The next product-facing implementation target is a declarative PostgreSQL
catalog route with indexed filtering and cursor pagination, accompanied by pool
acquisition metrics and a configurable acquire policy. Chunked export follows
after that path is correct and measured.

## Comparison Contract

Every publishable comparison must satisfy all of the following:

- Run on Linux without the Docker Desktop network proxy. Use a separate load
  generator; add a database on a separate host as a second profile and record
  its measured RTT.
- Run a one-core comparison and a matched multi-core scaling comparison. Apply
  equal CPU limits and equal total database connection limits to both stacks.
- Warm the applications and data, then run each point for 30 to 60 seconds at
  least three times. Alternate Silta and baseline runs to reduce time-dependent
  host bias.
- Use deterministic, seeded request sequences. Point-read reports must separate
  random keys from a documented hot-key distribution.
- Validate status, headers and exact response bytes before load generation.
  Align timestamps, decimal values, nulls, Unicode, ordering and error bodies.
- Include a conventional FastAPI implementation and an optimized FastAPI
  implementation. Measure typed Pydantic serialization separately from direct
  `ORJSONResponse` or pre-serialized bytes; FastAPI supports custom responses
  and streaming, so Serde alone is not a sufficient comparison argument. See
  [FastAPI custom responses](https://fastapi.tiangolo.com/advanced/custom-response/).
- Record release-build flags, dependency versions, database configuration,
  schema, indexes, query plans, worker counts, pool sizes and all runtime
  environment variables.

## Success Metric

The primary result is successful requests per second at a predeclared p99
latency limit and equal CPU and memory budgets. Maximum RPS is secondary.
Reports must also include p50, p95 and p99 latency, CPU, RSS, error rate,
response bytes and time to first byte for streaming responses.

Instrument database pool wait, acquire validation, query execution, row decode,
response construction, serialization and socket write separately. A framework
win cannot be inferred when database saturation explains the ceiling. Report
the median of repeated runs and their dispersion; do not label a difference as
an advantage when it is within observed run-to-run noise.

## Reliability Matrix

Database changes require integration coverage beyond happy-path benchmarks:

- database restart while traffic is active;
- pool exhaustion and bounded waiting;
- connection loss during a query;
- SQL cancellation after an HTTP deadline or client disconnect;
- exact numeric, timestamp, null and Unicode behavior;
- slow clients and early disconnects during large responses;
- bounded RSS and resource release after large reads and exports;
- SQLite writer contention and WAL checkpoint pressure;
- Redis pipeline batch limits and memory behavior.

These checks should run against real database services in CI before pool policy
or streaming routes are treated as supported behavior.

## Benchmark Hygiene

Benchmarks should document:

- Hardware and operating system.
- Rust and Python versions.
- Dependency versions.
- Runtime flags and environment variables.
- Workload shape.
- Warmup strategy.
- Statistical treatment of results.

Runnable prototypes, raw samples and alpha reports live under
[`benchmarks/`](../../benchmarks/).
