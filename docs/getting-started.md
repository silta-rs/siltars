# Getting Started

Silta is Pre-Alpha. These instructions verify the repository and
show the current Python-facing API shape.

## Requirements

- Rust toolchain compatible with the workspace `rust-version`.
- Python 3.10 or newer.

## Verify Rust Crates

```bash
cargo test --workspace
```

## Run the Python Example

```bash
PYTHONPATH=python python examples/hello-world/app.py
```

Expected output is a Python dictionary describing the application and its route
metadata. It is not a running HTTP service.

## Inspect With The CLI

Install the local package:

```bash
python -m pip install .
```

Inspect the example app metadata:

```bash
silta inspect examples/hello-world/app.py:app
```

The CLI supports metadata inspection and can start the first Rust runtime
prototype when the `silta-runtime` binary is available.

## Current Python API

```python
from silta import App

app = App()

@app.get("/hello")
async def hello():
    return {"hello": "world"}
```

The `App` object records declarations that a future runtime boundary can turn
into an application representation. Silta does not yet expose `Model`, an ORM,
server startup, or deployment commands.
