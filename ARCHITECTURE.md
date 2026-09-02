# Silta Architecture

This document defines Silta's system boundaries. It does not choose concrete
implementations, crates, protocols, storage engines, or deployment targets.

Silta's architecture is based on a simple separation:

- Python describes the application.
- Rust executes the runtime.
- The bridge turns application definitions into runtime-ready representation.

Silta must not become a thin wrapper around Python infrastructure. The intended
model is a Python control plane around native Rust execution modules.

## System Boundary

```text
Python API
     |
     v
Application Definition
     |
     v
Silta Bridge
     |
     v
Rust Runtime
 +-----------------------------+
 | HTTP                        |
 | Router                      |
 | Middleware                  |
 | Validation                  |
 | Serialization               |
 | Database                    |
 | Cache                       |
 | Background Jobs             |
 | Observability               |
 +-----------------------------+
```

The exact Python/Rust boundary is an open architectural question and must be
validated through benchmarks and prototypes.

## Control Plane And Execution Plane

Silta has two distinct planes:

- Python control plane.
- Rust execution plane.

The Python control plane owns the developer-facing interface. It describes
services, routes, models, configuration, policies, and custom business logic.
It should feel like ordinary async Python code.

The Rust execution plane owns the operational work. HTTP handling, routing,
validation, serialization, database access, cache access, background execution,
and observability should run in native Rust modules whenever they can be
represented from the application definition.

Python should configure and describe many Rust execution modules. It should not
coordinate every request, schedule every task, generate SQL per request, or
serialize every JSON response on the hot path.

```text
Python framework surface
 +-----------------------------------------------------------+
 | App, Model, routes, configuration, policies, user logic    |
 +-----------------------------------------------------------+
                              |
                              v
                       Silta Bridge / IR
                              |
                              v
Rust runtime modules
 +-----------------------------------------------------------+
 | HTTP | Router | Validation | ORM/Query | Serde | Jobs     |
 | Cache | Middleware | Observability | Runtime Scheduling   |
 +-----------------------------------------------------------+
```

This is the source of the performance opportunity: Python remains the language
of expression, while Rust modules perform the high-concurrency execution work.
The design should allow many native runtime paths to run concurrently without
being serialized through the Python interpreter or GIL.

## Installation Boundary

Silta must be usable by Python developers through Python packaging.

The intended installation experience is:

```bash
pip install siltars
```

The `siltars` distribution is not published on PyPI yet; see
`docs/architecture/distribution.md` for the current local install path.

A normal user should not need to install Rust, run Cargo, compile native
extensions manually, or understand Rust build tooling. Rust should be delivered
as prebuilt native artifacts inside platform-specific Python wheels.

The package should expose a Python API and, eventually, a `silta` CLI. That CLI
may start or configure the Rust runtime, but it should not turn Python into the
hot-path request scheduler.

See `docs/architecture/distribution.md`.

## Layer Responsibilities

### Python API

The Python API is the developer-facing interface.

It should let developers describe an application using familiar Python syntax:

- Routes.
- Models.
- Configuration.
- Service metadata.
- Business logic entry points.

The Python API should not own infrastructure execution on the hot path. Its
primary role is to collect intent and expose a clear developer experience.

### Application Definition

The application definition is the structured representation of what the Python
API describes.

It should be explicit enough for the Rust runtime to prepare native execution
state without depending on active Python objects for every request.

This boundary may eventually include:

- Route definitions.
- Handler references.
- Model metadata.
- Validation rules.
- Serialization schema.
- Database/query metadata.
- Middleware configuration.
- Deployment and service metadata.

The exact format is intentionally undecided.

### Silta Bridge

The Silta Bridge converts the Python-authored application definition into the
form consumed by the Rust runtime.

The bridge is a boundary, not a commitment to a specific mechanism. Possible
future mechanisms include:

- A native Python extension.
- Embedded CPython.
- A Python process communicating with a Rust runtime.
- A generated intermediate representation.
- A hybrid of these approaches.

The bridge should minimize Python-to-Rust crossings on the request hot path.
Python should be entered during request handling only when business logic
requires it.

### Rust Runtime

The Rust runtime owns infrastructure execution.

Runtime responsibilities include:

- HTTP request handling.
- Routing.
- Middleware execution.
- Request validation.
- Response serialization.
- Database/query execution.
- Cache access.
- Background job orchestration.
- Observability.
- Native runtime scheduling and concurrency.

The runtime should integrate proven Rust ecosystem components where appropriate.
This document deliberately does not select those components.

### Native Module Boundary

Runtime capabilities should be modeled as native modules with explicit
interfaces. Examples include:

- HTTP module.
- Router module.
- Validation module.
- Serialization module.
- Database/query module.
- Cache module.
- Background jobs module.
- Observability module.

The Python API may expose simple methods for configuring these modules, but the
module internals should remain Rust-owned. This keeps the framework from
becoming a Python facade over Python implementations.

## Hot Path Principle

The target hot path is native-first.

Native mode:

```text
HTTP
  -> Rust
  -> Rust
  -> Rust
  -> Response
```

Python business logic mode:

```text
HTTP
  -> Rust
  -> optional Python business logic
  -> Rust
  -> Response
```

The architecture should avoid designs where every request repeatedly crosses the
Python/Rust boundary for routing, validation, serialization, or database access.

For CRUD-style requests, the target path is:

```text
HTTP
  -> Rust HTTP module
  -> Rust router module
  -> Rust validation module
  -> Rust database/query module
  -> Rust serialization module
  -> JSON response
```

For custom business logic, the target path is:

```text
HTTP
  -> Rust HTTP/router/validation modules
  -> Python business logic
  -> Rust serialization/observability modules
  -> JSON response
```

The second mode exists for expressiveness. The first mode is the core
architectural advantage Silta must prove.

Performance should be a property of the architecture, not a collection of
optional optimizations. The common case should require very little
configuration. Advanced behavior should remain accessible.

Silta should optimize the common case, not prohibit the complex case. CRUD
should be extremely simple. Complex applications must remain possible. A user
should be able to drop down from declarative APIs to lower-level control when
necessary.

Prefer established Rust crates. Every important performance claim should be
measurable.

Users should never become prisoners of the framework. Generated Docker,
Kubernetes, and OpenAPI artifacts should remain inspectable and customizable.

## Ownership Boundaries

### Python Owns

- Developer-facing API shape.
- Application declaration ergonomics.
- Business logic authored by users.
- Error messages that point back to Python source.
- Control-plane configuration of native Rust runtime modules.

### Bridge Owns

- Conversion from Python declarations to runtime representation.
- Compatibility between Python package versions and runtime versions.
- Boundary diagnostics.
- Any unavoidable Python/Rust interop.

### Rust Owns

- Runtime lifecycle.
- Native request pipeline.
- Prepared route state.
- Native validation and serialization paths.
- Runtime observability.
- Production execution behavior.
- Database/query execution for representable ORM operations.
- Native concurrency and scheduling.

## Current Bootstrap Mapping

The current repository maps these boundaries as follows:

- `python/silta`: minimal Python API skeleton.
- `crates/silta-core`: shared application representation types.
- `crates/silta-http`: HTTP boundary vocabulary.
- `crates/silta-router`: router abstraction.
- `crates/silta-runtime`: runtime preparation skeleton.
- `docs/architecture/python-boundary.md`: detailed bridge tradeoff analysis.

This mapping is intentionally minimal. It establishes ownership boundaries
without pretending the full platform already exists.

## Non-Goals For This Document

This document does not define:

- Which HTTP server crate Silta will use.
- How Python will call into Rust.
- How Rust will call Python business logic.
- ORM implementation details.
- Cache backend selection.
- Background job implementation.
- Kubernetes, Docker, or cloud deployment logic.
- Authentication, GraphQL, or gRPC architecture.

Those decisions should be made through focused design documents or RFCs.
