# Licensing Policy

Silta is licensed under the Apache License, Version 2.0.

This project uses the SPDX identifier:

```text
Apache-2.0
```

## Why Apache-2.0

Silta is open-source infrastructure for Python and Rust developers. Its license
should support:

- Public open-source development.
- Commercial and private use.
- Forks and downstream integrations.
- Use in Rust applications and Python packages.
- Compatibility with common permissive Rust ecosystem dependencies.
- Clear patent terms for contributors and users.

Apache-2.0 is a permissive license with an explicit patent grant and a patent
termination clause. That makes it a better fit than MIT-only for a
patent-sensitive infrastructure project.

## Outbound License

All Silta code is distributed under Apache-2.0 unless a file clearly states
otherwise.

Cargo metadata should use:

```toml
license = "Apache-2.0"
```

Python package metadata should also declare:

```toml
license = "Apache-2.0"
```

## Inbound Contributions

Unless explicitly stated otherwise, contributions intentionally submitted to
Silta are submitted under Apache-2.0.

Contributors should not submit code they cannot license under Apache-2.0.

## Project Origin And Attribution

Silta was originally conceived and initiated by Serrka.

Original initiator profile: <https://github.com/Sergey2Gnezdilov/>

The project includes a `NOTICE` file so the original project roots and initiator
attribution are preserved in source distributions, forks, and derivative works
as part of the Apache-2.0 notice model.

Downstream projects may add their own notices for their own modifications, but
should preserve the original Silta attribution notices and should not remove or
obscure the project origin.

This attribution requirement protects the roots of the project. It does not
change the permissive nature of Apache-2.0.

## Dependency Policy

Silta should prefer dependencies that are compatible with open-source
infrastructure and broad ecosystem adoption.

Preferred dependency licenses:

- Apache-2.0.
- MIT.
- BSD-2-Clause.
- BSD-3-Clause.
- ISC.
- Zlib.
- Other common permissive licenses after review.

Rust ecosystem projects such as Tokio, SQLx, Diesel, Serde, tracing, and similar
building blocks may use permissive licenses or dual-license models. Silta can
depend on permissively licensed crates when their terms are compatible with
Apache-2.0 distribution.

Every dependency must still be reviewed on its own license terms.

## Copyleft Criteria

Silta is not a copyleft project. Apache-2.0 does not require downstream projects
or forks to publish their source code.

Copyleft dependencies require extra care:

- Strong copyleft dependencies, including GPL-family licenses, should not be
  added to core runtime crates without an RFC and explicit maintainer approval.
- AGPL-family dependencies should be avoided in core runtime, CLI, bridge, and
  packaging components unless the project intentionally accepts the network-use
  source distribution obligations.
- LGPL/MPL-style weak copyleft dependencies may be acceptable only when their
  obligations are well understood, isolated, documented, and compatible with the
  intended distribution model.
- Optional integrations with copyleft components should be isolated behind
  feature flags, separate crates, separate processes, or external adapters where
  practical.
- Generated artifacts, user applications, and downstream deployments should not
  unexpectedly inherit copyleft obligations from Silta internals.

If a dependency creates uncertainty about source distribution, static linking,
network service obligations, patent terms, or commercial adoption, require an
RFC or maintainer license review before adding it.

## Forks And Downstream Use

Apache-2.0 allows forks, modifications, redistribution, private use, and
commercial use.

Downstream users must comply with Apache-2.0 obligations, including preserving
license notices and stating significant changes where required.

If a downstream work includes a `NOTICE` file or distributes Silta source or
derivative works, it should include a readable copy of Silta's attribution
notices in the manner required by Apache-2.0.

Silta should keep generated Docker, Kubernetes, OpenAPI, and other artifacts
inspectable and customizable. Users should not become prisoners of the
framework.

## Trademarks

The Apache-2.0 license covers copyright and patent permissions. It does not
grant trademark rights.

The Silta name, logos, domains, and project identity may need a separate
trademark policy as the community grows. See `TRADEMARKS.md` for the current
project intent.

## Practical Rule

When choosing between license compatibility, adoption, and patent safety:

1. Prefer permissive dependencies.
2. Prefer Apache-2.0-compatible terms.
3. Avoid strong copyleft in core components.
4. Require benchmarks and technical justification for performance-sensitive
   dependency choices.
5. Document non-obvious license decisions.
