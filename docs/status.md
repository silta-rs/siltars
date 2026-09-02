# Project Status

Silta is Pre-Alpha.

This document states what the current repository proves, what it does not prove
yet, and what should be built next. It is intentionally conservative: benchmark
numbers are engineering evidence, not production claims.

## What Is Proven

- A Python application definition can configure a Rust native runtime.
- The Rust runtime can start an HTTP server from that definition.
- Supported prototype routes execute without routing each request through a
  Python HTTP stack.
- Native PostgreSQL read and write routes work through `sqlx`.
- Large JSON read responses can be shaped with Rust structs and serialized
  through Serde.
- Local load-curve smoke tests run without request errors in the measured
  scenarios.
- `silta dev` forwards `SIGINT`, `SIGTERM`, and `SIGHUP` to the child runtime,
  so normal process managers do not leave the runtime listening as an orphan.

## What Is Not Proven

- The Rust -> Python -> Rust business-logic escape hatch is not implemented or
  measured yet.
- The current route-to-native-handler mapping still uses symbolic function
  names as a temporary Pre-Alpha contract.
- Native wheels do not yet bundle the Rust runtime artifact, so `pip install
  siltars` is not yet the complete no-Rust-user workflow.
- Benchmarks currently compare a native Rust prototype path with a typical
  FastAPI baseline; they are not final public performance claims.
- CPU, RSS, startup time, and allocation benchmarks are not part of the current
  published smoke reports.

## Public Positioning

The honest current statement is:

> Silta is a Pre-Alpha experiment for Python-defined, Rust-executed backend
> services. The current prototype shows the native Rust runtime path and early
> PostgreSQL/JSON benchmark signal. The Python escape-hatch path and bundled
> runtime wheels are the next critical milestones.

Avoid claims such as "Silta is 2.7x faster than FastAPI" until reproducible
benchmark gates include the Python bridge path, dependency locks, memory,
startup, CPU, and allocation data.

## Immediate Engineering Focus

1. Build the smallest Rust -> Python -> Rust route and measure its cost.
2. Bundle the native `silta-runtime` binary into platform wheels.
3. Replace symbolic handler-name mapping with explicit route operation
   declarations.
4. Add benchmark gates for RSS, CPU, startup, and allocations.
5. Reduce nonessential governance text until the implementation surface is
   larger.
