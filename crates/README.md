# Rust Crates

This directory contains Rust crates for the Silta runtime.

Current crates:

- `silta-core`: shared application representation types.
- `silta-http`: HTTP boundary vocabulary.
- `silta-router`: router abstraction.
- `silta-runtime`: runtime preparation skeleton.

Crates should stay small and explicit. Do not add a crate until there is a real
ownership boundary and implementation need.

Silta should prefer mature Rust ecosystem components over custom replacements.
