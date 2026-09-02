# Experiments

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
