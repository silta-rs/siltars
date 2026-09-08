# Benchmark Results

Summary tables from the benchmark runs. Raw oha JSON, per-run CSVs and charts are
kept by the maintainers outside the repository and are available on request; the
runners under this directory reproduce every table. Every number here is
engineering evidence from one laptop, not a production claim. Method:
[docs/architecture/performance.md](../docs/architecture/performance.md).

## Methodology run, 2026-09-06 (PostgreSQL and ClickHouse, native runtime)

MacBook Pro M5, 10 cores, macOS; PostgreSQL 16 in Docker Desktop; local ClickHouse; oha 1.16 at
c=50; 30 s points, 3 alternating runs; Silta dev at d22edac plus the merged pool fix; FastAPI 0.141
on uvicorn 0.52 with uvloop, Python 3.14. RPS is the median of three runs, spread is (max - min) /
median, CPU is measured over the whole process tree of the server. One-row PostgreSQL cells carry a
23 to 37 percent spread from host noise; the pairs stay comparable because targets alternate.

### One core: Silta with one tokio worker thread vs FastAPI with one uvicorn worker

| Route | Target | RPS median | spread | p99 | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| one row, hot key | FastAPI, Pydantic response | 8,801 (0.99x) | 36.8% | 11.2 ms | 0.97 | 111 | 69 MB |
| one row, hot key | FastAPI, ORJSONResponse | 8,862 | 33.7% | 10.3 ms | 0.96 | 109 | 62 MB |
| one row, hot key | Silta, 1 thread | 10,604 (1.20x) | 36.6% | 9.8 ms | 0.66 | 62 | 22 MB |
| one row, random key | FastAPI, Pydantic response | 8,356 (0.98x) | 32.5% | 11.2 ms | 0.96 | 116 | 69 MB |
| one row, random key | FastAPI, ORJSONResponse | 8,521 | 23.0% | 10.8 ms | 0.96 | 113 | 56 MB |
| one row, random key | Silta, 1 thread | 10,276 (1.21x) | 28.5% | 10.5 ms | 0.66 | 64 | 22 MB |
| 100 rows | FastAPI, Pydantic response | 2,600 (0.66x) | 5.5% | 35.0 ms | 0.95 | 365 | 41 MB |
| 100 rows | FastAPI, ORJSONResponse | 3,922 | 2.6% | 21.6 ms | 0.96 | 246 | 63 MB |
| 100 rows | Silta, 1 thread | 5,262 (1.34x) | 18.1% | 17.1 ms | 0.93 | 175 | 23 MB |
| 3000 nested rows | FastAPI, Pydantic response | 105 (0.73x) | 8.6% | 695.4 ms | 0.98 | 9,353 | 179 MB |
| 3000 nested rows | FastAPI, ORJSONResponse | 144 | 6.5% | 546.7 ms | 0.97 | 6,757 | 157 MB |
| 3000 nested rows | Silta, 1 thread | 203 (1.40x) | 5.6% | 341.7 ms | 0.96 | 4,728 | 71 MB |

### Acquire ping on and off, same binary otherwise, one thread

| Route | Target | RPS median | spread | p99 | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| one row, hot key | ping on (dev default) | 9,849 | 4.9% | 11.0 ms | 0.66 | 67 | 22 MB |
| one row, hot key | ping off | 14,048 (1.43x) | 8.3% | 7.3 ms | 0.7 | 51 | 22 MB |
| one row, random key | ping on (dev default) | 10,093 | 13.2% | 9.4 ms | 0.67 | 67 | 22 MB |
| one row, random key | ping off | 13,728 (1.36x) | 1.7% | 8.0 ms | 0.7 | 51 | 22 MB |

### Ten executors per side, unequal CPU: Silta default threads vs FastAPI ORJSON with 10 workers, equal total database connections

| Route | Target | RPS median | spread | p99 | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| one row, random key | FastAPI ORJSON, 10 workers, 10 x 3 connections | 8,173 | 4.8% | 19.6 ms | 2.93 | 358 | 351 MB |
| one row, random key | Silta, 10 threads, 32 connections | 9,422 (1.15x) | 4.3% | 11.6 ms | 1.04 | 111 | 23 MB |
| 100 rows | FastAPI ORJSON, 10 workers, 10 x 3 connections | 5,200 | 8.9% | 33.4 ms | 3.08 | 596 | 328 MB |
| 100 rows | Silta, 10 threads, 32 connections | 5,902 (1.14x) | 7.4% | 18.2 ms | 1.52 | 274 | 24 MB |
| 3000 nested rows | FastAPI ORJSON, 10 workers, 10 x 3 connections | 245 | 2.9% | 442.0 ms | 3.22 | 12,849 | 679 MB |
| 3000 nested rows | Silta, 10 threads, 32 connections | 242 (0.99x) | 2.8% | 319.3 ms | 1.77 | 7,300 | 61 MB |

This profile gave each side ten executors rather than an equal CPU budget, and
the measured cores differ (Silta 1.0 to 1.8, FastAPI 2.9 to 3.2), so read it as
"ten workers against ten threads", not as a like-for-like comparison. Later
profiles fix the budget and verify it from the measured cores.

### ClickHouse: max_threads 1, 2 and 4 per query

| Route | Target | RPS median | spread | p99 | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| one row | FastAPI, max_threads 1 | 1,322 | 21.1% | 85.2 ms | 0.82 | 622 | 80 MB |
| one row | Silta, max_threads 1 | 1,969 (1.49x) | 21.2% | 128.8 ms | 0.31 | 158 | 25 MB |
| one row | FastAPI, max_threads 2 | 1,350 (1.02x) | 3.9% | 78.1 ms | 0.83 | 616 | 80 MB |
| one row | Silta, max_threads 2 | 1,992 (1.51x) | 11.2% | 131.9 ms | 0.31 | 158 | 25 MB |
| one row | FastAPI, max_threads 4 | 1,353 (1.02x) | 1.1% | 80.3 ms | 0.82 | 614 | 81 MB |
| one row | Silta, max_threads 4 | 1,897 (1.43x) | 10.9% | 135.8 ms | 0.3 | 157 | 25 MB |
| 1000 rows | FastAPI, max_threads 1 | 648 | 5.5% | 128.9 ms | 0.99 | 1,530 | 91 MB |
| 1000 rows | Silta, max_threads 1 | 1,678 (2.59x) | 3.2% | 88.5 ms | 1.8 | 1,075 | 35 MB |
| 1000 rows | FastAPI, max_threads 2 | 630 (0.97x) | 7.6% | 159.8 ms | 0.98 | 1,553 | 90 MB |
| 1000 rows | Silta, max_threads 2 | 1,690 (2.61x) | 11.6% | 91.8 ms | 1.85 | 1,108 | 35 MB |
| 1000 rows | FastAPI, max_threads 4 | 660 (1.02x) | 4.6% | 131.7 ms | 0.99 | 1,501 | 89 MB |
| 1000 rows | Silta, max_threads 4 | 1,762 (2.72x) | 8.0% | 90.7 ms | 1.89 | 1,064 | 36 MB |

## Runtime binaries A/B, 2026-09-08

Three builds under identical conditions after unrelated container stacks were stopped.

### Three builds under identical conditions, no Python parent, 10 threads, pool 50, c=50, 20 s points

| Route | Target | RPS median | spread | p99 | MB/s | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| one row, hot key | 1136e01 (Sep 5, PR 7) | 11,229 | 47.2% | 7.6 ms | 2 | 1.01 | 93 | 12 MB |
| one row, hot key | 730a0c1 (PR 9, typed serialization) | 11,314 (1.01x) | 35.1% | 8.9 ms | 2 | 1.03 | 91 | 14 MB |
| one row, hot key | d22edac (dev, Sep 6) | 11,486 (1.02x) | 34.5% | 7.8 ms | 2 | 1.06 | 92 | 14 MB |
| 100 rows | 1136e01 (Sep 5, PR 7) | 6,070 | 32.3% | 13.5 ms | 95 | 2.3 | 383 | 14 MB |
| 100 rows | 730a0c1 (PR 9, typed serialization) | 6,424 (1.06x) | 40.7% | 13.5 ms | 101 | 1.71 | 266 | 15 MB |
| 100 rows | d22edac (dev, Sep 6) | 6,584 (1.08x) | 35.0% | 12.6 ms | 104 | 1.73 | 268 | 15 MB |
| /ping | 1136e01 (Sep 5, PR 7) | 138,048 | 31.8% | 1.2 ms | 2 | 3.47 | 25 | 11 MB |
| /ping | 730a0c1 (PR 9, typed serialization) | 140,091 (1.01x) | 26.3% | 1.1 ms | 2 | 3.61 | 25 | 12 MB |
| /ping | d22edac (dev, Sep 6) | 136,722 (0.99x) | 10.4% | 1.2 ms | 2 | 3.49 | 26 | 12 MB |

Answer: no regression in dev; the typed-serialization change cut CPU per request on the 100-row
route by about 30 percent. The host drifted during the run (all builds lost a third of their
throughput between pass 1 and pass 3 together), so within-pass pairs are the comparison.

## Mock catalog, serialization only, 2026-09-08

`GET /mock/rates/{count}` serves rows from an in-memory catalog, so the request
path is HTTP plus serialization with no database. Run on the same laptop with the
unrelated container stacks stopped. Equal CPU budget per side, verified from the
measured cores.

### What Was Compared (mock catalog)

| | Silta | FastAPI, conventional | FastAPI, ORJSON |
| --- | --- | --- | --- |
| Server | axum on tokio, `silta-runtime` at this branch (`cargo build --release`) | uvicorn 0.52.4, uvloop, httptools | uvicorn 0.52.4, uvloop, httptools |
| Route body | borrowed slice of a `Vec` built once at startup, `serde_json::to_vec` | slice of a list of dicts built once at import, FastAPI default JSON response path | same slice, `ORJSONResponse` |
| Python | none on the request path | 3.14.7, FastAPI 0.141.1 | 3.14.7, FastAPI 0.141.1, orjson 3.12.0 |
| Response bytes | 26,235 / 263,117 / 791,517 / 2,640,919 for 100 / 1000 / 3000 / 10000 rows | identical (hash-checked before load, `validation.txt`) | identical |

Both profiles give the two sides the same CPU budget, set by the number of
executors because macOS has no CPU affinity or cgroups: one tokio worker thread
against one uvicorn worker, then two against two. The measured CPU columns show
whether the budgets really were equal. `oha` 1.16 at 50 connections, 30 second
points, 3 runs with the target order rotated on every run, medians with the min
to max spread. CPU and RSS cover the whole process tree of each server.

### Environment (mock catalog)

- macOS Darwin 25.6.0 arm64, Apple M5, 10 logical CPUs, 24 GiB RAM. Servers and
  the load generator share the cores.
- Runs of 2026-09-08 with the unrelated container stacks on the host stopped;
  run-to-run spread 1 to 11 percent in the one-core cells.
- Silta was started without `--metrics-listen` or an OTLP endpoint; no metrics
  middleware was installed.

### One core per side: 1 tokio thread vs 1 uvicorn worker

| Route | Target | RPS median | spread | p99 | MB/s | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 rows, 26 KB | FastAPI, conventional | 13,045 (0.77x) | 8.0% | 5.6 ms | 342 | 0.99 | 76 | 61 MB |
| 100 rows, 26 KB | FastAPI, ORJSONResponse | 17,029 | 3.5% | 3.9 ms | 447 | 0.99 | 58 | 43 MB |
| 100 rows, 26 KB | Silta, 1 thread | 37,728 (2.22x, 2.89x vs conventional) | 4.8% | 2.2 ms | 990 | 0.98 | 26 | 11 MB |
| 1000 rows, 263 KB | FastAPI, conventional | 2,082 (0.66x) | 10.7% | 46.8 ms | 548 | 0.99 | 475 | 29 MB |
| 1000 rows, 263 KB | FastAPI, ORJSONResponse | 3,143 | 3.3% | 31.2 ms | 827 | 0.99 | 316 | 30 MB |
| 1000 rows, 263 KB | Silta, 1 thread | 4,827 (1.54x, 2.32x vs conventional) | 5.3% | 13.5 ms | 1,270 | 0.99 | 205 | 12 MB |
| 3000 rows, 792 KB | FastAPI, conventional | 746 (0.65x) | 1.2% | 131.7 ms | 590 | 0.99 | 1,331 | 35 MB |
| 3000 rows, 792 KB | FastAPI, ORJSONResponse | 1,150 | 1.1% | 85.1 ms | 910 | 0.99 | 864 | 32 MB |
| 3000 rows, 792 KB | Silta, 1 thread | 1,745 (1.52x, 2.34x vs conventional) | 2.7% | 36.3 ms | 1,381 | 0.99 | 569 | 15 MB |
| 10000 rows, 2.6 MB | FastAPI, conventional | 223 (0.65x) | 5.1% | 448.3 ms | 590 | 0.99 | 4,449 | 44 MB |
| 10000 rows, 2.6 MB | FastAPI, ORJSONResponse | 341 | 6.9% | 287.3 ms | 901 | 0.99 | 2,909 | 45 MB |
| 10000 rows, 2.6 MB | Silta, 1 thread | 523 (1.53x, 2.34x vs conventional) | 2.1% | 113.3 ms | 1,380 | 0.99 | 1,903 | 23 MB |

### Two cores per side: 2 tokio threads vs 2 uvicorn workers

| Route | Target | RPS median | spread | p99 | MB/s | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 rows, 26 KB | FastAPI ORJSON, 2 workers | 28,589 | 15.1% | 2.1 ms | 750 | 1.98 | 69 | 201 MB |
| 100 rows, 26 KB | Silta, 2 threads | 55,742 (1.95x) | 18.6% | 1.4 ms | 1,462 | 1.97 | 35 | 67 MB |
| 1000 rows, 263 KB | FastAPI ORJSON, 2 workers | 5,396 | 9.4% | 18.0 ms | 1,420 | 1.99 | 369 | 200 MB |
| 1000 rows, 263 KB | Silta, 2 threads | 8,328 (1.54x) | 11.6% | 9.4 ms | 2,191 | 1.98 | 238 | 41 MB |
| 3000 rows, 792 KB | FastAPI ORJSON, 2 workers | 1,944 | 6.2% | 49.6 ms | 1,539 | 1.99 | 1,023 | 179 MB |
| 3000 rows, 792 KB | Silta, 2 threads | 2,971 (1.53x) | 7.1% | 26.1 ms | 2,352 | 1.99 | 669 | 70 MB |
| 10000 rows, 2.6 MB | FastAPI ORJSON, 2 workers | 573 | 5.5% | 170.6 ms | 1,513 | 1.99 | 3,477 | 214 MB |
| 10000 rows, 2.6 MB | Silta, 2 threads | 872 (1.52x) | 3.8% | 88.5 ms | 2,302 | 1.99 | 2,281 | 162 MB |

Measured consumption: Silta 1.97 to 1.99 cores, FastAPI 1.98 to 1.99 cores, so the
budgets held. Spread 4 to 19 percent.

### Load Generator Saturation Check

Silta with ten threads on `/mock/rates/1000` was driven first by one `oha`
process at 50 connections, then by three in parallel (`oha-saturation.txt`):

    one oha, c=50: rps=17226, server cpu cores=7.26
    three oha in parallel, c=50 each: rps=5821 5793 5794 sum=17408, server cpu cores=7.21

Three load generators produced the same throughput at the same server CPU as
one, so the load generator was not the ceiling in these runs and the ratios are
measurements rather than floors.

### Reading The Numbers (mock catalog)

- One core, 100 rows: 2.22x against ORJSON and 2.89x against the conventional
  path, at 26 against 58 and 76 CPU milliseconds per thousand requests.
- One core, 1000 to 10000 rows: 1.52 to 1.54x against ORJSON and 2.32 to 2.34x against the
  conventional path. Per request, Silta used 1.5 to 2.2 times less CPU than ORJSON across
  the four sizes; its single thread was busy 0.98 to 0.99 of a core.

- Two cores, same sizes: 1.52 to 1.95x against two ORJSON workers. Doubling the
  budget moves both sides, so the ratio, not the absolute number, is what carries
  across budgets.

- The Python side of this test is as fast as Python gets: the dictionaries exist
  before the request, so `orjson` only encodes. A real route builds those objects
  from database rows on every request, which is the cost the conventional path
  and the ClickHouse comparison pay for.
- Resident memory of the Rust runtime stays an order of magnitude below a
  multi-worker uvicorn deployment; the 10000-row cell leaves the allocator
  holding freed 2.6 MB buffers.

### Reproduce (mock catalog)

```bash
cd benchmarks/native-runtime
docker compose up -d --wait
cargo build --release --manifest-path ../../Cargo.toml -p silta-runtime
SILTA_RUNTIME_BIN=../../target/release/silta-runtime scripts/run_mock_catalog_benchmark.sh
```

`WORKERS=4` compares another equal budget. Output goes to `results/` and stays
out of git; the summary belongs in `benchmarks/RESULTS.md`.
