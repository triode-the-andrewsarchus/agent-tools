---
name: rust-development
description: Implement, debug, and review Rust crates and Cargo workspaces. Use for Rust code, compiler errors, ownership, APIs, dependencies, and build or test work; use rust-doc-formatting for rustdoc prose and examples.
---

# Rust development

Work with the repository's conventions and toolchain before choosing an implementation. Inspect the workspace manifest, `rust-toolchain*`, `rust-version` (MSRV), edition, enabled features, and nearby code. Check existing types, error patterns, and helpers before adding a crate or abstraction. Treat the installed toolchain, project MSRV, and latest stable Rust as separate versions.

For compiler errors, read the diagnostic and use `rustc --explain E....` when useful. Trace who must own or borrow each value and for how long. Use a clone, reference count, interior mutability, or `unsafe` only when the actual sharing or mutation requirement warrants it. Preserve the project's public API and supported targets unless the task calls for changing them.

Make the smallest change that meets the requested behavior. Choose tests that exercise the behavior or failure mode, including feature or platform cases when relevant. For public APIs and documentation, also use `rust-doc-formatting`.

Use the repository's own task commands when present. Otherwise choose the relevant subset of:

```text
cargo fmt --all --check
cargo check --workspace --all-targets
cargo test --workspace
cargo clippy --workspace --all-targets
```

Run `cargo fmt --all` to apply formatting when editing code. Add `--all-features` only if those features are intended to work together. Respect lockfiles and avoid unrelated dependency updates. Report checks run and any relevant checks that could not run.

For version-sensitive or unfamiliar behavior, verify against the [Rust Reference](https://doc.rust-lang.org/reference/), [standard library](https://doc.rust-lang.org/std/), [Cargo Book](https://doc.rust-lang.org/cargo/), or [Clippy documentation](https://doc.rust-lang.org/clippy/).
