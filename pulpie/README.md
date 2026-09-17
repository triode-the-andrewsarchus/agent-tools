# Pulpie Web Preprocessing Service for Antigravity & Codex

A specialized local preprocessing service and Model Context Protocol (MCP) server that sits between web fetching (search, HTTP, browser) and downstream LLM reasoning workers (Antigravity, Codex CLI, and the Codex IDE extension).

Powered by **Pulpie Orange Small** (`feyninc/pulpie-orange-small`, 210M parameters), Pulpie strips web boilerplate (navigation headers, sidebars, advertisements, cookie banners, tracking scripts, and footers) while preserving essential document semantics: headings, paragraphs, lists, tables, code blocks, links, and mathematical formulas.

---

## Why Pulpie?

1. **Massive Token Savings**:
   Raw HTML typically contains 60–85% boilerplate noise. In our benchmarks, Pulpie achieves **61.6% average token reduction** across diverse web pages (and **80.5% reduction** on navigation-heavy pages).
2. **Structure Preservation**:
   Unlike simple heuristic tag strippers that destroy tables or corrupt code snippets, Pulpie's EuroBERT encoder model labels DOM blocks in parallel, ensuring tables, LaTeX/math expressions, and code syntax blocks remain intact.
3. **High Throughput & Low Latency**:
   As an encoder model (single forward pass), Pulpie does not generate autoregressive tokens. It extracts content in **~10–25 ms per page** on GPU (**>60 pages/sec throughput**).
4. **Lightweight & Independent**:
   Consumes only **~413 MB VRAM** on GPU (or runs on CPU). It is completely decoupled from LM Studio reasoning workers and does not consume worker slots or trigger model unloads.

---

## Architectural Position

```
       [Web / Search / Browser Fetcher]
                       │
                       ▼ (Raw HTML)
     ┌────────────────────────────────────┐
     │         Pulpie MCP Service         │
     │  - simplify DOM (MinerU tagging)   │
     │  - pack chunks (8,192 tokens)      │
     │  - encode & classify (Orange Small)│
     │  - fallback to Trafilatura/Soup    │
     └─────────────────┬──────────────────┘
                       │
                       ▼ (Clean Semantic Markdown)
     [Antigravity / Codex / Local LLMs / RAG]
```

---

## Installation & Setup

### 1. Prerequisites
- Python >= 3.12
- NVIDIA GPU with CUDA (recommended, ~420 MB free VRAM) or CPU
- `uv` package manager (or standard `python -m venv`)

### 2. Create Virtual Environment & Install
```bash
cd /home/vega/Documents/git/local/antigravity_with_pulpie
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e . ".[dev]"
```

### 3. Preload / Download Model Weights
```bash
PYTHONPATH=src .venv/bin/python scripts/download_model.py
```
This pre-caches `feyninc/pulpie-orange-small` (~423 MB safetensors) into standard Hugging Face cache (`~/.cache/huggingface/hub`).

---

## Assistant Integrations

Pulpie works seamlessly across both **Google Antigravity** and **OpenAI Codex** (CLI and IDE extension).

### 1. OpenAI Codex Integration (CLI & IDE Extension)

#### A. Register MCP Server via Codex CLI
Run the following one-line command to register Pulpie globally in Codex:
```bash
codex mcp add pulpie \
  --env PYTHONPATH=/home/vega/Documents/git/local/antigravity_with_pulpie/src \
  -- /home/vega/Documents/git/local/antigravity_with_pulpie/.venv/bin/python -m pulpie_service.mcp_server
```

#### B. Manual Config (`~/.codex/config.toml` or Project `.codex/config.toml`)
Alternatively, add the server definition directly to your TOML config:
```toml
[mcp_servers.pulpie]
command = "/home/vega/Documents/git/local/antigravity_with_pulpie/.venv/bin/python"
args = ["-m", "pulpie_service.mcp_server"]

[mcp_servers.pulpie.env]
PYTHONPATH = "/home/vega/Documents/git/local/antigravity_with_pulpie/src"
```

#### C. Global Skill Symlink
Link the Pulpie extractor skill so Codex can discover and reference it:
```bash
ln -sfn /home/vega/Documents/git/local/antigravity_with_pulpie/.agents/skills/pulpie-extractor ~/.codex/skills/pulpie-extractor
```

#### D. Global Agent Guidance (`~/.codex/AGENTS.md`)
Add preprocessing instructions to your global Codex agent guidance file (`~/.codex/AGENTS.md`):
```markdown
## Web Content Preprocessing with Pulpie
When fetching raw HTML or reading web pages that contain navigation headers, sidebars, advertisements, cookie banners, tracking scripts, or footers, preprocess the content using `clean_html` or `clean_web_page` before feeding it to context or downstream analysis.
```

#### E. Using with the Codex IDE Extension
- The Codex VS Code extension automatically picks up MCP servers configured in `~/.codex/config.toml`.
- When interacting with the agent in the IDE sidebar or composer, Pulpie's tools (`clean_html`, `clean_web_page`, `pulpie_status`, `pulpie_preload`) are available.
- Check and verify your Codex MCP status anytime:
  ```bash
  codex mcp list
  codex mcp get pulpie
  ```

---

### 2. Antigravity Integration

#### MCP Server Registration (`~/.gemini/config/mcp_config.json`)
```json
{
  "mcpServers": {
    "pulpie": {
      "command": "/home/vega/Documents/git/local/antigravity_with_pulpie/.venv/bin/python",
      "args": ["-m", "pulpie_service.mcp_server"],
      "env": {
        "PYTHONPATH": "/home/vega/Documents/git/local/antigravity_with_pulpie/src"
      }
    }
  }
}
```

#### Global Skills & Rules Symlinks
```bash
# Skill reference
ln -sfn /home/vega/Documents/git/local/antigravity_with_pulpie/.agents/skills/pulpie-extractor ~/.gemini/config/skills/pulpie-extractor

# Preprocessing policy rule
ln -sfn /home/vega/Documents/git/local/antigravity_with_pulpie/.agents/rules/pulpie_preprocessing.md ~/.gemini/config/rules/pulpie_preprocessing.md
```

---

## Agent Tools & Interface

| Tool | Parameters | Description |
|---|---|---|
| `clean_html` | `html: str`, `output_format: "markdown" \| "html"`, `fallback: bool = True` | Cleans raw HTML string. Returns cleaned content, block counts, compression ratio, token savings, and latency. |
| `clean_web_page` | `url: str`, `output_format: "markdown" \| "html"`, `timeout_seconds: float = 15.0` | Convenience tool to fetch a URL and return cleaned content in one call. |
| `pulpie_status` | *(none)* | Returns service health, model loaded status, device (`cuda`/`cpu`), and VRAM allocations. |
| `pulpie_preload` | *(none)* | Forces model weight loading into memory to warm up the engine. |

### Example Tool Invocation

#### `clean_html`
```json
{
  "html": "<!DOCTYPE html><html><body><nav>Menu</nav><h1>Guide</h1><p>Main content...</p><footer>Footer</footer></body></html>",
  "output_format": "markdown"
}
```

#### Output
```json
{
  "title": "Guide",
  "format": "markdown",
  "content": "# Guide\n\nMain content...",
  "stats": {
    "blocks_total": 4,
    "blocks_main": 2,
    "blocks_other": 2,
    "char_count_in": 115,
    "char_count_out": 24,
    "compression_ratio": 0.208,
    "token_estimate_in": 28,
    "token_estimate_out": 6,
    "token_savings_pct": 78.5,
    "latency_ms": 11.4
  },
  "status": {
    "used_fallback": false,
    "fallback_reason": null,
    "model_used": "orange-small",
    "device": "cuda"
  }
}
```

---

## Graceful Fallback Behavior

Pulpie is engineered to **never** crash web processing or silently return empty strings:
1. **Model Unavailable / First Run**: If weights are missing or offline, the service immediately routes to **Trafilatura** (or BeautifulSoup + html2text).
2. **CUDA Out-of-Memory**: Automatically falls back to CPU execution or heuristic extraction without interrupting the agent.
3. **Empty / Suspicious Pruning**: If Pulpie labels all blocks as boilerplate on a page with non-trivial text, fallback extraction triggers automatically.
4. **Observability**: Tool responses explicitly include `status.used_fallback` and `status.fallback_reason`.

---

## Resource Usage & Performance

Benchmarked on **NVIDIA GeForce RTX 3090** (CUDA 13):

| Metric | Measured Value |
|---|---|
| **VRAM Footprint** | **412.8 MB** allocated (~430 MB reserved) |
| **Cold Start Time** | ~3.5 s (model weights load into VRAM) |
| **Mean Extraction Latency** | **16.09 ms** per page |
| **Single-Stream Throughput** | **62.1 pages / second** |
| **Average Token Reduction** | **61.6%** (up to 80.5% on noisy portals) |

### Benchmark Corpus Results (6 Diverse Page Types)

| Page Type | Raw Size | Clean Size | Compression | Token Savings | Blocks Kept | Latency |
|---|---|---|---|---|---|---|
| `navigation_heavy.html` | 4,591 chars | 898 chars | 19.6% | **80.5%** | 6 / 23 | 15.46 ms |
| `adversarial.html` | 683 chars | 279 chars | 40.8% | **59.4%** | 6 / 7 | 18.14 ms |
| `documentation_page.html` | 3,011 chars | 1,317 chars | 43.7% | **56.2%** | 9 / 12 | 27.68 ms |
| `normal_article.html` | 2,710 chars | 1,196 chars | 44.1% | **55.8%** | 8 / 16 | 11.43 ms |
| `table_math.html` | 3,086 chars | 1,480 chars | 48.0% | **52.0%** | 12 / 15 | 14.22 ms |
| `github_code.html` | 2,304 chars | 1,117 chars | 48.5% | **51.6%** | 1 / 6 | 9.63 ms |

---

## Verification & Testing

```bash
# Run full automated test suite (14 unit & integration tests)
PYTHONPATH=src .venv/bin/pytest tests/ -v

# Run interactive smoke test against sample HTML
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --sample

# Check service and GPU status
PYTHONPATH=src .venv/bin/python scripts/smoke_test.py --status

# Run full performance benchmark suite
PYTHONPATH=src .venv/bin/python scripts/benchmark.py
```
