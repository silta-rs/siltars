# Mock Catalog: Serialization-Only Benchmark, 2026-09-07

`GET /mock/rates/{count}` serves the first `count` rows of a deterministic
in-memory catalog with the same nested shape as `/rates/bulk`. There is no
database on the request path, so the route measures what the runtime itself
adds: HTTP, routing and turning already-loaded records into JSON. Engineering
evidence from one laptop for a Pre-Alpha prototype, not a production claim.

## What Was Compared

| | Silta | FastAPI, conventional | FastAPI, ORJSON |
| --- | --- | --- | --- |
| Server | axum on tokio, `silta-runtime` at this branch (built with `cargo build --release`) | uvicorn 0.52.4, uvloop, httptools | uvicorn 0.52.4, uvloop, httptools |
| Route body | borrowed slice of a `Vec` built once at startup, `serde_json::to_vec` | slice of a list of dicts built once at import, FastAPI default JSON response path | same slice, `ORJSONResponse` |
| Python | none on the request path | 3.14.7, FastAPI 0.141.1 | 3.14.7, FastAPI 0.141.1, orjson 3.12.0 |
| Response bytes | 26,235 / 263,117 / 791,517 / 2,640,919 for 100 / 1000 / 3000 / 10000 rows | identical (hash-checked before load, `validation.txt`) | identical |

Profile 1, one core: Silta with `TOKIO_WORKER_THREADS=1` against one uvicorn
worker of each FastAPI configuration. Profile 2, multi core: Silta with 10
tokio worker threads against `uvicorn --workers 10` of the ORJSON
configuration. `oha` 1.16 at 50 connections, 30 second points, 3 runs with the
target order rotated on every run, medians reported with the min to max spread.
CPU and RSS are measured over the whole process tree of each server.

## Environment

- macOS Darwin 25.6.0 arm64, Apple M5, 10 logical CPUs, 24 GiB RAM. Servers and
  the load generator share the cores.
- The host was under memory pressure during the run (21 unrelated containers in
  Docker Desktop, swap in use), which shows up as 5 to 19 percent spread in the
  one-core cells and 16 to 27 percent in the multi-core cells. The targets
  alternate within each run, so the pairs stay comparable.
- Silta was started without `--metrics-listen` or an OTLP endpoint; no metrics
  middleware was installed.

## Results

### Mock catalog, one core: Silta with 1 tokio thread vs FastAPI with 1 uvicorn worker

| Route | Target | RPS median | spread | p99 | MB/s | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 rows, 26 KB | FastAPI, Pydantic response | 6,804 (0.81x) | 4.9% | 18.2 ms | 178 | 0.86 | 123 | 65 MB |
| 100 rows, 26 KB | FastAPI, ORJSONResponse | 8,393 | 7.8% | 14.7 ms | 220 | 0.99 | 118 | 59 MB |
| 100 rows, 26 KB | Silta, 1 thread | 17,212 (2.05x, 2.53x vs Pydantic) | 6.4% | 6.2 ms | 452 | 0.97 | 57 | 139 MB |
| 1000 rows, 263 KB | FastAPI, Pydantic response | 1,072 (0.63x) | 6.6% | 129.2 ms | 282 | 0.74 | 695 | 33 MB |
| 1000 rows, 263 KB | FastAPI, ORJSONResponse | 1,694 | 15.9% | 59.8 ms | 446 | 0.76 | 447 | 31 MB |
| 1000 rows, 263 KB | Silta, 1 thread | 2,727 (1.61x, 2.54x vs Pydantic) | 19.1% | 45.9 ms | 718 | 0.88 | 324 | 12 MB |
| 3000 rows, 792 KB | FastAPI, Pydantic response | 400 (0.67x) | 4.6% | 300.4 ms | 316 | 0.81 | 1,984 | 37 MB |
| 3000 rows, 792 KB | FastAPI, ORJSONResponse | 594 | 8.8% | 178.1 ms | 470 | 0.96 | 1,614 | 35 MB |
| 3000 rows, 792 KB | Silta, 1 thread | 941 (1.59x, 2.35x vs Pydantic) | 9.6% | 98.5 ms | 745 | 0.81 | 863 | 50 MB |
| 10000 rows, 2.6 MB | FastAPI, Pydantic response | 116 (0.68x) | 16.6% | 1314.1 ms | 306 | 0.64 | 5,124 | 68 MB |
| 10000 rows, 2.6 MB | FastAPI, ORJSONResponse | 170 | 5.4% | 710.2 ms | 449 | 0.99 | 5,820 | 65 MB |
| 10000 rows, 2.6 MB | Silta, 1 thread | 269 (1.58x, 2.32x vs Pydantic) | 18.1% | 334.5 ms | 710 | 0.8 | 2,989 | 158 MB |

### Mock catalog, multi core: Silta with 10 tokio threads vs FastAPI ORJSON with 10 uvicorn workers

| Route | Target | RPS median | spread | p99 | MB/s | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1000 rows, 263 KB | FastAPI ORJSON, 10 workers | 3,752 | 21.7% | 87.7 ms | 987 | 2.7 | 720 | 634 MB |
| 1000 rows, 263 KB | Silta, 10 threads | 7,001 (1.87x) | 18.4% | 36.0 ms | 1,842 | 2.94 | 394 | 164 MB |
| 3000 rows, 792 KB | FastAPI ORJSON, 10 workers | 1,255 | 27.0% | 177.5 ms | 994 | 3.21 | 2,841 | 661 MB |
| 3000 rows, 792 KB | Silta, 10 threads | 2,069 (1.65x) | 20.7% | 101.5 ms | 1,637 | 3.03 | 1,465 | 68 MB |
| 10000 rows, 2.6 MB | FastAPI ORJSON, 10 workers | 342 | 17.1% | 376.6 ms | 903 | 2.27 | 6,850 | 551 MB |
| 10000 rows, 2.6 MB | Silta, 10 threads | 616 (1.80x) | 15.8% | 268.5 ms | 1,627 | 2.64 | 4,950 | 190 MB |

## Load Generator Saturation Check

After the run, Silta with 10 threads on `/mock/rates/1000` was driven first by one
`oha` process at 50 connections, then by three in parallel (`oha-saturation.txt`):

    one oha, c=50: rps=4504, server cpu cores=2.44
    three oha in parallel, c=50 each: rps=3416 3426 3406 sum=10248, server cpu cores=4.74

One load generator drove the runtime to about 2.4 cores; three drove it to about
4.7 cores and 2.3 times the throughput. On a shared laptop the single `oha` is the
ceiling for the Rust side, so the multi-core ratios above are floors.

## Reading The Numbers

- One core, 100 rows: 2.05x against ORJSON and 2.5x against the conventional
  path, at less than half the CPU per request (57 against 118 and 123 CPU ms
  per thousand requests).
- One core, 1000 to 10000 rows: 1.6x against ORJSON and 2.3 to 2.5x against the
  conventional path, again at about half the CPU per request. Silta's single
  thread was never fully busy (0.8 to 0.9 of a core), the load generator was.
- Multi core: 1.65 to 1.9x against ten ORJSON workers at similar total CPU, with
  68 to 190 MB of resident memory against 550 to 660 MB.
- The Python side of this test is as fast as Python gets: the dictionaries exist
  before the request, so `orjson` only encodes. A real route builds those objects
  from database rows on every request, which is the cost the conventional path
  and the ClickHouse comparison pay for.
- Resident memory of the Rust runtime grows to 140 to 190 MB after the 10000-row
  cell (50 in-flight responses of 2.6 MB each) and stays there; the allocator keeps
  the freed buffers. It is 12 to 50 MB in the cells that run before it.

## Reproduce

```bash
cd experiments/poc-001-pip-native-runtime
docker compose up -d --wait
cargo build --release --manifest-path ../../Cargo.toml -p silta-runtime
SILTA_RUNTIME_BIN=../../target/release/silta-runtime scripts/run_mock_catalog_benchmark.sh
```

Files: `one-core/` and `multi-core/` hold `medians.csv`, `points.csv`, the
`bench_program.py` config and the raw `oha` JSON per point; `validation.txt` is
the byte-identity check; `progress.log` is the timeline.
