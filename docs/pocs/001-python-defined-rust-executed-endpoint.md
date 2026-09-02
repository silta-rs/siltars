# POC-001: Python-Defined, Rust-Executed Endpoint

## Status

Implemented prototype.

## Goal

Validate the core Silta thesis:

> A Python developer can define useful API endpoints while the common request
> path executes inside native Rust runtime modules.

This proof of concept must demonstrate that Silta is not a wrapper around
Python HTTP, ORM, or serialization code.

## Target Shape

```text
Python App definition
  -> Application Definition / IR
  -> Silta Bridge
  -> Rust Runtime
  -> Rust HTTP module
  -> Rust router module
  -> Rust response serialization
  -> HTTP JSON response
```

Python should configure the endpoint. Python should not execute on the native
hot path.

## Proposed Python Surface

Subject to RFC.

```python
from silta import App

app = App()


@app.get("/ping", native=True)
def ping():
    return {"ok": True}
```

The exact API is not important for this POC. The important requirement is that
Python produces application metadata and Rust serves the endpoint.

## Required Paths

Measure four paths separately:

1. Rust-only endpoint defined entirely in Rust.
2. Python handler endpoint that enters Python business logic.
3. Rust endpoint configured from Python metadata.
4. Rust -> Python -> Rust endpoint.

These paths make the Python/Rust boundary cost visible.

## Success Criteria

The POC is successful if it shows:

- Python can define an endpoint naturally.
- Rust can prepare runtime state from the Python-authored definition.
- Rust can serve the configured endpoint without entering Python on each
  request.
- JSON response serialization happens in Rust for the native path.
- The benchmark harness can compare native and Python-invoking paths.
- Measurements include latency, throughput, memory, CPU, allocations where
  practical, and startup time.

The POC is not successful merely because the Python API looks pleasant.

## Metrics

Measure:

- Requests per second.
- p50 latency.
- p95 latency.
- p99 latency.
- RSS memory.
- CPU usage.
- Allocations where practical.
- Startup time.

## Non-Goals

- Full ORM.
- CRUD generation.
- PostgreSQL integration.
- Migrations.
- Authentication.
- OpenAPI.
- Kubernetes or Docker generation.
- Production Python bridge.
- Final public API design.

## Follow-Up POC

If POC-001 succeeds, the next proof should add the database path:

```text
Python Model definition
  -> query/application representation
  -> Rust database/query module
  -> PostgreSQL
  -> Rust serialization
  -> JSON
```

That follow-up should prove the first MVP path:

```text
PostgreSQL
  -> Model
  -> CRUD
  -> REST
  -> JSON
```
