# Silta Project

> Bridge Python. Power with Rust.

Silta is an open-source runtime-first backend platform. It combines Python's
developer experience with the performance, efficiency, and scalability of the
Rust ecosystem.

Developers write applications in Python. Silta's long-term goal is to execute
the infrastructure-heavy parts of those applications inside a native Rust
runtime.

Silta's core belief is simple:

> Python should describe the application. Rust should execute the runtime.

## The Problem

Python is one of the most productive backend languages. It lets teams build
products quickly, but production services often run into the same operational
costs:

- High RAM usage.
- Large container images.
- Multiple worker processes.
- Lower request throughput than native runtimes.
- Slow cold starts.
- Heavy deployment stacks.
- Expensive infrastructure at scale.

The usual answer is to rewrite the service in Go or Rust. Silta exists to make
that tradeoff less necessary.

## The Vision

Silta separates application description from application execution.

Python is the language developers use to describe:

- Routes.
- Models.
- Configuration.
- Permissions.
- Business logic.

Rust is the engine that executes infrastructure:

- HTTP serving.
- Routing.
- Middleware.
- Validation.
- Query planning.
- Serialization.
- Observability.
- Deployment-oriented runtime behavior.

Instead of executing every HTTP request inside CPython, Silta should move the
request pipeline into Rust and enter Python only when custom business logic
requires it.

Silta should not be a wrapper around Python HTTP, ORM, or serialization
libraries. It should provide a Python framework surface over native Rust runtime
modules.

## Runtime First

Silta is not just another web framework. The runtime is the product. The Python
framework is the developer interface.

The target shape is:

```text
Python application
  -> Python API / DSL
  -> application representation / IR
  -> Rust runtime
  -> native execution
```

Silta should improve Python backend performance by replacing the infrastructure
underneath Python, not by pretending CPython is a native backend runtime.

## The Hot Path

Traditional Python backend request path:

```text
HTTP
  -> ASGI
  -> Python router
  -> Python middleware
  -> Python validation
  -> Python ORM
  -> SQL
  -> Python JSON serialization
  -> response
```

Silta's target request path:

```text
HTTP
  -> Rust HTTP server
  -> Rust router
  -> Rust middleware
  -> Rust validation
  -> Rust query layer
  -> SQL
  -> Rust serialization
  -> response
```

Python should be executed only when a request needs Python business logic.

## Execution Modes

### Native Mode

Native mode is the target path where a request never enters Python.

This should eventually fit workloads such as:

- CRUD endpoints.
- REST APIs.
- Internal APIs.
- Admin panels.
- Small production microservices.

### Python Mode

Python mode is for custom business logic that should remain in Python, such as:

- Payments.
- Complex authorization.
- AI pipelines.
- External API orchestration.
- Domain-specific logic that cannot be represented natively.

After Python logic returns, Rust should continue response handling,
serialization, observability, and other runtime work.

## ORM Philosophy

Silta should not execute ORM infrastructure in Python on the hot path.

The intended direction is for Python to create an abstract query representation:

```python
User.where(User.age > 18).limit(20)
```

The runtime can then prepare and execute the query natively:

```text
Python query expression
  -> application/query representation
  -> Rust query builder
  -> prepared statement
  -> database
```

This is a long-term architectural direction, not functionality that exists in
the bootstrap repository.

The ORM is only one native module in the larger runtime system. Python should
describe models and query intent. Rust should own representable query execution,
connection pooling, prepared statements, and serialization.

## Automatic CRUD

Silta should eventually make common CRUD endpoints native by default.

Potential future API:

```python
class User(Model):
    id: int
    name: str

app.crud(User)
```

Potential generated endpoints:

```text
GET /users
GET /users/{id}
POST /users
PATCH /users/{id}
DELETE /users/{id}
```

The goal is native Rust execution without generated Python request handlers.

## Serialization

Typical Python serialization:

```text
Python object
  -> json.dumps()
  -> response bytes
```

Silta's target serialization path:

```text
Rust value
  -> Serde
  -> bytes
  -> socket
```

The goal is fewer Python allocations, less garbage collection pressure, and
lower per-request overhead.

## Deployment Philosophy

Deployment should become part of the framework experience. Developers should
not need to hand-write the same infrastructure for every service:

- Dockerfiles.
- Compose files.
- Kubernetes manifests.
- Helm charts.
- Ingress rules.
- Health checks.
- OpenAPI configuration.
- Metrics setup.
- Tracing setup.

Future Silta tooling should make production defaults accessible through a
coherent CLI and application configuration.

Potential future commands:

```bash
silta new
silta run
silta dev
silta test
silta benchmark
silta build
silta deploy
silta doctor
silta update
```

This deployment layer is a long-term goal and is intentionally outside the
bootstrap implementation.

## Infrastructure as Code

Infrastructure should live next to application code when doing so improves
clarity and deployment safety.

Potential future API:

```python
app.service(
    replicas=3,
    cpu="500m",
    memory="512Mi",
)
```

Silta could use this metadata to generate deployment artifacts such as
deployments, services, ingress, secrets, config maps, and autoscaling policy.

## Observability

Production services should have observability built in:

- OpenTelemetry.
- Metrics.
- Tracing.
- Health endpoints.
- Structured logging.

These should become runtime defaults, not separate projects every application
team has to assemble from scratch.

## What Silta Is

- A runtime platform.
- A Python developer interface.
- A Rust execution runtime.
- A production-oriented backend platform.
- Kubernetes-friendly over time.
- Docker-native over time.
- Open source.

## What Silta Is Not

- A FastAPI clone.
- A conventional Python ORM.
- An ASGI server.
- A Rust HTTP framework competing with Hyper, Axum, or Tower.
- A collection of fake features that only work in examples.

Silta should expose the Rust ecosystem to Python developers through a coherent
runtime-first architecture.

## Roadmap

### Phase 1: Runtime Foundation

- Runtime architecture.
- Router abstraction.
- Application representation.
- Model representation.
- CRUD design.
- PostgreSQL strategy.

### Phase 2: Application Capabilities

- Authentication.
- Redis integration.
- Caching.
- Background jobs.
- OpenAPI generation.

### Phase 3: Production Platform

- Container builds.
- Kubernetes manifests.
- Deployment workflow.
- Observability defaults.

### Phase 4: Extended Protocols and Integrations

- gRPC.
- GraphQL.
- Multiple databases.
- Cloud integrations.

## Open Source Model

Silta should be developed in public:

- The original project roots and initiator attribution should be preserved.
- Architecture discussions happen in public.
- Major decisions go through RFCs.
- Benchmarks are reproducible.
- Performance claims are measurable.
- Licensing is Apache-2.0.

Silta was originally conceived and initiated by Сергей Гнездилов
(Serge Gnezdilov).

## Current Status

Silta is Pre-Alpha. The current repository contains:

- A minimal Rust workspace.
- Initial runtime, route, HTTP, and core crate boundaries.
- A minimal Python `App` object.
- A native Rust runtime prototype for HTTP, JSON, Python-produced application
  definitions, and PostgreSQL-backed benchmark routes.
- Local benchmark reports comparing Silta and FastAPI as prototype signals.
- Architecture documentation.
- Project governance and contribution scaffolding.

It does not yet contain a production Python-to-Rust bridge, ORM, CRUD runtime,
stable error contract, deployment system, authentication, GraphQL, or gRPC
support.

## Mission

Bridge Python. Power with Rust.

## Motto

Write Python. Run Rust.
