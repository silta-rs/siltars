# Performance

Silta's performance goal is architectural: keep common backend infrastructure on
the native Rust hot path and enter Python only when application logic requires
it.

The project does not make production performance claims yet. POC benchmark
snapshots may be checked into `experiments/` as engineering evidence, but they
must state their limitations and reproduction steps.

## Principles

- Measure before publishing claims.
- Keep benchmarks reproducible and checked into the repository.
- Compare against realistic Python stacks and Rust baselines.
- Separate cold start, steady-state latency, throughput, and memory footprint.
- Track Python boundary crossings explicitly.
- Avoid optimizing code paths that the final architecture may not use.

## Future Benchmark Areas

- Startup time for small applications.
- Route matching latency.
- Request throughput for native-only routes.
- Request latency for routes that execute Python business logic.
- Memory usage under idle, warm, and concurrent-load scenarios.
- Serialization and validation cost.
- Database query overhead once a query layer exists.

## Benchmark Hygiene

Benchmarks should document:

- Hardware and operating system.
- Rust and Python versions.
- Dependency versions.
- Runtime flags and environment variables.
- Workload shape.
- Warmup strategy.
- Statistical treatment of results.

The `benchmarks/` directory is currently a placeholder for this work.
