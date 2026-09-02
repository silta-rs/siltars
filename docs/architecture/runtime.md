# Runtime Architecture

The runtime is responsible for turning an application representation into native
execution state.

In the current Pre-Alpha repository, `silta-runtime` can read a JSON application
definition, prepare route metadata into a route table, and start a native Axum
HTTP server for supported prototype routes. It does not yet provide a production
Python execution bridge, stable validation layer, stable error contract, or ORM.

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

## Data And Stream Adapter Boundary

Silta should not hard-code one ORM as the whole database story. Real projects
use different SQL databases, different query styles, and different operational
constraints. The runtime should keep a database adapter boundary with a common
native execution contract.

For the framework core, the first priority is a fast async driver/query path
that can be produced from Python metadata and executed natively. `sqlx` is a
reasonable first PostgreSQL path because it is async, works naturally with
Tokio, and supports explicit SQL. `tokio-postgres` should remain a candidate for
lower-level hot paths where less abstraction is useful.

Diesel should be treated as an optional typed ORM integration, not the only
runtime foundation. It can be valuable for Rust-authored models and strongly
typed schemas, but the Silta core must still support generated and
metadata-driven query plans coming from Python definitions.

The same rule applies to stream systems. Kafka should sit behind a native
runtime adapter boundary. For Confluent-compatible Kafka, the likely Rust path
is a native client built on `librdkafka` rather than putting a Java client on the
request hot path. Java-based integrations can exist at the edges, but the Silta
runtime should keep HTTP, routing, validation, database access, serialization,
and stream publishing/consuming in native runtime modules whenever practical.

## Deferred Decisions

- HTTP engine selection and integration model.
- Async runtime ownership and lifecycle.
- Python boundary strategy.
- IR format and schema versioning.
- Native validation and serialization model.
- Database/query adapter abstraction.
- Kafka and stream adapter abstraction.
- Cache and background job boundaries.
- Observability defaults.

The bootstrap crates should stay small until these decisions are made through
design notes or RFCs.
