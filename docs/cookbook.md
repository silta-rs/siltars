# Silta Cookbook for FastAPI and Django Developers

This book follows everyday tasks: start a service, receive JSON, call Python,
set a deadline, recover from failure, and test the result. Recipes 1–10 use the
current repository; recipe 11 lists migration gaps. Silta remains Pre-Alpha.

The complete runnable application is [examples/cookbook/app.py](../examples/cookbook/app.py).
The crash and slow routes are local test tools; do not expose them in a deployed
application.

## 1. Start an application

From a checkout, build the runtime and install the Python package with uv:

```bash
cargo build -p silta-runtime
uv venv
uv pip install -e .
uv run --no-project silta dev examples/cookbook/app.py:app \
  --runtime-bin ./target/debug/silta-runtime --port 8000
```

Run commands from the repository root. The Rust build needs the platform build
dependencies, including OpenSSL development libraries on Linux. The examples
use POSIX shell syntax; on Windows use the corresponding `.exe` runtime path.
The Python wheel does not yet bundle the Rust binary.

`silta dev` currently starts one runtime. It is not an automatic reload server.
Restart it after editing code or route declarations; worker recovery reloads
Python code but does not rebuild the already exported routing plan.

To inspect which routes execute in Rust and which call Python:

```bash
uv run --no-project silta inspect examples/cookbook/app.py:app
```

## 2. Add a native health endpoint

```python
from silta import App

app = App(name="orders")

@app.get("/health", response={"status": "ok"})
def health():
    pass
```

```bash
curl -i http://127.0.0.1:8000/health
```

Expected: `200` and `{"status":"ok"}`. `response=...` is a static declaration;
the function is not invoked for requests. This endpoint can remain available
while the Python worker restarts. It proves HTTP liveness, not readiness of
Python handlers, the database, or other dependencies.

An ordinary decorated function without `response=...` runs in Python. Do not
set `python=False` to speed up arbitrary Python code: that flag selects the
legacy symbolic native operations and is not a Python compiler switch.

## 3. Receive JSON and return a dictionary

```python
@app.post("/echo")
async def echo(request):
    return {"received": request["body"]}
```

```bash
curl -i http://127.0.0.1:8000/echo \
  -H 'Content-Type: application/json' -d '{"order_id":42}'
```

Expected: `200` and `{"received":{"order_id":42}}`.
The handler receives a dictionary with `body`, not a FastAPI `Request` or Django
`HttpRequest`. An empty body becomes `None`; a valid JSON value can be a scalar,
array, or object. Validate the shape before using object-specific operations.
Malformed JSON returns `400` before Python runs.

Type annotations do not yet generate extraction or validation. There is no
automatic Pydantic model binding or `422` response. A Python exception currently
becomes `500`; returning a dictionary containing a `status` key does not set an
HTTP status code. Custom response/status APIs are a migration gap.

## 4. Use async Python code

```python
import asyncio

@app.get("/async")
async def async_example():
    await asyncio.sleep(0.01)
    return {"completed": True}
```

A worker reuses its asyncio event loop between requests. One worker still
executes one request at a time, so awaiting I/O does not allow another HTTP
handler to execute in that worker. Native Rust routes remain independent.

The loop does not run while the worker synchronously waits for its next IPC
request. Do not use detached `asyncio.create_task()` calls as a reliable job
queue. Worker restarts also lose globals, caches, and pending tasks. Durable
work needs an external job system; lifecycle/dependency hooks are not yet
available in the Python API.

## 5. Set a request deadline

```bash
uv run --no-project silta dev examples/cookbook/app.py:app \
  --runtime-bin ./target/debug/silta-runtime --request-timeout-ms 1000
```

Or configure the default through the environment:

```bash
SILTA_REQUEST_TIMEOUT_MS=1000 uv run --no-project silta dev \
  examples/cookbook/app.py:app --runtime-bin ./target/debug/silta-runtime
```

The CLI value overrides a valid environment default. The default is 30,000 ms;
the supported range is 1–86,400,000 ms. Invalid values fail startup. Parsing an
invalid environment value fails even if a CLI override is also supplied.

```bash
curl -i -X POST http://127.0.0.1:8000/slow
curl -i http://127.0.0.1:8000/worker
```

The slow request returns `504` with `{"error":"request deadline exceeded"}`.
The supervisor kills and reaps an active timed-out worker and starts a fresh
one; the next request uses its remaining deadline to wait for recovery.
Cleanup can complete just after the client receives `504`.

The deadline starts when HTTP headers have been parsed. It includes body
extraction, queueing, worker startup/recovery, Python execution, and native
async operations through response creation. It is not a socket/header-read
or response-streaming timeout. Native futures are cancelled cooperatively;
a synchronous CPU operation cannot be preempted by an async timer.

A timeout does not roll back a completed database write or outbound request.
No failed request is automatically replayed. Design write operations with
idempotency and transaction boundaries before adding client retries.

## 6. Recover from a worker crash

With the sample application running:

```bash
curl -i http://127.0.0.1:8000/worker
curl -i -X POST http://127.0.0.1:8000/crash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/worker
```

The crash request returns `500`. Its worker is reaped before the response,
`/health` still returns `200`, and a subsequent successful `/worker` response
contains a new PID. Worker recovery also runs after an idle worker dies; a new
HTTP request is not required to trigger it.

Repeated startup failures back off from 100 ms to a maximum of five seconds.
The runtime requires a readiness frame after app import, with a ten-second
startup limit. An import failure never receives a handler request. Expired
queued requests are skipped. Recovery retries continue until shutdown, allowing
a transient dependency or spawn failure to clear.

For an unavailable worker, requests can exhaust their deadline and return `504`.
A full queue (64 waiting calls) or shutdown produces `503`. A valid Python
exception/serialization-error reply returns `500` without restarting a healthy
worker. Broken IPC, a wrong response ID, or an oversized reply invalidates the
worker and triggers cleanup and recovery.

## 7. Keep JSON lossless and bounded

Static responses are validated before the Rust runtime starts and again when
the execution plan is exported. Python handler results are validated too.

- Integers must fit `[-2**63, 2**64 - 1]`; use a string for larger exact numbers.
- Object keys must be strings. Non-finite floats, invalid Unicode surrogates,
  cycles, and unsupported Python objects are rejected.
- The maximum JSON envelope depth is 64.
- Bridge HTTP bodies use Axum's default buffered body limit (2 MiB).
- IPC replies are limited to 16 MiB including the newline. Exceeding this limit
  returns `500` and restarts the worker.

Files and large binary payloads should eventually use streaming APIs. Encoding
files as base64 JSON would add copies and size overhead and is not the planned
file API.

## 8. Stop cleanly and inspect logs

On Unix, send SIGTERM to the CLI or runtime. The runtime stops accepting new
connections and stops dispatching/restarting Python work. An active call gets
up to five seconds to finish, then the supervisor kills and reaps its worker.
Cancelled queued requests are never dispatched.

Application `print()`, native-library stdout, and inherited subprocess stdout
are redirected to stderr in the worker. They cannot corrupt the private IPC
reply channel. Use ordinary Python logging for application diagnostics; there
is no built-in trace-ID injection or structured-log exporter yet.

A detected client disconnect cancels that HTTP call. If Python is already
executing it, the supervisor invalidates and reaps that worker. Cancellation
of a waiting call does not kill a worker executing someone else's request.

These guarantees cover the runtime-owned Python child. They do not supervise
arbitrary subprocess trees created by application code, or guarantee cleanup
when the runtime itself is forcibly killed.

## 9. Test the service over HTTP

Silta is not currently an ASGI application. FastAPI's `TestClient`, HTTPX's
`ASGITransport`, and Django's test client cannot directly host it. Start the
actual Rust binary and test it as an HTTP service:

```bash
cargo build -p silta-runtime
PYTHONPATH=python SILTA_RUNTIME_BIN="$PWD/target/debug/silta-runtime" \
  uv run --no-project python -m unittest discover -s python/tests \
  -p 'test_runtime_integration.py'
```

The suite checks crash recovery, PID reaping, timeout and disconnect cleanup,
expired queued work, overload, partial bodies, native route availability,
readiness/import failures, and SIGTERM during active work or restart backoff.
It also smoke-tests the sample application linked at the start of this book.

For business logic, keep functions separately testable and call them directly
in unit tests. Use HTTP tests to verify extraction, response codes, and process
lifecycle. See [test_runtime_integration.py](../python/tests/test_runtime_integration.py)
for the server fixture and cleanup pattern.

## 10. Export metrics without changing handlers

For Prometheus, enable a separate management port:

```bash
uv run --no-project silta dev examples/cookbook/app.py:app \
  --runtime-bin ./target/debug/silta-runtime --metrics-listen 127.0.0.1:9464
curl http://127.0.0.1:9464/metrics
```

For OpenTelemetry Collector, configure the service and HTTP metrics endpoint:

```bash
OTEL_SERVICE_NAME=orders-api \
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:4318/v1/metrics \
uv run --no-project silta dev examples/cookbook/app.py:app \
  --runtime-bin ./target/debug/silta-runtime
```

Both exporters can run together. HTTP counts, latency histograms, active
requests, queue depth/wait, worker readiness, failures/restarts, and export
outcomes are collected automatically in Rust. No extra Python package or route
decorator is required. Worker crashes do not erase counters or stop scraping;
an unavailable Collector does not block request handling.

Prometheus and Collector configuration files, exact instruments, PromQL examples,
authentication headers, timeouts, cardinality limits, and shutdown behavior are
covered in the [metrics guide](metrics.md).

Metrics export is implemented. Distributed traces, correlated log export, and
custom Python business-metric helpers remain planned. Installing a Python
instrumentation library alone would not observe native Rust route execution.

## 11. Map your existing framework features

| Existing pattern | Current Silta equivalent or migration gap |
| --- | --- |
| Route decorator / Django URL-to-view mapping | `@app.get`, `@app.post`, and other method decorators |
| JSON response dictionary / `JsonResponse` | Return a JSON-compatible Python value; ordinary replies are `200` |
| Async view | `async def`; one sequential worker, shared event loop |
| Request JSON body | `request["body"]`; invalid JSON gets `400` |
| Typed path/query/header arguments | Not yet extracted for Python handlers |
| Pydantic / serializers / forms | No automatic schema compilation or validation-error mapping yet |
| `Depends`, middleware, auth, lifespan hooks | No compatible Python API yet |
| Django ORM and migrations | No Django adapter; native SQLx benchmark routes are not a general ORM API |
| UploadedFile / UploadFile / multipart | Not implemented; planned Rust-managed streaming and cleanup |
| StreamingResponse / FileResponse | Not implemented; response-stream deadlines will need a separate contract |
| BackgroundTasks / background jobs | No durable task runner; use a separate job system |
| Custom status, headers, cookies, OpenAPI | No general Python response API or OpenAPI generator yet |
| ASGI server and test client | Silta CLI + native binary + real HTTP tests |

Migrate one self-contained endpoint first. Verify behavior and equivalent-workload
latency before expanding. Native static-response results cannot substantiate a
performance claim about Python business logic or a Django application.
