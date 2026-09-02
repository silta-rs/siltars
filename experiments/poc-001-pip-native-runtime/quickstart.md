# Quick Start

This quick start describes the target developer experience for POC-001.

The current repository includes the first native Rust runtime prototype.
`silta inspect` reads the Python application definition. `silta dev` validates
that definition and starts the Rust runtime binary for supported native routes.

## Target Silta Flow

Create a virtual environment:

```bash
uv venv
. .venv/bin/activate
```

Install Silta:

```bash
uv pip install siltars
```

`siltars` is not published on PyPI yet, so this command does not work today.
Install the package from the repository checkout instead (run from this
experiment directory):

```bash
uv pip install -e ../..
```

Inspect the app definition:

```bash
silta inspect silta_app:app
```

Run the app:

```bash
silta dev silta_app:app --host 127.0.0.1 --port 8000
```

Call the endpoint:

```bash
curl http://127.0.0.1:8000/ping
```

Expected response:

```json
{"ok":true}
```

Start the reproducible PostgreSQL container:

```bash
docker compose up -d postgres
```

Run against the local experiment database:

```bash
cargo build -p silta-runtime --release
SILTA_RUNTIME_BIN="$PWD/../../target/release/silta-runtime" \
  SILTA_PORT=8104 \
  ./scripts/run_silta_native.sh
```

Then call real exchange-rate data:

```bash
curl http://127.0.0.1:8104/rates/EUR/USD
```

## Developer Expectation

The target packaged experience is that the Python developer should not need to
run:

```bash
cargo build
```

or install a Rust toolchain.

The Silta wheel should already contain the native runtime artifact for the
developer's platform.

## Baseline Flow

Use the experiment PostgreSQL container:

```bash
docker ps --filter name=silta-poc-postgres
```

This experiment reads the seeded `public.rates` table. Do not commit local
database passwords into the repository. To use a private development database
instead, set `POSTGRES_CONTAINER`, `POSTGRES_HOST`, and `POSTGRES_PORT`.

Install baseline dependencies:

```bash
uv pip install -r requirements-baseline.txt
```

Run FastAPI baseline:

```bash
./scripts/run_fastapi_rates_baseline.sh
```

Run Litestar baseline:

```bash
litestar --app baselines.litestar_app:app run --host 127.0.0.1 --port 8102
```

Benchmark commands are in [benchmark.md](benchmark.md).
