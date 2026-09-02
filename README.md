# Silta

> Write Python. Run Rust.

A runtime-first backend framework for Python, powered by a native Rust runtime.

[Website](https://silta.dev) | [Documentation](docs/README.md) | [RFCs](rfcs/README.md) | [Benchmarks](benchmarks/README.md) | [Experiments](experiments/README.md) | [Funding](FUNDING.md) | [License](LICENSING.md)

## Why?

Python is great for building backends.

Rust is great for running them.

Silta connects the two.

## Install

Target experience:

```bash
pip install silta
```

Silta should not require ordinary Python users to install Rust or run Cargo.
Native Rust runtime artifacts should be distributed through Python wheels.

Current bootstrap CLI:

```bash
silta inspect examples/hello-world/app.py:app
```

prints the application definition metadata. `silta dev` can start the first
native Rust runtime prototype when the `silta-runtime` binary is available.

## Proposed API

Subject to RFC.

```python
from silta import App, Model

app = App()


class User(Model):
    id: int
    name: str
    email: str


app.crud(User)
```

Potential generated endpoints:

```text
GET     /users
GET     /users/{id}
POST    /users
PATCH   /users/{id}
DELETE  /users/{id}
```

## Status

Silta is experimental and under active development.

The API is not stable.

The architecture is being validated through prototypes and benchmarks. The
first native runtime prototype serves HTTP, JSON, and PostgreSQL-backed routes
from Rust modules configured through the Python CLI.

Silta does not yet provide a production server, Python execution bridge, ORM,
deployment system, authentication, GraphQL, or gRPC support.

## Benchmark Snapshot

POC-001 compares the Silta native Rust runtime against FastAPI on the same local
PostgreSQL container after benchmark tuning.

![Silta vs FastAPI response time curve](experiments/poc-001-pip-native-runtime/reports/load-curve-postgres-tuned/rates.svg)

See the full report in
[experiments/poc-001-pip-native-runtime/reports/load-curve-postgres-tuned](experiments/poc-001-pip-native-runtime/reports/load-curve-postgres-tuned/README.md).

## Project Origin

Silta was originally conceived and initiated by Serge Gnezdilov.

See [AUTHORS.md](AUTHORS.md), [NOTICE](NOTICE), and
[LICENSING.md](LICENSING.md).

## License

Licensed under:

- Apache License 2.0
