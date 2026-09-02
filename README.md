# Silta

> Write Python. Run Rust.

Silta is a runtime-first backend framework for Python developers, powered by a
native Rust execution engine.

`silta` means `bridge` in Finnish. That is the project idea: keep the Python
developer experience on the outside, and move the hot infrastructure path into
Rust.

```text
Python developer experience
        |
      Silta
        |
Rust native runtime
```

[Documentation](docs/README.md) | [Architecture](ARCHITECTURE.md) | [RFCs](rfcs/README.md) | [Experiments](experiments/README.md) | [Funding](FUNDING.md) | [License](LICENSING.md)

## What Silta Is

Silta is not a FastAPI wrapper and not an ASGI server.

The goal is to let Python developers define backends naturally while the runtime
executes common infrastructure work natively:

```text
HTTP request
  -> Rust HTTP server
  -> Rust router
  -> Rust validation
  -> Rust database/query adapter
  -> Rust serialization
  -> JSON response
```

Python remains the control plane. Rust is the execution plane.

## Why It Exists

Python is great for backend development speed.

Rust is great for predictable high-concurrency execution.

Silta bridges them without forcing every Python developer to learn Cargo,
compile Rust, or rewrite their application in Rust.

## Target Install

```bash
pip install siltars
```

> **Not on PyPI yet.** The `siltars` distribution has not been published to
> PyPI, so the command above does not work today. Until the first release,
> install from a local checkout of this repository:
>
> ```bash
> pip install -e .
> ```
>
> The distribution name is `siltars`. The Python import name and the CLI stay
> `silta`.

Silta should not require ordinary Python users to install Rust or run Cargo.
Native Rust runtime artifacts should be distributed through Python wheels.

Current prototype:

```bash
silta inspect examples/hello-world/app.py:app
silta dev examples/hello-world/app.py:app
```

prints the application definition metadata. `silta dev` can start the first
native Rust runtime prototype when the `silta-runtime` binary is available.

## Python Shape

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

## Benchmark Snapshot

POC-001 currently contains a local load-curve snapshot of the Silta native Rust
runtime against a FastAPI baseline on the same local PostgreSQL container after
benchmark tuning. This is useful engineering signal, not a public performance
claim.

![Silta vs FastAPI response time curve](experiments/poc-001-pip-native-runtime/reports/load-curve-postgres-tuned/rates.svg)

Best local points from the current prototype smoke run:

| Endpoint | Silta | FastAPI | Signal |
| --- | ---: | ---: | --- |
| `/ping` | 133,413 RPS | 48,662 RPS | Lower HTTP/runtime overhead |
| `/rates/EUR/USD` | 15,753 RPS | 11,958 RPS | Native DB path leads after tuning |
| `/rates` | 9,652 RPS | 3,873 RPS | Larger JSON response favors Rust serialization |

Important limitations: each point used 5,000 requests, the run was executed
once, the environment record is incomplete, response bodies are not yet byte-for
byte identical, and the Python bridge path is not measured yet. The official
benchmark bar is 30-second runs, repeated three times, with CPU/RSS/startup and
full dependency versions recorded.

See the full report and caveats in
[experiments/poc-001-pip-native-runtime/reports/load-curve-postgres-tuned](experiments/poc-001-pip-native-runtime/reports/load-curve-postgres-tuned/README.md).

## Current Status

Silta is Pre-Alpha.

The API is not stable yet.

The architecture is being validated through prototypes and benchmarks. The
first native runtime prototype can start an HTTP server, read a Python-produced
JSON application definition, serve simple native JSON routes, and run
PostgreSQL-backed benchmark routes in Rust.

Silta does not yet provide a production server, Python execution bridge, ORM,
stable error contract, deployment system, authentication, GraphQL, or gRPC
support.

## Alpha Milestone

Silta should move from Pre-Alpha to Alpha when these criteria are met:

- `pip install siltars` installs a wheel with the native runtime artifact.
- The Python route API is stable enough for early users.
- Native PostgreSQL CRUD works from Python model definitions.
- Runtime configuration is documented for local and container deployments.
- Benchmark runs are reproducible in CI and locally.
- A Rust -> Python -> Rust path is measured and documented.
- The project has a small example application that can be cloned, run, and
  modified without Rust knowledge.

## Positioning

Silta is closest to an application-definition and native-runtime bridge. Robyn
and Granian are important Python/Rust server references, while PostgREST and
Hasura prove the value of schema-driven APIs. Silta's intended difference is the
IR boundary: Python describes routes, models, and policies; Rust executes
representable HTTP, validation, database, and serialization paths natively; and
Python remains available as an explicit escape hatch for business logic.

## Architecture Documents

- [ARCHITECTURE.md](ARCHITECTURE.md): system boundaries.
- [docs/architecture/overview.md](docs/architecture/overview.md): Python
  control plane and Rust execution plane.
- [docs/architecture/runtime.md](docs/architecture/runtime.md): runtime
  ownership.
- [docs/architecture/database-adapters.md](docs/architecture/database-adapters.md):
  SQLx, tokio-postgres, Diesel, and Kafka adapter direction.

## Project Origin

Silta was originally conceived and initiated by Сергей Гнездилов
(Serge Gnezdilov).

See [AUTHORS.md](AUTHORS.md), [NOTICE](NOTICE), and
[LICENSING.md](LICENSING.md).

## License

Licensed under:

- Apache License 2.0
