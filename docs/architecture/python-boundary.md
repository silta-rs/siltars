# Python Boundary

The Python boundary is the central architectural decision for Silta.

The goal is not for every request to call Python. The goal is:

```text
Python initialization/configuration
  -> application representation
  -> Rust runtime
  -> native hot path
```

Python should describe the application. Rust should execute infrastructure.
Crossing between Python and Rust on the hot path should be avoided unless the
request needs Python business logic.

The boundary should support a Python control plane around native Rust execution
modules. Python should configure HTTP, routing, validation, database/query,
serialization, cache, background jobs, and observability behavior. Rust should
execute those modules directly whenever the work can be represented.

Silta should not call Python on every request merely to delegate to Rust helper
functions. That would preserve Python as the hot-path scheduler and limit the
architecture's concurrency and memory advantages.

## Options

### A. PyO3 Extension Module

Python imports a native extension built with PyO3. The extension exposes Rust
functions or types directly to Python.

Tradeoffs:

- Startup cost: good once the extension is installed, but import-time native
  loading must be measured.
- Runtime overhead: good for coarse calls, poor if request handling requires
  many fine-grained Python-to-Rust crossings.
- GIL: calls start in Python and must respect Python's threading model.
- Object allocation: risk of many Python wrapper objects if the API is too
  granular.
- Memory: usually better than a full Python framework stack, but still tied to
  Python process memory.
- Debugging: familiar to Python users until failures cross into native code.
- Packaging: native wheels are required for supported platforms.
- Deployment: deployment must include compatible wheels or local builds.
- Async compatibility: possible, but async boundaries need careful design.
- Developer experience: strong if the API feels like normal Python.

### B. Embedded CPython

A Rust binary embeds CPython and loads a Python application during startup.

Tradeoffs:

- Startup cost: potentially higher because Rust owns interpreter setup.
- Runtime overhead: can be low if Python is used only for initialization or
  selected business logic.
- GIL: still present when Python executes.
- Object allocation: can be constrained if the Rust runtime consumes a compact
  representation after initialization.
- Memory: includes embedded interpreter cost.
- Debugging: harder because Python runs inside a Rust-owned process.
- Packaging: Rust binary and Python environment packaging must be solved
  together.
- Deployment: attractive for small containers if Python assets are bundled
  cleanly.
- Async compatibility: complex when coordinating Rust tasks and Python
  coroutines.
- Developer experience: strong only if error reporting and local iteration are
  excellent.

### C. Python Process Plus Rust Runtime

Python runs as its own process and communicates with a Rust runtime process over
IPC, sockets, or another control plane.

Tradeoffs:

- Startup cost: higher because multiple processes must be launched and
  coordinated.
- Runtime overhead: depends on IPC frequency; unacceptable if every request
  crosses the process boundary.
- GIL: isolated to the Python process.
- Object allocation: Python objects stay out of Rust memory, but serialization
  costs can appear.
- Memory: higher baseline from multiple processes.
- Debugging: process boundaries are visible and inspectable.
- Packaging: can keep Python and Rust packages more independent.
- Deployment: more moving parts unless managed by a wrapper.
- Async compatibility: IPC protocol must map async behavior cleanly.
- Developer experience: can be understandable, but local startup must be simple.

### D. Generated Application IR

Python executes at build time or startup to produce a versioned application
intermediate representation that the Rust runtime loads.

Tradeoffs:

- Startup cost: can be excellent when IR is pre-generated; startup generation
  cost depends on app size.
- Runtime overhead: best fit for native hot paths because Rust consumes a stable
  representation.
- GIL: absent from native paths that do not call Python business logic.
- Object allocation: minimized on the hot path.
- Memory: potentially lowest if runtime state is compact.
- Debugging: requires source mapping from IR back to Python declarations.
- Packaging: requires IR schema versioning and compatibility checks.
- Deployment: promising for small containers and reproducible builds.
- Async compatibility: Python async functions still need a later execution
  strategy when invoked.
- Developer experience: strong if generation is transparent and errors point to
  Python source.

This option best matches the native-module goal for representable CRUD and REST
paths, but it still needs a separate strategy for custom Python business logic.

### E. Hybrid Architecture

Silta may combine the above: Python declares an application, a generated IR
describes native infrastructure, and selected Python handlers are invoked through
a controlled bridge only when needed.

Tradeoffs:

- Startup cost: depends on whether IR is generated ahead of time or at startup.
- Runtime overhead: can be low if native routes avoid Python crossings.
- GIL: limited to requests that execute Python handlers.
- Object allocation: native route state can remain compact.
- Memory: likely higher than pure Rust, lower than conventional Python stacks if
  Python is not in every path.
- Debugging: most complex unless tooling makes the active boundary obvious.
- Packaging: must handle both native runtime and Python application assets.
- Deployment: can support production containers if the packaging model is
  disciplined.
- Async compatibility: requires a clear contract between Rust futures and Python
  awaitables.
- Developer experience: strongest long-term option if complexity is hidden
  behind a simple Python API.

This is the most likely long-term shape if prototypes prove that native module
execution can be configured from Python while preserving a good developer
experience.

## Current Bootstrap Position

The repository does not choose a final boundary yet.

The current Python package records declarations through `App`. The current Rust
workspace defines minimal application and routing metadata. The next decision is
how Python-authored metadata becomes a versioned representation that Rust can
prepare and execute.

## Decision Criteria

Any boundary design should be evaluated against:

- Number of Python-to-Rust crossings per request.
- Ability to keep routing, middleware, validation, and serialization native.
- Ability to keep representable database/query work native.
- Whether Python remains a control plane or becomes the hot-path scheduler.
- Startup time in local development and production.
- Memory footprint under concurrent load.
- Packaging across Linux, macOS, and common container environments.
- Error reporting that points back to Python source.
- Async execution semantics.
- Benchmark reproducibility.
