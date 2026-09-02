# RFC 0001: Vision

## Status

Accepted for Technical Preview

## Summary

Silta is a runtime-first backend framework: Python is the developer-facing
language, and Rust is the execution runtime.

Silta is not "FastAPI rewritten in Rust". It is a runtime-first system where
Python is a convenient way to express an application, Rust is the way to execute
it efficiently, and Docker/Kubernetes should become a natural final step from
source code to running microservice.

Silta should not become a thin wrapper around Python infrastructure. The project
should expose a Python framework surface over native Rust execution modules.

## Motivation

Python has excellent backend ergonomics, but common infrastructure paths often
pay interpreter, allocation, and framework-layer costs even when the requested
work is structurally predictable. Rust has strong runtime performance and a
mature async ecosystem, but Rust-first backend frameworks do not provide the
same immediate developer experience many Python users expect.

Silta should combine these strengths without pretending that Python and Rust
have the same runtime model.

## Core Idea

Python should describe the application. Rust should execute infrastructure.

```text
Python API / DSL
  -> application representation / IR
  -> Rust runtime
  -> native execution
```

The runtime should avoid Python crossings on the hot path unless user-defined
business logic requires Python.

The conceptual split is:

```text
Python control plane
  -> application definition / IR
  -> Rust execution plane
```

The Rust execution plane should eventually include native modules for HTTP,
routing, middleware, validation, serialization, database access, cache access,
background jobs, observability, and runtime scheduling.

The exact Python/Rust boundary remains an open architectural question. It must
be validated through prototypes and benchmarks before the project commits to one
primary approach.

## Initial Scope

The bootstrap repository includes:

- A Cargo workspace with `silta-core`, `silta-http`, `silta-router`, and
  `silta-runtime`.
- A minimal Python package with `App`.
- Documentation for the runtime and Python boundary.
- Project governance, contribution, security, and CI scaffolding.

## First Technical Question

The first narrow technical question is:

> Can Silta provide a natural Python API while a typical `GET/POST -> DB ->
> JSON` path is served by the Rust runtime without Python on the hot path?

If the answer is yes, the project has a useful foundation for ORM, CRUD,
deployment, and the wider platform. If the answer is no, the project should
learn that through a small proof of concept before large framework investment.

The first proof should focus on Rust-executed endpoints configured from Python,
not on making Python ORM calls look convenient while still executing the hot
path inside Python.

## POC-001: Validate The Python/Rust Execution Boundary

Goal:

Create a minimal prototype:

```text
Python application
  -> Rust runtime
  -> HTTP endpoint
  -> Rust-generated response
```

Measure:

1. Rust-only endpoint.
2. Python endpoint.
3. Rust endpoint configured from Python.
4. Rust -> Python -> Rust endpoint.

Required metrics:

- RPS.
- p50 latency.
- p95 latency.
- p99 latency.
- RSS memory.
- CPU.
- Allocations.
- Startup time.

Do not optimize before measuring.

The success criterion is not only a pleasant Python API. The prototype must
show that representable API endpoints can be configured from Python and executed
through native Rust modules.

## Explicit Non-Goals

- Complete web framework.
- ORM or CRUD layer.
- Production Python bridge.
- Kubernetes or deployment automation.
- GraphQL, gRPC, authentication, or WebSocket support.
- Performance marketing without reproducible benchmarks.
- Replacing mature Rust ecosystem components without a compelling reason.

## Open Questions

- Which Python boundary design should Silta adopt first?
- What should the application IR contain and how should it be versioned?
- Which HTTP stack should back the runtime?
- How should Python async handlers be executed when a route requires Python?
- What benchmark suite is credible enough for early public claims?
