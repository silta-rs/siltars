# Contributing

Silta is in bootstrap. Contributions should keep the repository small, explicit,
and architecture-driven.

Contributors are welcome.

## Local Checks

```bash
cargo fmt --check
cargo clippy --workspace --all-targets
cargo test --workspace
PYTHONPATH=python python examples/hello-world/app.py
```

## Guidelines

- Prefer small focused pull requests.
- Keep changes scoped to the issue or RFC being addressed.
- Prefer mature Rust ecosystem crates over custom infrastructure.
- Do not add dependencies without a clear reason.
- Do not add fake framework features to make examples look complete.
- Add tests when behavior changes.
- Add documentation when behavior, architecture, or public APIs change.
- Document architectural decisions that affect public APIs or runtime boundaries.
- Use public technical discussion for major tradeoffs whenever practical.

## Performance

Performance-sensitive changes must include benchmarks when practical.

Do not optimize based on intuition alone. Measure first.

Benchmarks should report enough environment and workload detail for another
contributor to reproduce the result.

## Commit Style

Use concise, imperative commit messages. Examples:

- `Add route table duplicate detection`
- `Document Python boundary options`
- `Bootstrap Python package metadata`
