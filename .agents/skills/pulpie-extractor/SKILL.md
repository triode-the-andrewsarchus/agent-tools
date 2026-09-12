---
name: pulpie-extractor
description: Fast local web-content extraction and preprocessing tool using Pulpie. Cleans raw HTML to eliminate boilerplate (menus, sidebars, footers, ads) while strictly preserving headings, tables, code blocks, math formulas, and document hierarchy.
---

# Pulpie Web-Content Extractor — Quick Reference

Pulpie is a specialized **local preprocessing service** (210M EuroBERT encoder) that sits between web fetching and downstream LLM analysis/reasoning. It removes up to 80%+ of HTML token junk in milliseconds while preserving critical document structure.

## When to Use Pulpie

**Always use Pulpie when:**
- A fetched web page contains navigation menus, sidebars, cookie banners, ads, or footers.
- Raw HTML needs to be converted into high-density semantic Markdown for LLM context or RAG.
- Preserving tables, code blocks, links, and math formulas is essential.
- Context window efficiency matters (especially before passing to local or external LLMs).

**Do NOT use Pulpie when:**
- The content is already clean Markdown or plain text.
- Tiny/minimal pages where extraction adds no value (< 300 characters).
- Raw HTML structure, CSS selectors, or full DOM tree itself is what is being debugged.

---

## MCP Tools

### 1. `clean_html`
Clean already-fetched raw HTML string.

```json
{
  "html": "<!DOCTYPE html><html>...</html>",
  "output_format": "markdown", // optional: "markdown" (default) or "html"
  "fallback": true             // optional: fallback to heuristic if model error
}
```

**Returns:**
```json
{
  "title": "Article or Page Title",
  "format": "markdown",
  "content": "# Clean Main Heading\n\nPreserved body paragraphs, tables, and code...",
  "stats": {
    "blocks_total": 45,
    "blocks_main": 14,
    "blocks_other": 31,
    "char_count_in": 32150,
    "char_count_out": 4210,
    "compression_ratio": 0.131,
    "token_estimate_in": 8037,
    "token_estimate_out": 1052,
    "token_savings_pct": 86.9,
    "latency_ms": 28.4
  },
  "status": {
    "used_fallback": false,
    "fallback_reason": null,
    "model_used": "orange-small",
    "device": "cuda:0"
  }
}
```

### 2. `clean_web_page`
Convenience tool that fetches a URL and extracts clean content in one step.

```json
{
  "url": "https://example.com/blog/article",
  "output_format": "markdown",
  "timeout_seconds": 15.0
}
```

### 3. `pulpie_status`
Check service health, GPU memory allocation, and model status.
Pulpie runs on GPU (~420 MB VRAM) or CPU independently of local LLM reasoning workers.

### 4. `pulpie_preload`
Preload model weights into GPU/CPU memory to eliminate first-request cold-start latency.

---

## Recommended Workflow

```
Fetch Web Page (read_url_content / clean_web_page)
                  ↓
          Pulpie Preprocessing
  (Boilerplate stripped, tables & code preserved)
                  ↓
       Clean Semantic Markdown
                  ↓
   Agent Analysis / Local Worker / Reasoning
```

## Graceful Fallback & Observability
- If the neural model is loading or encounters an issue, Pulpie automatically falls back to Trafilatura or BeautifulSoup heuristic extraction.
- Check `status.used_fallback`: if `true`, check `status.fallback_reason` for diagnostics.
- Content is **never** silently dropped.
