# AGENTS.md — Pulpie Preprocessing Service

This repository provides a fast, lightweight web-content preprocessing service and Model Context Protocol (MCP) server for AI coding assistants (including Antigravity and Codex). It strips web boilerplate (navigation bars, ads, cookie banners, tracking scripts, sidebars, footers) while strictly preserving document structure, headings, tables, code blocks, math formulas, and links.

---

## Environment & Architecture

- **Python Version**: Python >= 3.12
- **Virtual Environment**: `.venv` (located at `/home/vega/Documents/git/local/agent-tools/pulpie/.venv`)
- **Package Source**: `src/` (root module: `pulpie_service`)
- **Engine**: EuroBERT encoder model (`feyninc/pulpie-orange-small`, ~210M parameters, ~413 MB VRAM on GPU / runs on CPU)
- **MCP Server**: Stdio MCP server implemented in `pulpie_service.mcp_server`

---

## Verification & Development Commands

Always run commands using the project virtualenv and `PYTHONPATH=src`:

```bash
# Run full automated test suite (unit + integration tests)
PYTHONPATH=src .venv/bin/pytest tests/ -v

# Run smoke test on a sample HTML document
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --sample

# Check service status, model load state, and GPU allocations
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --status

# Run full performance benchmark across diverse corpora
PYTHONPATH=src .venv/bin/python scripts/benchmark.py

# Pre-cache / download model weights from Hugging Face
PYTHONPATH=src .venv/bin/python scripts/download_model.py
```

---

## MCP Server Tools

When running as an MCP server, Pulpie provides the following tools:

1. **`clean_html`**:
   - Parameters:
     - `html: str` (required): Raw HTML content to clean.
     - `output_format: "markdown" | "html"` (optional, default: `"markdown"`): Output representation format.
     - `fallback: bool` (optional, default: `true`): Whether to fall back to heuristic extraction if neural processing encounters an issue.
   - Returns: Cleaned markdown/HTML, block counts, character counts, token estimates, token savings percentage, latency, and status.

2. **`clean_web_page`**:
   - Parameters:
     - `url: str` (required): Target web page URL to fetch and clean.
     - `output_format: "markdown" | "html"` (optional, default: `"markdown"`).
     - `timeout_seconds: float` (optional, default: `15.0`).
   - Returns: Cleaned content and extraction statistics in one call.

3. **`pulpie_status`**:
   - Parameters: None.
   - Returns: Model load state, device (`cuda`/`cpu`), and VRAM usage.

4. **`pulpie_preload`**:
   - Parameters: None.
   - Returns: Forces weights into memory to avoid first-call latency.

---

## Agent Guidelines & Fallback Handling

- **When to Preprocess**: Always clean raw HTML from web fetches, browser pages, or documentation sites before feeding it to downstream reasoning models or context windows to eliminate up to 80%+ token noise.
- **Graceful Degradation**: Pulpie never crashes web flows or silently produces empty output. If the neural model is offline or encounters CUDA OOM, the service automatically falls back to Trafilatura or BeautifulSoup heuristic extraction.
- **Observability**: Check `status.used_fallback` and `status.fallback_reason` in tool responses when troubleshooting extraction behavior.
- **Code Standards**: Preserve type annotations, maintain existing test coverage, and test with both fallback and neural modes.
