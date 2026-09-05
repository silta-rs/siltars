# Execution Plan

Silta uses Python as its application control plane and a versioned execution
plan as the boundary to the Rust runtime. Python developers should write normal
route handlers; the framework selects the safest available execution mode.

The first schema version establishes the contract without claiming that every
operation is already native.

## Route Modes

- `native`: the request can be completed by Rust runtime modules without a
  request-time Python call.
- `hybrid`: Rust owns HTTP, routing, JSON body parsing and HTTP serialization.
  Python executes the handler and serializes its result over JSON-lines IPC.
  Typed validation and worker pooling remain future work. Request deadlines
  and worker supervision are implemented by the Rust runtime.
- `python_fallback`: Python owns behavior that is not representable by the
  hybrid contract. This is reserved for later compatibility work and is rejected
  by this runtime rather than silently treated as hybrid.

An ordinary Python handler is automatically classified as `hybrid`. A route
with a static `response` is automatically classified as `native`. The current
benchmark application can temporarily request `python=False` to preserve its
Pre-Alpha symbolic native handlers; this escape hatch is not the intended
public application model.

## Version 1 Shape

```json
{
  "plan_version": 1,
  "name": "example",
  "routes": [
    {
      "method": "POST",
      "path": "/events",
      "handler": "create_event",
      "python_handler": true,
      "execution": {
        "mode": "hybrid",
        "operation": "python_handler",
        "reason": "automatic_python_handler"
      }
    }
  ]
}
```

`python_handler` remains in version 1 as a transition field for older
Pre-Alpha runtimes. New runtimes use `execution` and reject unsupported plan
versions, unknown fields, or contradictory mode/operation combinations during
preparation. Version 1 requires `execution` on every route. An absent version is
accepted only as a legacy definition without `execution` metadata; explicit
`null` or `0` versions are invalid.

## Version 1 Invariants

- A `static_response` operation must be `native` and include a non-null native
  response. A static JSON `null` response is not supported in v1.
- A `python_handler` operation must be `hybrid` and must not include a native
  response. If the transitional `python_handler` flag is supplied, it must agree
  with the execution mode.
- A `legacy_symbolic` operation must be `native` and must not include a native
  response.
- Every explicit selection includes a non-empty reason so inspection tooling
  can explain why a route crosses the Python boundary.
- The runtime fails at startup when a plan needs Python but bridge configuration
  is missing or incomplete.

## Developer Experience

No execution flag is required for an ordinary async route:

```python
from silta import App

app = App()


@app.post("/events")
async def create_event(request):
    return {"accepted": True, "payload": request["body"]}
```

`silta inspect app:app` exposes the selected mode, operation, and reason. Later
compiler passes can promote a route from `hybrid` to `native` without changing
the Python declaration.

## Migration and Current Limits

This changes the default for decorators without `response` or `python`: they
now execute the actual Python function. Previously they selected a benchmark
Rust handler by function name or returned 501. Existing benchmark applications
must use `python=False` to keep that temporary mapping. Previously serialized
unversioned definitions retain their old behavior. The direct
`Route(..., python_handler=True)` constructor remains supported.

No Python function is executed speculatively or translated to Rust at startup.
The initial selection uses explicit response metadata and the legacy override;
there is no automatic compiler for arbitrary Python function bodies. Static
responses are not interchangeable with handlers that perform side effects.

Hybrid handlers currently accept either no arguments or one positional request
dictionary containing `body`. FastAPI-style typed arguments, dependencies,
headers and multipart inputs are not implemented in this increment.

IPC replies use a private, non-inheritable descriptor duplicated from the
runtime pipe before the worker imports application code. FD 1 is redirected to
stderr, so `os.write(1, ...)`, native C stdio, and inherited subprocess stdout
cannot interleave with protocol replies, even without a trailing newline.

Each Python worker reuses one event loop. It is still a sequential worker;
background tasks do not progress while it waits synchronously for the next IPC
line. Async resource cleanup occurs on normal worker exit.

A dedicated Rust supervisor task exclusively owns the child and its IPC streams.
HTTP tasks submit calls through a bounded queue of 64 waiting requests. There
are no process/child mutex pairs. EOF, broken IPC, active-call cancellation,
or deadline expiry invalidate the worker. EOF waits up to one second for exit,
then kills and reaps if needed; other failures kill and reap immediately. Failed
requests are never replayed. Idle exits are reaped without waiting for traffic.

The supervisor automatically restarts the worker, backing off from 100 ms to
five seconds after repeated failures. A completed IPC call resets the delay.
A readiness frame confirms app import and handler registration before dispatch;
startup is limited to ten seconds. Pending HTTP requests retain their deadlines
during recovery. Expired/cancelled queued calls are not executed. Queue overflow
returns 503; request deadline expiry returns 504. Valid Python error replies
remain correlated 500 responses without restarting the worker. IPC replies have
a 16 MiB limit, including the newline; malformed or mismatched replies fail closed.

`--request-timeout-ms` / `SILTA_REQUEST_TIMEOUT_MS` configure a global deadline
(default 30 seconds, valid range 1 ms–24 hours). It starts after HTTP headers
are parsed and includes body extraction, queue wait, worker recovery, and native
or Python execution through response creation. It does not time out header
receipt or response streaming. Native async cancellation is cooperative and does
not undo committed database effects. An active Python timeout triggers process
cleanup independently of HTTP cancellation; cleanup may complete after the 504.

On Unix, SIGINT/SIGTERM/SIGHUP stop admission and restarts, allow the active call
up to five seconds to finish, then kill and reap the worker before runtime exit.
The server explicitly joins its supervisor. This covers normal signal-driven
shutdown, not SIGKILL, runtime crashes, or arbitrary processes independently
spawned by user handlers. In-memory Python state is lost on every restart.

Unsupported, non-finite, cyclic, excessively nested, or invalid-Unicode results
produce a correlated 500 response, leaving the next request usable. JSON object
keys must be strings; integers must fit the Serde JSON signed/unsigned 64-bit
range. The maximum response envelope depth is 64. Malformed IPC requests fail
closed so Rust observes EOF and the supervisor recovers the worker.
Duplicate handler qualified names are rejected, not silently overwritten.

The same JSON validator checks static `response`/`native_response` values,
direct `Route` construction, and the whole plan at export (including payloads
mutated after registration). Integers outside `[-2**63, 2**64 - 1]`, surrogate
code points, non-finite floats, and non-string object keys fail before Rust is
started. Large integers are rejected rather than rounded to floating point;
use an explicit string representation if that is the application's contract.

## Verification

Run Python unit tests and the Rust checks from the repository root. The HTTP
integration tests require an actual compiled binary:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo build -p silta-runtime
PYTHONPATH=python SILTA_RUNTIME_BIN="$PWD/target/debug/silta-runtime" python -m unittest discover -s python/tests
```

CI runs on pull requests to both `main` and `dev`, including the actual
Rust/Python HTTP integration suite. This suite checks automatic async execution,
static native responses, exact integer boundaries and Unicode, event-loop reuse,
malformed request JSON, and recovery after serialization errors. It also checks
native/stdout noise without newlines and SIGTERM sent to either the CLI or the
runtime during a long Python handler, asserting both runtime and worker are gone.
Worker exit via `os._exit(7)` and pipe closure without exit must return 500,
remove the worker PID (including zombies), leave native routes answering 200,
and allow subsequent Python requests on a fresh worker. The suite also covers
idle crashes, protocol corruption, slow bodies, sync/async deadlines, expired
queued work, overload, client disconnects, import crash backoff, and shutdown
during restart backoff.
This suite does not establish production readiness or a
performance improvement; fresh equivalent-workload benchmarks are still needed.

## Next Compiler Passes

Execution Plan v1 is the base for the next vertical slices:

1. Describe typed path, query, header, cookie, and body inputs.
2. Compile validation and serialization schemas into prepared Rust modules.
3. Expand the supervised single worker to a pool while preserving deadlines,
   cancellation, bounded queueing, and restart isolation.
4. Add Rust-managed multipart parsing and streaming file handles so file bytes
   do not cross the Python bridge unless a handler explicitly reads them.
5. Add streaming S3, image, CSV, Arrow, and Parquet native operations.
6. Remove the symbolic benchmark handler mapping after equivalent explicit
   native operations exist.

Each slice must add malformed-input, cancellation, resource-limit, and cleanup
tests before its operation is considered production ready.
