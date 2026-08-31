# Silta Manifesto

## Write Python. Run Rust.

Silta exists because backend developers should not have to choose between
Python's productivity and Rust's performance.

Python is one of the best languages for expressing application logic.

Rust is one of the best languages for building reliable, efficient, and
high-performance infrastructure.

Silta connects them.

## Python Is The Interface

Silta should feel natural to a Python developer.

The developer should be able to describe:

- Models.
- Routes.
- APIs.
- Configuration.
- Permissions.
- Application logic.

using Python.

A developer should not need to understand Rust lifetimes, ownership, Cargo
internals, or async runtime implementation details to use Silta.

## Rust Is The Engine

The runtime should use the Rust ecosystem wherever it provides a better
execution model.

Silta should prefer existing, mature Rust libraries over reinventing
infrastructure.

Potential building blocks include:

- Tokio.
- Hyper.
- Tower.
- Serde.
- SQLx.
- SeaORM.
- Tonic.
- OpenTelemetry.
- tracing.
- Existing Redis clients.
- Existing ecosystem components for WebSockets, OpenAPI, and GraphQL.

Silta is not intended to replace these projects. Silta is intended to connect
them behind a coherent Python developer experience.

## Keep Python Out Of The Hot Path

The central performance principle is:

> Python should only execute when Python is actually needed.

A typical CRUD request should ideally follow:

```text
HTTP
  -> Rust Router
  -> Rust Middleware
  -> Rust Validation
  -> Rust Database Layer
  -> Rust Serialization
  -> HTTP Response
```

without entering the Python interpreter.

Complex application-specific business logic may explicitly enter Python. After
that logic completes, execution can return to Rust.

## Preserve Python Productivity

Performance is not the only goal.

Silta must preserve developer productivity.

The desired experience is:

```python
class User(Model):
    id: int
    name: str
    email: str


app.crud(User)
```

and eventually receive a production-quality REST API.

The framework should hide infrastructure complexity without hiding important
behavior. Silta should provide sensible defaults. A developer should not have to
manually configure common infrastructure for a normal application:

- Routers.
- Serialization.
- Health checks.
- Docker.
- Kubernetes manifests.
- OpenAPI.
- Metrics.
- Tracing.
- Connection pools.

Advanced users must still be able to override defaults.

Silta should optimize the common case, not prohibit the complex case. CRUD
should be extremely simple. Complex applications must remain possible. A user
should be able to drop down from declarative APIs to lower-level control when
necessary.

## From Idea To Service

Silta should reduce the distance between:

```text
idea
  -> Python application
  -> production service
```

The desired workflow is:

```text
silta new
silta dev
silta test
silta build
silta deploy
```

The deployment layer should be generated from application configuration whenever
possible.

Generated Docker, Kubernetes, and OpenAPI artifacts should remain inspectable
and customizable. Users should never become prisoners of the framework.

## Use The Ecosystem

Silta should not build:

- A custom HTTP server.
- A custom async runtime.
- A custom JSON engine.
- A custom tracing system.
- A custom gRPC implementation.
- A custom Kubernetes implementation.

unless there is a compelling technical reason.

Use the ecosystem. Integrate it. Expose it through a simple interface.

## Measure First

Performance should be a property of the architecture, not a collection of
optional optimizations.

Silta should never rely on vague claims such as "blazing fast", "10x faster",
or "enterprise performance" unless they are supported by reproducible
benchmarks.

The project should measure:

- Requests per second.
- p50 latency.
- p95 latency.
- p99 latency.
- CPU consumption.
- RSS memory.
- Allocations.
- Startup time.
- Container image size.
- Concurrency.

Comparisons should be made against realistic alternatives. Do not optimize based
on intuition alone. Measure first.

Silta is designed for efficient high-concurrency backend workloads. The project
aims to reduce memory consumption and runtime overhead for common Python backend
workloads. It does not publish performance claims until benchmarks exist.

## Open Source

Silta is intended to be an open-source project.

Architecture discussions should happen publicly. Important architectural changes
should use RFCs. Performance claims should be reproducible. Benchmarks should be
public. The project should be welcoming to contributors.

The long-term goal is not to make Python look like Rust. The goal is to let
Python developers benefit from Rust without having to become Rust developers.

Python for expression. Rust for execution. Silta is the bridge.
