# Pool Acquire Ping: Before And After

This report measures one change in the native PostgreSQL pool: SQLx's default
`test_before_acquire` was switched off, so a native database request costs one
round trip to PostgreSQL instead of two. Everything else in the runtime, the
FastAPI baseline, the database and the machine is identical between the two runs.

The change lives in `pool_options()` in `crates/silta-runtime/src/lib.rs`. This
is engineering evidence for a Pre-Alpha prototype, not a production claim.

## Why The Ping Mattered

SQLx pings a pooled connection every time it is handed out. The ping is a
Sync/ReadyForQuery exchange, so it costs a full network round trip before the
real query is sent. On this setup PostgreSQL runs in Docker Desktop and every
round trip crosses the VM boundary through a userspace proxy: `pgbench` from the
host measures 0.123 ms per query at one connection and about 1 ms at fifty.
The query itself takes 0.04 ms inside the container. The runtime spends most of
its time waiting for that round trip (a CPU sample under load shows 88 percent of
samples parked on a condition variable and one core busy), so removing one of
the two round trips shows up directly as throughput.

## Environment

- OS: macOS Darwin 25.6.0 arm64.
- CPU: Apple M5, 10 logical CPUs.
- RAM: 24 GiB.
- Python: 3.14.7.
- Rust: rustc 1.98.0.
- Silta runtime: release build, `before` = `dev` at 1136e01, `after` = this branch.
- FastAPI: 0.141.1. Uvicorn: 0.52.4 with uvloop and httptools, one worker. asyncpg: 0.31.0.
- Benchmark tool: oha 1.16.0.
- PostgreSQL: 16.15, container `silta-poc-postgres`, `max_connections` 200, `shared_buffers` 512MB, `VACUUM ANALYZE` after seeding.
- `public.rates`: 250,000 seeded rows.
- Silta database pool: min 50, max 50. FastAPI database pool: max 50.
- Duration per point: 6 s. Runs per point: 1. Concurrency sweep: 10, 50, 200.
- Load generator, both servers, the Docker proxy and PostgreSQL share the same 10 cores. Host load average rose from 5 to 13 during the run.

## Single Connection: Round Trips Per Request

`oha -z 5s -c 1` against `GET /rates/EUR/USD`. With one connection the request
time is the sum of the round trips, so the drop is the ping itself.

| Runtime | RPS | mean | p50 | p99 |
| --- | ---: | ---: | ---: | ---: |
| before, ping + query | 3,341 | 0.298 ms | 0.277 ms | 0.627 ms |
| after, query only | 4,668 | 0.213 ms | 0.190 ms | 0.541 ms |

Reference points measured on the same machine: `pgbench` host to Docker, one
connection, 0.123 ms per query; Silta `GET /ping` at one connection, 0.032 ms per
request. The `before` request is about two database round trips plus HTTP; the
`after` request is about one.

## Load Curve: Before, After, FastAPI Baseline

Raw points are in `before/` and `after/` (CSV plus one `oha` JSON per point).
FastAPI was measured in both runs; the table shows the run that matches each
Silta column so the pairs were taken minutes apart under the same host load.

### `GET /rates/EUR/USD`, one row

| c | Silta before RPS | p99 | Silta after RPS | p99 | Change | FastAPI RPS | p99 | Ratio before | Ratio after |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 10,462 | 1.9 ms | 13,241 | 1.7 ms | +27% | 6,930 | 2.4 ms | 1.39x | 1.91x |
| 50 | 13,866 | 7.6 ms | 16,489 | 5.7 ms | +19% | 8,646 | 13.0 ms | 1.36x | 1.91x |
| 200 | 14,064 | 22.9 ms | 15,954 | 21.3 ms | +13% | 7,851 | 80.8 ms | 1.48x | 2.03x |

### `GET /rates`, 100 rows

| c | Silta before RPS | p99 | Silta after RPS | p99 | Change | FastAPI RPS | p99 | Ratio before | Ratio after |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 6,312 | 2.8 ms | 5,732 | 6.1 ms | -9% | 2,887 | 5.7 ms | 2.10x | 1.99x |
| 50 | 7,491 | 13.8 ms | 7,662 | 16.4 ms | +2% | 2,728 | 27.6 ms | 2.72x | 2.81x |
| 200 | 6,878 | 105.5 ms | 7,510 | 81.7 ms | +9% | 2,697 | 174.2 ms | 2.60x | 2.78x |

## Reading The Numbers

- The one-row path gains 13 to 27 percent in this run. An isolated A/B on the
  same day with a quieter host measured 12.1k to 18.1k RPS at 50 connections;
  the size of the gain tracks how expensive the round trip is at that moment.
- The 100-row path barely moves. Its request time is dominated by transferring
  and serializing 16 KB, so one fewer round trip is a small share.
- Throughput scales with pool size up to about 50 on this database and stops
  there; 200 pooled connections made p99 worse (95 ms) and the previous default
  of `min_connections = 1` combined with the ping could not even warm a pool of
  200 inside the 5 s acquire timeout. `run_silta_native.sh` now warms the pool
  to its maximum before the load starts.
- All points returned 100 percent 200 responses.

## Caveats

- One run per point and 6 s points. Treat differences under 10 percent as noise.
- PostgreSQL behind Docker Desktop is a poor benchmark target: the proxy costs
  about three host cores under load and sets a shared ceiling for every
  framework. Database benchmarks should move to a native PostgreSQL.
- The FastAPI baseline is a typical single-worker asyncpg setup. asyncpg does not
  ping on acquire, so the `before` comparison handicapped Silta by one round trip.
