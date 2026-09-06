# Changelog

All notable changes to Silta will be documented in this file.

The format is intentionally simple while the project is in bootstrap.

## Unreleased

- Raised the minimum supported Rust version (MSRV) from 1.88 to 1.89 to match
  the requirements of the ClickHouse 0.15 dependency family.
- Added an experimental ClickHouse path (`--clickhouse-url`, `/ch/*` routes) with
  a local seed script and a FastAPI `clickhouse-connect` baseline for 1, 100 and
  1000-row reads.
- Initialized repository structure.
- Added minimal Rust workspace skeleton.
- Added minimal Python package skeleton.
- Added architecture, governance, contribution, and security documents.
