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

[Documentation](docs/README.md) | [Cookbook](docs/cookbook.md) | [Status](docs/status.md) | [Architecture](docs/architecture/README.md) | [RFCs](rfcs/README.md) | [Benchmarks](benchmarks/README.md) | [Funding](docs/project/funding.md) | [License](docs/project/licensing.md)

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

The first example route is represented explicitly:

```python
@app.get("/hello", response={"hello": "world"})
async def hello():
    return {"hello": "world"}
```

`response=...` is serialized into the application definition. Silta does not
execute the Python handler body during `inspect` or `dev`.

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

## Performance

Measured, not claimed: every number comes from a reproducible runner under
[`benchmarks/`](benchmarks/README.md), follows the written
[methodology](docs/architecture/performance.md), and is engineering evidence
from one laptop. Summary tables live in [`benchmarks/RESULTS.md`](benchmarks/RESULTS.md).

| Route, one core, c=50 | Silta vs FastAPI (ORJSONResponse) | Why |
| --- | ---: | --- |
| One PostgreSQL row | 1.2x | Both stacks wait on the same database round trip |
| 100 PostgreSQL rows, 16 KB | 1.3x | Serialization starts to matter |
| 3000 nested PostgreSQL rows, 800 KB | 1.4x | Docker network proxy caps both |
| 1000 ClickHouse rows | 2.6x | RowBinary into structs, Serde out |
| 100 in-memory rows, serialization only | 2.1x (2.5x vs Pydantic) | No database in the path |
| `GET /ping` | about 4x | HTTP stack overhead only |

Across those routes the runtime spent about half the CPU per request of the
FastAPI baseline and held a tenth of the memory of a ten-worker uvicorn
deployment. Where the database is the ceiling the gain is modest; where JSON
is the work it grows. Python `orjson` with prebuilt objects is the toughest
baseline (1.6x on large bodies); routes that build objects per request pay
what the conventional FastAPI path pays.

## Current Status

Silta is Pre-Alpha.

The API is not stable yet.

The architecture is being validated through prototypes and benchmarks. The
first native runtime prototype can start an HTTP server, read a Python-produced
JSON application definition, serve simple native JSON routes, and run
PostgreSQL-backed benchmark routes in Rust.

Silta does not yet provide a production server, production Python execution
bridge, ORM, stable error contract, deployment system, authentication, GraphQL,
or gRPC support.

See [docs/status.md](docs/status.md) for the current proven/not-proven state
and immediate engineering focus.

## Alpha Milestone

See the canonical Alpha checklist in [ROADMAP.md](ROADMAP.md#alpha-milestone).

## Positioning

Silta is closest to an application-definition and native-runtime bridge. Robyn
and Granian are important Python/Rust server references, while PostgREST and
Hasura prove the value of schema-driven APIs. Silta's intended difference is the
IR boundary: Python describes routes, models, and policies; Rust executes
representable HTTP, validation, database, and serialization paths natively; and
Python remains available as an explicit escape hatch for business logic.

## Architecture Documents

- [docs/architecture/README.md](docs/architecture/README.md): system boundaries.
- [docs/architecture/overview.md](docs/architecture/overview.md): Python
  control plane and Rust execution plane.
- [docs/architecture/runtime.md](docs/architecture/runtime.md): runtime
  ownership.
- [docs/architecture/database-adapters.md](docs/architecture/database-adapters.md):
  SQLx, tokio-postgres, Diesel, and Kafka adapter direction.

## Project Origin

Silta was originally conceived and initiated by
[Serrka](https://github.com/Sergey2Gnezdilov/).

See [AUTHORS.md](docs/project/authors.md), [NOTICE](NOTICE), and
[LICENSING.md](docs/project/licensing.md).

## License

Licensed under:

- Apache License 2.0
