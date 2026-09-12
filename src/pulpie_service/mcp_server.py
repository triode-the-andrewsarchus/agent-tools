"""MCP Server exposing Pulpie web-content extraction and preprocessing tools."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Annotated, Any, Optional

from mcp.server.mcpserver import MCPServer

from .config import PulpieConfig
from .extractor import PulpieService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

# Singleton service instance
_service: Optional[PulpieService] = None


def get_service() -> PulpieService:
    global _service
    if _service is None:
        _service = PulpieService()
    return _service


def _fmt(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def make_mcp_server() -> MCPServer:
    mcp = MCPServer(
        name="pulpie",
        version="0.1.0",
        instructions=(
            "Pulpie is a local web-content extraction and preprocessing service. "
            "It removes web boilerplate (navigation, headers, footers, ads) while preserving "
            "document structure (headings, tables, code blocks, math formulas, links). "
            "Use clean_html or clean_web_page before passing web content into downstream LLMs."
        ),
    )

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="clean_html",
        description=(
            "Clean raw HTML using Pulpie Orange Small. "
            "Removes headers, footers, navigation, sidebars, and ads while preserving "
            "headings, paragraphs, lists, tables, code blocks, links, and formulas. "
            "Returns clean semantic Markdown or HTML along with compression and token-saving metrics."
        ),
    )
    async def clean_html(
        html: Annotated[str, "Raw HTML string to clean"],
        output_format: Annotated[str, "Output format: 'markdown' (default) or 'html'"] = "markdown",
        fallback: Annotated[bool, "Whether to fall back to heuristic extraction on failure or empty output"] = True,
    ) -> str:
        svc = get_service()
        # Run synchronous extraction in thread pool to avoid blocking async event loop
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None, svc.clean_html, html, output_format, fallback
        )
        return _fmt(res.to_dict())

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="clean_web_page",
        description=(
            "Fetch a URL and clean its content using Pulpie. "
            "Convenience tool combining HTTP fetching with Pulpie preprocessing. "
            "Returns cleaned semantic Markdown with boilerplate removed and structured elements preserved."
        ),
    )
    async def clean_web_page(
        url: Annotated[str, "Web page URL to fetch and clean"],
        output_format: Annotated[str, "Output format: 'markdown' (default) or 'html'"] = "markdown",
        fallback: Annotated[bool, "Whether to fall back to heuristic extraction on failure"] = True,
        timeout_seconds: Annotated[float, "HTTP request timeout in seconds"] = 15.0,
    ) -> str:
        svc = get_service()
        res = await svc.clean_web_page(
            url=url,
            output_format=output_format,
            fallback=fallback,
            timeout=timeout_seconds,
        )
        data = res.to_dict()
        data["url"] = url
        return _fmt(data)

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="pulpie_status",
        description=(
            "Check Pulpie service health, model status, GPU VRAM usage, and availability. "
            "Pulpie runs independently from local LLM reasoning workers."
        ),
    )
    async def pulpie_status() -> str:
        svc = get_service()
        st = svc.status()
        return _fmt(st)

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="pulpie_preload",
        description=(
            "Explicitly preload the Pulpie model weights into memory (GPU or CPU) "
            "so subsequent extraction requests experience zero cold-start latency."
        ),
    )
    async def pulpie_preload() -> str:
        svc = get_service()
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, svc.preload)
        return _fmt(res)

    return mcp


async def async_main() -> None:
    log.info("Starting Pulpie MCP server...")
    mcp = make_mcp_server()
    await mcp.run_stdio_async()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Quick CLI verification mode
        svc = get_service()
        print("Status:", json.dumps(svc.status(), indent=2))
        sys.exit(0)
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
