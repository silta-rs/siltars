# Database And Stream Adapters

Silta should keep the framework core independent from a single ORM. The runtime
needs a native adapter boundary that can support different databases, query
styles, and operational limits without forcing Python developers to choose a
Rust ORM directly.

## Core Direction

The core runtime path should optimize for:

- native async execution under Tokio;
- metadata-driven query plans generated from Python definitions;
- low allocation response serialization;
- configurable connection pools;
- explicit driver and ORM adapters;
- measurable behavior under benchmark tools such as `oha`.

The core should not depend on Diesel as the only database model. Diesel can be
excellent for Rust-authored typed schemas, but Silta also needs generated query
plans and dynamic metadata produced from Python.

## Adapter Candidates

### SQLx

SQLx is the first PostgreSQL adapter in the POC runtime because it is async,
works naturally with Tokio, and supports explicit SQL. It is a good fit for the
first native hot path because Python metadata can compile down to SQL without
requiring user-authored Rust schema code.

Current weakness: dynamic SQL and generic row extraction can cost performance if
used carelessly. The POC moved DB routes to typed `query_as` mapping to reduce
hot-path overhead.

### tokio-postgres

`tokio-postgres` should remain a candidate for a lower-level high-performance
adapter. It may be useful where Silta wants less abstraction than SQLx, explicit
prepared statement management, and tighter control over query execution.

### Diesel

Diesel should be an optional adapter, not the default runtime foundation. It is
valuable for typed Rust models, migrations, and compile-time schema workflows.
That strength can be awkward for Silta's Python-first model where application
definitions are authored outside Rust.

The likely model is:

```text
Python model metadata
  -> Silta query IR
  -> selected native adapter
  -> database
```

For Diesel:

```text
Rust-authored typed schema
  -> Diesel adapter
  -> Silta runtime module
```

### ClickHouse (experimental)

The runtime carries an experimental ClickHouse path behind `--clickhouse-url`.
It uses the official `clickhouse` crate over HTTP with RowBinary decoding into
typed rows, mirrors the PostgreSQL rate routes under `/ch/*`, and exists to
measure an analytical store next to the transactional one. It is not an
adapter contract yet: routes are still mapped by symbolic handler name and
there is no query plan. See `experiments/poc-001-pip-native-runtime/benchmark.md`
for the seed and the comparison against FastAPI with `clickhouse-connect`.

## Kafka And Streams

Kafka should use the same adapter boundary. The runtime should support native
stream publishing and consuming without putting Java clients on the HTTP hot
path.

For Confluent-compatible Kafka, the likely Rust direction is a client backed by
`librdkafka`. Java-based integrations can exist at service edges, but the Silta
runtime should keep request handling, validation, serialization, database
access, and stream operations in native modules whenever practical.

## Operational Finding From POC-001

The first private local PostgreSQL container used for smoke testing had
`max_connections = 20`. That made database pool sizing a first-class runtime
concern. A pool that is too large can fail under benchmark load even when the
SQL plan itself is fast.

For local benchmark parity with FastAPI, the POC uses:

```text
db_min_connections = 1
db_max_connections = 10
db_acquire_timeout = 5000 ms
```

Higher pool sizes should be tested only after the database server's own
connection limit is raised.
