# Changelog

All notable changes to Silta will be documented in this file.

The format is intentionally simple while the project is in bootstrap.

## Unreleased

- Added `GET /mock/rates/{count}`, a serialization-only route over a deterministic
  in-memory catalog, plus an `ORJSONResponse` FastAPI baseline, so large JSON
  responses can be compared without a database in the loop. The runner
  (`benchmarks/native-runtime/scripts/run_mock_catalog_benchmark.sh`), the
  alternating-run orchestrator behind it (`scripts/bench_program.py`) and the
  result summary in `benchmarks/RESULTS.md` ship with it.
- Raised the minimum supported Rust version (MSRV) from 1.88 to 1.89 to match
  the requirements of the ClickHouse 0.15 dependency family.
- Added an experimental ClickHouse path (`--clickhouse-url`, `/ch/*` routes) with
  a local seed script and a FastAPI `clickhouse-connect` baseline for 1, 100 and
  1000-row reads.
- Disabled the SQLx acquire ping on the native PostgreSQL pool: one round trip
  per database request instead of two. Benchmark scripts start with a warm pool.
- Initialized repository structure.
- Added minimal Rust workspace skeleton.
- Added minimal Python package skeleton.
- Added architecture, governance, contribution, and security documents.
