# Distribution And Installation

Silta must be usable by Python developers who do not know Rust and do not want
to compile Rust code locally.

The intended user experience is:

```bash
pip install silta
```

Then:

```bash
silta dev
```

or:

```bash
python app.py
```

depending on the chosen runtime launch model.

## Product Requirement

A normal Python developer should not need:

- Rust toolchain installation.
- Cargo knowledge.
- Native compiler setup.
- Manual Rust builds.
- Local linking/debugging of Rust runtime internals.

Rust should be present as prebuilt native artifacts distributed through Python
package wheels.

## Distribution Model

The likely package shape is:

```text
silta Python package
  -> Python API / DSL
  -> bundled native Rust runtime artifact
  -> platform-specific wheel
```

The Python package should provide the developer-facing API. The wheel should
ship the Rust runtime module or executable needed to serve native paths.

The exact mechanism remains subject to prototype results:

- Native extension module loaded by Python.
- Bundled Rust runtime binary launched by the Python package.
- Hybrid package with both extension and runtime binary.
- Generated application IR consumed by a Rust runtime artifact.

The requirement is stable even if the mechanism changes: `pip install silta`
must install everything needed for normal local use on supported platforms.

## Wheel Strategy

Silta should publish prebuilt wheels for supported platforms before claiming a
developer-friendly release.

Initial target matrix:

- Linux x86_64.
- Linux aarch64.
- macOS arm64.
- macOS x86_64.

Windows support should be evaluated, but not allowed to block the first runtime
prototype.

Source distributions may exist, but they should not be the primary installation
path for ordinary users. If installation falls back to building Rust locally,
the experience has failed for the target Python developer.

## CLI Requirement

The Python package should eventually expose a CLI entry point:

```bash
silta
```

Potential commands:

```text
silta dev
silta run
silta test
silta benchmark
silta build
silta deploy
```

These commands should orchestrate the native runtime without requiring users to
call Cargo directly.

## Runtime Launch Requirement

The launch path should preserve the architecture:

```text
Python app import/configuration
  -> Application Definition / IR
  -> Native Rust runtime artifact
  -> Rust HTTP/router/database/serialization modules
```

The Python package may start, configure, or communicate with the Rust runtime.
It should not become the hot-path request scheduler.

## Performance Claims

Silta is designed for efficient high-concurrency backend workloads and aims to
reduce runtime overhead for common Python backend workloads.

The project must not claim that Silta is "dozens of times faster" or use similar
benchmark language until reproducible benchmark results exist.

The distribution model should make performance possible by default:

- Native Rust runtime artifact installed with the Python package.
- Native routing and serialization for representable endpoints.
- Native database/query execution for representable ORM operations.
- Minimal Python/Rust crossings on hot paths.
- No local Rust compilation requirement for users.

## Developer Experience Contract

A Python developer should be able to:

1. Install Silta with `pip`.
2. Define an application in Python.
3. Run the application without knowing Cargo.
4. Get clear Python-facing errors for application definition mistakes.
5. Use native Rust execution for representable HTTP, database, and JSON paths.
6. Drop down to Python business logic where necessary.

This is the packaging and installation standard future implementation work
should target.
