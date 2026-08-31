# Silta

> Write Python. Run Rust.

A runtime-first backend framework for Python, powered by a native Rust runtime.

[Website](https://silta.dev) | [Documentation](docs/README.md) | [RFCs](rfcs/README.md) | [Benchmarks](benchmarks/README.md)

## Why?

Python is great for building backends.

Rust is great for running them.

Silta connects the two.

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

The architecture is being validated through prototypes and benchmarks.

Silta does not yet provide a production server, Python execution bridge, ORM,
deployment system, authentication, GraphQL, or gRPC support.

## License

Licensed under either:

- Apache License 2.0
- MIT License

at your option.
