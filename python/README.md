# Python Package

This directory contains the Python-facing Silta API.

Current state:

- Minimal `App` object.
- Route metadata recording.
- No production Python/Rust bridge.
- No `Model` implementation.
- No ORM or CRUD execution.

The Python package should evolve as a developer-facing DSL. It should collect
application intent in a form that the Silta bridge can convert into runtime
representation.

Proposed APIs must be labeled as proposed and subject to RFC until accepted.
