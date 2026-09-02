# Roadmap

Silta's roadmap is organized by capabilities, not dates.

The first MVP must prove the core use case:

```text
PostgreSQL
    |
    v
Model
    |
    v
CRUD
    |
    v
REST
    |
    v
JSON
```

Proposed API. Subject to RFC.

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

The API above is not final. The MVP succeeds only if it proves that a Python
developer can define a useful backend service with minimal code while the common
request path executes primarily in Rust, with measurably lower runtime overhead
than a conventional Python stack.

The MVP should prove Silta is not a wrapper around Python HTTP or ORM code.
Python should describe the service. Native Rust modules should execute the
representable request path.

## Phase 0: Foundation

- Repository.
- Manifesto.
- Architecture.
- RFC process.
- CI.
- Development tooling.
- Initial benchmarks.

## Phase 1: Runtime Prototype

Goal:

Prove that Python can describe a service while the common HTTP path executes
primarily in Rust.

- Rust runtime.
- HTTP server.
- Routing.
- Basic Python bridge.
- JSON responses.
- Basic configuration.
- Native endpoint configured from Python.
- Explicit Rust-only versus Rust-Python-Rust benchmark paths.
- Local developer launch through Python package commands.

First prototype target:

```text
Python App definition
  -> Silta Bridge / IR
  -> Rust HTTP module
  -> Rust router module
  -> Rust JSON response
```

## Phase 2: Database

- PostgreSQL.
- Connection pooling.
- Models.
- Query representation.
- CRUD.
- Migrations.
- Transactions.
- Native Rust execution for representable ORM/query operations.

Database prototype target:

```text
Python Model definition
  -> query/application representation
  -> Rust database/query module
  -> PostgreSQL
  -> Rust serialization
  -> JSON
```

## Phase 3: Production API

- Validation.
- Middleware.
- OpenAPI.
- Authentication.
- Authorization.
- Structured errors.
- Health checks.
- Python-facing runtime errors.
- CLI entry point.

## Phase 3.5: Distribution

- Prebuilt Python wheels.
- Bundled native Rust runtime artifact.
- Linux x86_64 wheel.
- Linux aarch64 wheel.
- macOS arm64 wheel.
- macOS x86_64 wheel.
- Source distribution with clear fallback behavior.
- Installation tests without local Rust toolchain.

## Alpha Milestone

Silta should be called Alpha only after the project can support early external
experimentation without requiring Rust knowledge for the standard Python
workflow.

Required criteria:

- `pip install siltars` installs a platform wheel with the native runtime
  artifact.
- The Python route API is stable enough for early users.
- Native PostgreSQL CRUD works from Python model definitions.
- Runtime configuration is documented for local and container deployments.
- Benchmark runs are reproducible in CI and locally.
- Example applications demonstrate the Python-defined, Rust-executed path.
- Known limitations are documented clearly.

Beta should come later, after external users can build small real services on
the Python-defined, Rust-executed path and the Python bridge/ORM contracts have
stabilized.

## Phase 4: Performance

- Benchmark suite.
- Memory profiling.
- Allocation profiling.
- Concurrency testing.
- Startup benchmarks.
- Container benchmarks.

## Phase 5: Deployment

- Docker / OCI images.
- Production image optimization.
- Configuration management.
- Secrets.
- Kubernetes manifests.
- Health/readiness probes.
- Autoscaling.
- Observability.

Future `silta build` should create an OCI-compatible image.

Future `silta deploy` should be able to generate or apply standard Kubernetes
resources. Silta should not replace Kubernetes. Users should be able to run a
command such as `silta kubernetes generate` and inspect or customize ordinary
YAML.

## Phase 6: Extended Protocols

Potential integrations:

- WebSockets.
- gRPC.
- GraphQL.
- Background jobs.
- Redis.
- Caching.

These should reuse mature Rust ecosystem components wherever possible.

## Phase 7: Ecosystem

- Plugin system.
- Integrations.
- Documentation.
- Examples.
- Community tooling.
- Deployment providers.

## Future Integrations

The following are future integrations, not initial implementation scope:

- GraphQL.
- gRPC.
- WebSockets.
- Redis.
- Kafka.
- RabbitMQ.
- Auth provider integrations.
- Cloud providers.
- Kubernetes operator.
- Service mesh.
- Admin panel.
- Frontend.
- AI features.

The next technical stage is:

> Build the smallest possible Silta runtime prototype.

Start with [POC-001: Python-defined, Rust-executed endpoint](docs/pocs/001-python-defined-rust-executed-endpoint.md).

The corresponding experiment folder is
[experiments/poc-001-pip-native-runtime](experiments/poc-001-pip-native-runtime/README.md).
