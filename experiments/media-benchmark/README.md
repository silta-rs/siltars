# Binary and image response benchmark

This Alpha experiment measures in-memory non-JSON responses through Silta and
an optimized single-worker FastAPI/Uvicorn baseline.

The cases are:

- a deterministic 64 KiB `application/octet-stream` body;
- a deterministic 1 MiB `application/octet-stream` body;
- a valid 512x512 24-bit BMP image of 786,486 bytes.

Both applications build each payload once at startup. The runner compares the
response bodies byte-for-byte and validates MIME types, exact sizes, and the BMP
file structure before starting `oha`, so the benchmark does not reward missing
or truncated responses. It intentionally excludes filesystem and image-encoding
costs.

The report includes requests per second, tail latency, and GiB/s. For the 1 MiB
and BMP cases, GiB/s is the primary throughput signal.

The current Python 3.14 Alpha report, chart, CSV, and raw `oha` output are in
[`reports/python-3.14-alpha`](reports/python-3.14-alpha/README.md).

```bash
cd experiments/media-benchmark
./scripts/run_benchmark.sh
```

For a smoke test:

```bash
BENCH_DURATION=2s BENCH_RUNS=1 BENCH_CONCURRENCY=1,25,100 ./scripts/run_benchmark.sh
```

This is a local Alpha engineering experiment, not a general performance claim.
The routes are currently benchmark handlers in the pre-Alpha runtime; generic
binary response declarations in the Python API are not implemented yet.
