# Architecture Overview

Silta is a Rust runtime with a Python application interface.

The project is not a FastAPI clone and not an ASGI server. Python should provide
the developer-facing DSL. Rust should execute infrastructure work such as
routing, middleware, validation, query execution, serialization, observability,
and response handling wherever the application representation makes that
possible.

Silta should not be a thin wrapper around Python HTTP, ORM, or serialization
libraries. It should expose a Python framework surface over native Rust runtime
modules.

## Target Shape

```text
Python application
  -> Python API / DSL
  -> application representation / IR
  -> Rust runtime
  -> native execution
```

Another way to state the boundary:

```text
Python control plane
  -> application definition / IR
  -> Rust execution plane
```

The control plane describes services, routes, models, configuration, policies,
and business logic entry points. The execution plane owns native runtime modules
for request handling, routing, validation, database/query work, serialization,
observability, and concurrency.

The long-term request path is:

```text
HTTP
  -> Rust HTTP server
  -> Rust router
  -> Rust middleware
  -> Rust validation
  -> Rust query layer
  -> database
  -> Rust serialization
  -> HTTP response
```

Python should be entered only when the request requires user-defined business
logic that cannot be represented and executed natively.

For CRUD-style endpoints, the intended path should remain native:

```text
HTTP
  -> Rust HTTP module
  -> Rust router module
  -> Rust validation module
  -> Rust database/query module
  -> Rust serialization module
  -> JSON response
```

For custom application logic, Python may be invoked deliberately:

```text
HTTP
  -> Rust HTTP/router/validation modules
  -> Python business logic
  -> Rust serialization/observability modules
  -> JSON response
```

The second mode preserves expressiveness. The first mode is the core
architectural claim that must be validated through prototypes and benchmarks.

## Workspace Boundaries

- `silta-core` owns shared application representation types.
- `silta-http` owns HTTP boundary vocabulary while the server choice remains
  open.
- `silta-router` owns route table abstractions.
- `silta-runtime` owns runtime preparation and orchestration boundaries.

These crates are intentionally small. They exist to keep ownership boundaries
clear without pretending that the complete framework is implemented.

Future runtime crates should map to real native module boundaries, not to
marketing categories. A new crate should exist only when ownership, dependency
surface, and implementation responsibility justify it.

## Near-Term Non-Goals

- No production Python execution bridge.
- No ORM or CRUD framework.
- No Kubernetes, Helm, or container deployment layer.
- No GraphQL, gRPC, authentication, or WebSocket subsystem.
- No performance claims without reproducible benchmarks.

## Ecosystem Direction

Silta should prefer proven Rust crates where appropriate:

- HTTP: Hyper or Axum where the abstraction fits.
- Async runtime: Tokio.
- Middleware: Tower and Tower HTTP.
- Serialization: Serde and serde_json.
- Database access: SQLx, with SeaORM considered only if the model fits.
- Observability: tracing and the OpenTelemetry ecosystem.

Each dependency should be chosen deliberately and documented when it becomes
part of the architecture.
