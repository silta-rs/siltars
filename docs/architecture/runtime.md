# Runtime Architecture

The runtime is responsible for turning an application representation into native
execution state.

In the bootstrap repository, `silta-runtime` only prepares route metadata into a
route table. It does not start an HTTP server, call Python, validate request
bodies, query a database, or serialize responses.

The long-term runtime is the Rust execution plane for Silta. Python configures
and describes it, but the runtime should own high-concurrency request execution
without routing every operation through the Python interpreter.

## Responsibilities

The runtime should eventually own:

- Startup and application loading.
- Conversion from Python-authored declarations into Rust runtime state.
- Native routing, middleware, validation, and serialization where possible.
- Native database/query execution for representable ORM operations.
- Native cache access where configured.
- Native background job orchestration where configured.
- Controlled execution of Python business logic only when needed.
- Observability hooks for traces, metrics, and structured logs.
- Runtime scheduling and concurrency.
- Production-friendly shutdown behavior.

## Runtime Boundary

The core runtime input should be an application representation, not an active
Python object graph. This keeps the hot path from depending on repeated Python
interpreter crossings.

```text
application representation
  -> prepared runtime state
  -> native request execution
```

Representable routes should be prepared into native modules:

```text
prepared route
  -> HTTP module
  -> router module
  -> validation module
  -> database/query module
  -> serialization module
```

Python business logic should be an explicit runtime step, not an implicit
requirement for every request.

## Native Modules

Runtime functionality should be organized around native modules with explicit
interfaces:

- HTTP.
- Router.
- Middleware.
- Validation.
- Serialization.
- Database/query.
- Cache.
- Background jobs.
- Observability.

The Python API can configure these modules, but module internals should be
Rust-owned. This is the difference between Silta and a Python wrapper around
existing Python frameworks.

## Deferred Decisions

- HTTP engine selection and integration model.
- Async runtime ownership and lifecycle.
- Python boundary strategy.
- IR format and schema versioning.
- Native validation and serialization model.
- Database/query abstraction.
- Cache and background job boundaries.
- Observability defaults.

The bootstrap crates should stay small until these decisions are made through
design notes or RFCs.
