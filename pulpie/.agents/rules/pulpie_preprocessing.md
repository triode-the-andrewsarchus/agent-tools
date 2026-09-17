# Web Content Preprocessing Policy — Pulpie Integration

You have access to a local content extraction capability via the `pulpie` MCP tools.

## Policy

1. **Preprocess Web Pages**:
   Whenever fetching raw HTML or navigating web content that contains headers, navigation links, ads, sidebars, or tracking noise, run it through `clean_html` or `clean_web_page` before passing the content into your context window or offloading to downstream local LLM workers.

2. **Independence from Reasoning Workers**:
   Pulpie is a lightweight 210M parameter neural encoder (~420 MB VRAM) running independently from LM Studio and local reasoning workers (`cheap` / `smart`). It can be invoked anytime without blocking or interrupting ongoing LLM reasoning tasks.

3. **Fallback Observability**:
   If `status.used_fallback` is true in a tool response, the service automatically degraded to heuristic parsing. You may proceed normally, but take note of `fallback_reason` if diagnosing web parsing issues.
