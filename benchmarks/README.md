# Benchmarks

This directory will contain reproducible Silta benchmarks.

The project does not publish performance claims yet. Benchmarks should be added
only when they measure a real architectural path and include enough environment
detail for others to reproduce the result.

Silta benchmarks must be:

- Reproducible.
- Versioned.
- Published.
- Workload-specific.
- Memory-aware.

## Initial Matrix

Potential comparison targets:

- Silta.
- FastAPI.
- Litestar.
- Django.
- Go.
- Rust/Axum.

Benchmarks should compare against realistic alternatives, not synthetic
microbenchmarks alone.

## Scenarios

Initial scenarios should include:

- `GET /ping`.
- `GET /users`.
- `POST /users`.
- `GET /users/{id}`.
- `POST` plus validation.
- CRUD plus PostgreSQL.
- Concurrent requests.
- Memory under load.
- Container startup.

## Metrics

Benchmarks should report:

- Requests per second.
- p50 latency.
- p95 latency.
- p99 latency.
- CPU consumption.
- RSS memory.
- Allocations.
- Startup time.
- Container image size where relevant.
