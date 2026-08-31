# Runtime Architecture

The runtime is responsible for turning an application representation into native
execution state.

In the bootstrap repository, `silta-runtime` only prepares route metadata into a
route table. It does not start an HTTP server, call Python, validate request
bodies, query a database, or serialize responses.

## Responsibilities

The runtime should eventually own:

- Startup and application loading.
- Conversion from Python-authored declarations into Rust runtime state.
- Native routing, middleware, validation, and serialization where possible.
- Controlled execution of Python business logic only when needed.
- Observability hooks for traces, metrics, and structured logs.
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

## Deferred Decisions

- HTTP engine selection and integration model.
- Async runtime ownership and lifecycle.
- Python boundary strategy.
- IR format and schema versioning.
- Native validation and serialization model.
- Database/query abstraction.
- Observability defaults.

The bootstrap crates should stay small until these decisions are made through
design notes or RFCs.
