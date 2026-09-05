# Experiments

- [`mysql-read-benchmark`](mysql-read-benchmark/) compares native SQLx/MySQL
  reads with an optimized FastAPI baseline for 1, 100, and 1,000 rows.
- [`media-benchmark`](media-benchmark/) compares in-memory binary and image
  responses without JSON serialization or filesystem I/O.

This directory contains focused experiments for validating Silta's architecture.

Experiments are not product features. They are small, measurable prototypes used
to answer technical questions before the framework grows.

Rules:

- Define the question before writing code.
- Measure Rust-only, Python-only, and Rust/Python boundary paths separately.
- Do not make public performance claims from incomplete experiments.
- Keep baselines realistic.
- Record environment details.
- Keep experiments reproducible.

Current experiments:

- [POC-001: pip-installed native runtime](poc-001-pip-native-runtime/README.md).
