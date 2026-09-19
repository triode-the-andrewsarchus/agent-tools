---
name: rust-doc-formatting
description: Write or revise Rust API documentation and rustdoc examples using RFC 1574 Appendix A as the style base. Use for rustdoc comments, documentation style and layout, API examples, and documentation review; use rustfmt for source-code layout.
---

# Rust API documentation style

Use [RFC 1574, Appendix A](https://github.com/rust-lang/rfcs/blob/master/text/1574-more-api-documentation-conventions.md#appendix-a-full-conventions-text) as the base for API documentation. Follow an existing project's explicit documentation conventions where they differ. The RFC's American English rule explicitly addresses `rustc` and the standard library; do not impose it on unrelated projects without a local preference.

- Start an item doc comment with one short summary sentence suitable for rustdoc listings. Prefer third-person present tense: “Returns …”, “Creates …”. Add a blank doc line before further detail.
- Use `///` on items and `//!` for crate or module overview docs. Prefer line comments over block comments. For a `mod` block, prefer `///` immediately above the module when it reads well.
- Use Markdown in doc comments. Put applicable sections under `# Examples`, `# Errors`, `# Panics`, and `# Safety`; use the plural `Examples` even for one example. Document behavior and caller obligations rather than adding empty template sections.
- Put code terms in backticks. Use fenced code blocks, marking non-Rust languages and choosing rustdoc attributes (`no_run`, `compile_fail`, `ignore`) only for their actual purpose. In long-form Markdown, label Rust fences explicitly.
- Give public APIs useful examples when feasible. Prefer small runnable examples that demonstrate why the API is useful and assert meaningful results. Keep examples compatible with the project's MSRV and features. Use `?` for ordinary fallible examples when practical.
- Spell generic types with parameters when discussing the type itself, such as `Option<T>`. Use generic lowercase terms only when intentionally referring to a broader concept.
- Link important API names. Prefer modern rustdoc intra-doc links such as ``[`Option<T>`]`` or ``[`Self::method`]`` over the RFC's older hand-written `.html` paths. Use reference-style links when a prose link has a URL target and that form helps readability.
- Keep module docs broad; document each type's contract on its own page. Small duplication is acceptable when it makes a type page self-contained.

Check rendered output and run relevant doctests, typically `cargo test --doc` and `cargo doc --no-deps`. Resolve broken links and example failures. Use `cargo fmt --all` for source-code layout; rustfmt does not replace prose review.

For current link syntax and doctest behavior, consult the [rustdoc book](https://doc.rust-lang.org/rustdoc/). The [Rust API Guidelines documentation chapter](https://rust-lang.github.io/api-guidelines/documentation.html) provides related API guidance.
