# ClickHouse Alpha Load Curve: 1, 100 And 1000 Rows

Silta's experimental native ClickHouse routes against a FastAPI baseline on the
same local ClickHouse. Three payload sizes, four concurrency levels, one run per
point, 6 s per point. Engineering evidence for a Pre-Alpha prototype, not a
production claim.

## What Was Compared

| | Silta | FastAPI |
| --- | --- | --- |
| HTTP server | axum on tokio, native Rust | uvicorn 0.52.4, uvloop, httptools, one worker |
| ClickHouse client | `clickhouse` crate 0.15.2, HTTP, RowBinary into typed rows | `clickhouse-connect` 1.8.0 async client on aiohttp 3.14.3 |
| Connections to ClickHouse | hyper connection pool | aiohttp connector, per-host limit raised to 50 |
| JSON | Serde from typed structs | dicts from `column_names` and `result_rows`, FastAPI default response |
| SQL | identical, `rate` and `ts_utc` converted to text server-side | identical |

Routes: `GET /ch/rates/{base}/{quote}` (latest row for a pair), `GET /ch/rates`
(latest 100 rows), `GET /ch/rates/1000` (latest 1000 rows). Response bodies are
byte-identical in size between the two servers: 146 B, 15,168 B and 151,333 B.

## Environment

- OS: macOS Darwin 25.6.0 arm64. CPU: Apple M5, 10 logical CPUs. RAM: 24 GiB.
- ClickHouse 26.4.2.10, local Homebrew install, HTTP interface on 127.0.0.1:8123, default user, `max_concurrent_queries` unlimited.
- Table `silta_poc.rates`: 250,000 rows, MergeTree `ORDER BY (ts_utc, base, quote)`, one part after `OPTIMIZE FINAL`, seeded by `scripts/seed_clickhouse.sh`.
- Python 3.14.7. FastAPI 0.141.1. Rust 1.98.0, release build of this branch.
- Benchmark tool: oha 1.16.0. Duration per point 6 s, one run per point, concurrency 1, 10, 50, 200.
- Load generator, both servers and ClickHouse share the same 10 cores. Another benchmark (a MySQL container) was running on the machine part of the time; host load average was between 8 and 14 at the start of each run and 35 to 80 at the end because ClickHouse saturates the cores at 50 and 200 connections.

## Results

All points returned 100 percent `200` responses. Raw `oha` JSON for every point is
under each run directory in `raw/`.

### Run A: `max_threads = 1` per query on both clients (`max-threads-1/`)

| Endpoint | c | Silta RPS | p50 | p99 | FastAPI RPS | p50 | p99 | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `/ch/rates/EUR/USD` (one row) | 1 | 859 | 1.1 ms | 2.8 ms | 244 | 3.7 ms | 10.8 ms | 3.52x |
| `/ch/rates/EUR/USD` (one row) | 10 | 3,227 | 2.6 ms | 10.8 ms | 2,024 | 4.6 ms | 11.8 ms | 1.59x |
| `/ch/rates/EUR/USD` (one row) | 50 | 2,792 | 4.4 ms | 137.2 ms | 1,737 | 26.0 ms | 78.3 ms | 1.61x |
| `/ch/rates/EUR/USD` (one row) | 200 | 2,483 | 73.5 ms | 273.9 ms | 1,588 | 120.4 ms | 260.1 ms | 1.56x |
| `/ch/rates` (100 rows, 15 KB) | 1 | 944 | 1.0 ms | 2.9 ms | 265 | 3.6 ms | 9.6 ms | 3.56x |
| `/ch/rates` (100 rows, 15 KB) | 10 | 2,612 | 3.5 ms | 8.7 ms | 1,822 | 5.0 ms | 12.8 ms | 1.43x |
| `/ch/rates` (100 rows, 15 KB) | 50 | 2,497 | 7.0 ms | 127.5 ms | 1,645 | 29.0 ms | 65.4 ms | 1.52x |
| `/ch/rates` (100 rows, 15 KB) | 200 | 2,308 | 75.5 ms | 363.1 ms | 1,495 | 122.8 ms | 282.7 ms | 1.54x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 1 | 235 | 3.8 ms | 12.6 ms | 172 | 5.3 ms | 17.8 ms | 1.37x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 10 | 1,927 | 4.7 ms | 13.1 ms | 638 | 14.0 ms | 46.4 ms | 3.02x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 50 | 1,641 | 25.7 ms | 93.0 ms | 319 | 135.8 ms | 344.2 ms | 5.14x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 200 | 1,269 | 139.2 ms | 627.9 ms | 441 | 305.4 ms | 4185.7 ms | 2.88x |

This is the recommended configuration for point reads: one thread per query
instead of ClickHouse's default ten-way fan-out, which oversubscribes the server
as soon as fifty requests are in flight.

### Run B: server default `max_threads` (`default-threads/`)

| Endpoint | c | Silta RPS | p50 | p99 | FastAPI RPS | p50 | p99 | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `/ch/rates/EUR/USD` (one row) | 1 | 939 | 1.0 ms | 2.2 ms | 224 | 4.5 ms | 10.2 ms | 4.19x |
| `/ch/rates/EUR/USD` (one row) | 10 | 2,661 | 2.8 ms | 20.3 ms | 1,769 | 5.3 ms | 12.4 ms | 1.50x |
| `/ch/rates/EUR/USD` (one row) | 50 | 1,557 | 17.6 ms | 178.0 ms | 1,563 | 30.6 ms | 78.1 ms | 1.00x |
| `/ch/rates/EUR/USD` (one row) | 200 | 1,545 | 113.8 ms | 396.3 ms | 1,482 | 139.7 ms | 222.7 ms | 1.04x |
| `/ch/rates` (100 rows, 15 KB) | 1 | 901 | 1.0 ms | 2.0 ms | 263 | 3.6 ms | 9.0 ms | 3.42x |
| `/ch/rates` (100 rows, 15 KB) | 10 | 1,869 | 4.2 ms | 26.5 ms | 1,171 | 7.7 ms | 24.4 ms | 1.60x |
| `/ch/rates` (100 rows, 15 KB) | 50 | 2,078 | 9.6 ms | 142.7 ms | 996 | 47.9 ms | 101.6 ms | 2.09x |
| `/ch/rates` (100 rows, 15 KB) | 200 | 1,838 | 102.4 ms | 310.8 ms | 959 | 189.3 ms | 454.2 ms | 1.92x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 1 | 304 | 3.1 ms | 5.4 ms | 156 | 6.1 ms | 19.0 ms | 1.95x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 10 | 1,556 | 6.1 ms | 12.2 ms | 356 | 25.4 ms | 69.6 ms | 4.37x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 50 | 1,575 | 26.8 ms | 103.7 ms | 534 | 91.8 ms | 146.6 ms | 2.95x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 200 | 1,378 | 137.4 ms | 375.3 ms | 426 | 447.0 ms | 1069.0 ms | 3.24x |

## Reading The Numbers

- At one connection the request is one ClickHouse round trip plus the framework:
  Silta answers the one-row and 100-row queries in about 1 ms, FastAPI in 4 to 5 ms,
  a 3.5x gap that is the HTTP, driver and JSON overhead of the two stacks.
- From ten connections upward ClickHouse becomes the bottleneck. Its HTTP query
  path costs roughly 0.5 ms for `SELECT 1` and 1 to 3 ms for these reads, and the
  server consumes every core; both frameworks converge on the same ceiling of
  about 2.5 to 3.2k requests per second for one row. The remaining 1.4 to 1.6x is
  what the framework adds on top of a saturated database.
- The 1000-row path shows the largest gap under load, 3 to 5x at 10 to 50
  connections, because Python spends its time turning 1000 rows into dicts and
  JSON while Rust deserializes RowBinary into structs and serializes with Serde.
- `max_threads = 1` raised Silta's one-row throughput by 60 to 80 percent at 50
  and 200 connections and FastAPI's 100-row throughput by 50 to 65 percent. It is
  a per-query setting sent by both clients, not a server change.

## A Trap Worth Recording

The first version of the queries selected `toString(ts_utc) AS ts_utc` and then
wrote `ORDER BY ts_utc DESC`. ClickHouse resolves that `ts_utc` to the alias, so
it sorted strings over all 250,000 rows on every request: 11.5 ms per query
instead of 2.5 ms with `ORDER BY rates.ts_utc DESC`. Both servers had the same
SQL, so the ratio was fair, but the absolute numbers were meaningless. That run is
kept in `untuned/` as a cautionary example.

### Run C: alias trap, before the SQL fix (`untuned/`)

| Endpoint | c | Silta RPS | p50 | p99 | FastAPI RPS | p50 | p99 | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `/ch/rates/EUR/USD` (one row) | 1 | 118 | 8.1 ms | 15.7 ms | 174 | 5.5 ms | 9.5 ms | 0.68x |
| `/ch/rates/EUR/USD` (one row) | 10 | 513 | 15.7 ms | 85.0 ms | 602 | 15.1 ms | 47.6 ms | 0.85x |
| `/ch/rates/EUR/USD` (one row) | 50 | 557 | 70.8 ms | 309.3 ms | 539 | 79.9 ms | 297.7 ms | 1.03x |
| `/ch/rates/EUR/USD` (one row) | 200 | 653 | 313.9 ms | 688.3 ms | 585 | 330.6 ms | 749.5 ms | 1.12x |
| `/ch/rates` (100 rows, 15 KB) | 1 | 90 | 10.4 ms | 25.4 ms | 72 | 12.8 ms | 26.7 ms | 1.25x |
| `/ch/rates` (100 rows, 15 KB) | 10 | 223 | 34.5 ms | 161.0 ms | 213 | 42.0 ms | 145.8 ms | 1.05x |
| `/ch/rates` (100 rows, 15 KB) | 50 | 188 | 241.2 ms | 1238.8 ms | 195 | 255.1 ms | 562.0 ms | 0.97x |
| `/ch/rates` (100 rows, 15 KB) | 200 | 177 | 738.5 ms | 3573.7 ms | 223 | 995.3 ms | 1316.8 ms | 0.79x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 1 | 77 | 11.3 ms | 31.3 ms | 94 | 10.1 ms | 21.6 ms | 0.82x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 10 | 201 | 41.7 ms | 156.3 ms | 173 | 50.6 ms | 244.8 ms | 1.16x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 50 | 220 | 226.0 ms | 465.7 ms | 198 | 241.6 ms | 536.2 ms | 1.11x |
| `/ch/rates/1000` (1000 rows, 151 KB) | 200 | 197 | 804.8 ms | 4181.4 ms | 220 | 1263.0 ms | 1683.6 ms | 0.89x |

## Caveats

- One run per point and 6 s points on a shared, noisy machine. Treat differences
  under 15 percent as noise.
- ClickHouse is an analytical store; a per-request round trip for one row is not
  what it is built for. These numbers describe framework overhead in front of a
  saturated database, not ClickHouse capacity.
- The FastAPI baseline is the official driver with default settings plus a raised
  connector limit. `clickhouse-connect` also offers a native-format path and
  server-side JSON that were not measured here.
- The Silta routes are Pre-Alpha: mapped by symbolic handler name, no query plan,
  no validation contract.
