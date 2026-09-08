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

### Multi core: Silta default threads vs FastAPI ORJSON with 10 workers, equal total database connections

| Route | Target | RPS median | spread | p99 | CPU cores | CPU ms per 1k req | RSS |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| one row, random key | FastAPI ORJSON, 10 workers, 10 x 3 connections | 8,173 | 4.8% | 19.6 ms | 2.93 | 358 | 351 MB |
| one row, random key | Silta, 10 threads, 32 connections | 9,422 (1.15x) | 4.3% | 11.6 ms | 1.04 | 111 | 23 MB |
| 100 rows | FastAPI ORJSON, 10 workers, 10 x 3 connections | 5,200 | 8.9% | 33.4 ms | 3.08 | 596 | 328 MB |
| 100 rows | Silta, 10 threads, 32 connections | 5,902 (1.14x) | 7.4% | 18.2 ms | 1.52 | 274 | 24 MB |
| 3000 nested rows | FastAPI ORJSON, 10 workers, 10 x 3 connections | 245 | 2.9% | 442.0 ms | 3.22 | 12,849 | 679 MB |
| 3000 nested rows | Silta, 10 threads, 32 connections | 242 (0.99x) | 2.8% | 319.3 ms | 1.77 | 7,300 | 61 MB |

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

### Runtime binaries A/B: three builds under identical conditions, no Python parent, 10 threads, pool 50, c=50, 20 s points

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
