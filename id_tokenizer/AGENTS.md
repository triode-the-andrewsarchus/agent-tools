# AGENTS.md — ID Tokenizer & Substitution Service

This component provides identifier tokenization, UUID substitution, pattern hiding, and hallucination protection for autonomous agents (Google Antigravity and OpenAI Codex).

---

## Environment & Architecture

- **Rust Version**: Rust 1.80+ (2024 edition)
- **Python Version**: Python >= 3.12
- **Virtual Environment**: `.venv` (located at `id_tokenizer/.venv`)
- **Package Source**: Rust core in `src/`, Python bindings/packages in `python/id_tokenizer`
- **MCP Server**: Stdio MCP server implemented in `id_tokenizer.mcp_server`

---

## Verification & Development Commands

Always run commands using the project virtualenv:

```bash
# Build native extension with Maturin
.venv/bin/maturin develop --release

# Run pytest test suite
.venv/bin/pytest tests/ -v

# Run smoke test
.venv/bin/python scripts/smoke_test.py
```

---

## MCP Server Tools

1. **`substitute_ids`**: Replaces raw RFC 4122 UUIDs with `${UUID_N}` placeholders before passing text to an LLM.
2. **`restore_ids`**: Restores original UUIDs from model response text; flags unknown placeholders.
3. **`encode_id`**: Encodes UUIDs or integers into token-optimized words (1 token/word), memorable words, numeric integers, shuffled integers, faux-UUIDs, or factor values.
4. **`decode_id`**: Decodes encoded representations back to original UUIDs or integers; validates checksums and bloom filters.
5. **`id_tokenizer_status`**: Reports service health, vocabularies, supported styles, and active registry sessions.
