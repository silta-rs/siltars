# Architecture Overview

Silta is a Rust runtime with a Python application interface.

The project is not a FastAPI clone and not an ASGI server. Python should provide
the developer-facing DSL. Rust should execute infrastructure work such as
routing, middleware, validation, query execution, serialization, observability,
and response handling wherever the application representation makes that
possible.

## Target Shape

```text
Python application
  -> Python API / DSL
  -> application representation / IR
  -> Rust runtime
  -> native execution
```

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

## Workspace Boundaries

- `silta-core` owns shared application representation types.
- `silta-http` owns HTTP boundary vocabulary while the server choice remains
  open.
- `silta-router` owns route table abstractions.
- `silta-runtime` owns runtime preparation and orchestration boundaries.

These crates are intentionally small. They exist to keep ownership boundaries
clear without pretending that the complete framework is implemented.

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
