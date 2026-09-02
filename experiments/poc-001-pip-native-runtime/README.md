# POC-001: pip-installed Native Runtime

## Question

Can a normal Python developer install Silta with `pip`, define an API in Python,
and run an endpoint where the hot path executes in native Rust modules?

This experiment validates the product shape:

```text
pip install silta
  -> Python API / DSL
  -> prebuilt Rust runtime artifact
  -> Rust HTTP/router/serialization path
  -> JSON response
```

## What This Must Prove

- The user does not need Rust, Cargo, or a native compiler.
- Python defines the application.
- Rust serves the representable endpoint.
- JSON serialization for the native endpoint happens in Rust.
- Benchmarking can compare Silta against realistic Python async baselines.
- The Python/Rust boundary cost is measured, not guessed.

## What This Must Not Become

- A benchmark marketing page.
- A fake API example without runtime behavior.
- A Python web framework wrapper.
- A full ORM implementation.
- A production server.

## Experiment Files

- [quickstart.md](quickstart.md): developer-facing experiment flow.
- [silta_app.py](silta_app.py): proposed Silta application shape.
- [benchmark.md](benchmark.md): measurement plan and commands.
- [requirements-baseline.txt](requirements-baseline.txt): Python baseline dependencies.
- [baselines/fastapi_app.py](baselines/fastapi_app.py): FastAPI reference endpoint.
- [baselines/fastapi_db_app.py](baselines/fastapi_db_app.py): FastAPI PostgreSQL reference endpoint.
- [baselines/litestar_app.py](baselines/litestar_app.py): Litestar reference endpoint.
- [db/init.sql](db/init.sql): schema for the existing local Postgres container.

## Success Criteria

The experiment succeeds only if a user can:

1. Install Silta through Python packaging.
2. Run the proposed Silta app without manually compiling Rust.
3. Hit a JSON endpoint served by Rust runtime modules.
4. Compare results against Python async baselines using the same benchmark tool.
5. Record RPS, p50, p95, p99, RSS memory, CPU, and startup time.

No speedup claim should be published until the measurements are reproducible.
