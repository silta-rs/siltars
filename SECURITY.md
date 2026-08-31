# Security Policy

Silta is not production-ready yet. Please do not rely on it for production
systems until the project publishes a stable security posture.

## Reporting Vulnerabilities

Until a dedicated private reporting channel is published, avoid disclosing
security-sensitive details in public issues. Contact the maintainers privately
through the `silta-rs` organization where possible.

## Scope

Current security scope is limited to the repository's bootstrap code and
packaging metadata. There is no production runtime, authentication layer,
database layer, deployment tool, or Python execution bridge yet.

## Expectations

Future security work should cover:

- Python execution boundary hardening.
- Dependency auditing.
- Supply-chain integrity for wheels and Rust crates.
- Request validation behavior.
- Safe defaults for deployment artifacts.
