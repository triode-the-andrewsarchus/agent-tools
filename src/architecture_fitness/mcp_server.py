"""MCP Server exposing Architecture Fitness tools."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Annotated, Any, List, Optional

from mcp.server.mcpserver import MCPServer

from .service import ArchitectureFitnessService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

_service: Optional[ArchitectureFitnessService] = None


def get_service() -> ArchitectureFitnessService:
    global _service
    if _service is None:
        _service = ArchitectureFitnessService()
    return _service


def _fmt(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def make_mcp_server() -> MCPServer:
    mcp = MCPServer(
        name="architecture_fitness",
        version="0.1.0",
        instructions=(
            "Architecture Fitness is a local, multidimensional measurement and feedback system "
            "designed to prevent unnecessary architectural growth, code duplication, and complexity regressions. "
            "It integrates Lizard (cyclomatic complexity), jscpd (copy/paste detection), and Valknut (architecture/coupling). "
            "Always inspect existing architecture and search reuse candidates before introducing new mechanisms."
        ),
    )

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="architecture_baseline",
        description=(
            "Establish or retrieve an architecture baseline for the current repository. "
            "Records git commit, tool versions, normalized complexity/duplication vector, and file index. "
            "Stored in repository-local .fitness/baselines/ directory."
        ),
    )
    async def architecture_baseline(
        repo_path: Annotated[str, "Absolute path to the repository root directory"],
        name: Annotated[Optional[str], "Optional friendly name for the baseline (e.g. 'feature-start' or 'pre-refactor')"] = None,
        profile: Annotated[Optional[str], "Performance profile: 'fast' (default), 'balanced', 'thorough'"] = "fast",
    ) -> str:
        svc = get_service()
        loop = asyncio.get_running_loop()
        record, report = await loop.run_in_executor(
            None, svc.create_baseline, repo_path, name, profile
        )
        
        vec = record.vector
        res = {
            "status": "BASELINE_CREATED",
            "baseline_id": record.id,
            "git_commit": record.git_commit,
            "timestamp": record.timestamp,
            "tool_versions": record.tool_versions,
            "summary": {
                "lines_of_code": vec.lines_of_code,
                "files_count": vec.files_count,
                "functions_count": vec.functions_count,
                "avg_cyclomatic_complexity": vec.avg_cyclomatic_complexity,
                "max_cyclomatic_complexity": vec.max_cyclomatic_complexity,
                "duplication_percentage": f"{vec.duplication_percentage:.2f}%",
                "clone_groups_count": vec.clone_groups_count,
                "overall_health_score": vec.overall_health_score,
            },
            "hotspots_identified": len(report.hotspots),
            "stored_file": f".fitness/baselines/{record.id}.json",
        }
        return _fmt(res)

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="architecture_measure",
        description=(
            "Run all relevant architecture measurements (Lizard, jscpd, Valknut) against the current working tree. "
            "Returns normalized multidimensional architecture vector, warnings, tool statuses, and identified hotspots. "
            "Clearly distinguishes measurements, warnings, and unavailable metrics."
        ),
    )
    async def architecture_measure(
        repo_path: Annotated[str, "Absolute path to the repository root directory"],
        target_paths: Annotated[Optional[List[str]], "Optional specific subdirectories or files to measure"] = None,
        profile: Annotated[Optional[str], "Performance profile: 'fast' (default), 'balanced', 'thorough'"] = "fast",
    ) -> str:
        svc = get_service()
        loop = asyncio.get_running_loop()
        report = await loop.run_in_executor(
            None, svc.measure, repo_path, target_paths, profile
        )
        return _fmt(report.model_dump())

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="architecture_compare",
        description=(
            "Compare the current working tree against a baseline (or HEAD). "
            "Produces a human- and agent-readable delta across LOC, functions, CCN, duplication %, "
            "clone groups, and structural metrics. Distinguishes newly introduced problems from existing debt."
        ),
    )
    async def architecture_compare(
        repo_path: Annotated[str, "Absolute path to the repository root directory"],
        baseline_name: Annotated[Optional[str], "Name or commit of baseline to compare against (defaults to HEAD/latest)"] = None,
        diff_aware: Annotated[bool, "Whether to correlate problems with git diff (default: True)"] = True,
        profile: Annotated[Optional[str], "Performance profile: 'fast' (default), 'balanced', 'thorough'"] = "fast",
    ) -> str:
        svc = get_service()
        loop = asyncio.get_running_loop()
        comp = await loop.run_in_executor(
            None, svc.compare, repo_path, baseline_name, diff_aware, profile
        )
        
        # Return structured output with summary header prominently at the top
        return _fmt({
            "summary": comp.summary_header,
            "classification": comp.classification.value,
            "diff_aware": comp.diff_aware,
            "affected_files": comp.affected_files,
            "new_problems": comp.new_problems,
            "resolved_problems": comp.resolved_problems,
            "suggested_action": comp.suggested_action,
            "metrics": {k: m.model_dump() for k, m in comp.vector_delta.metrics.items()},
        })

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="architecture_hotspots",
        description=(
            "Identify the portions of the codebase that are currently the most structurally problematic. "
            "Combines high cyclomatic complexity functions, high duplication clusters, and structural chokepoints."
        ),
    )
    async def architecture_hotspots(
        repo_path: Annotated[str, "Absolute path to the repository root directory"],
        top_n: Annotated[int, "Maximum number of hotspots to return (default: 10)"] = 10,
        criteria: Annotated[Optional[str], "Optional filter criteria ('complexity', 'duplication', 'cycle')"] = None,
        profile: Annotated[Optional[str], "Performance profile: 'fast' (default), 'balanced', 'thorough'"] = "fast",
    ) -> str:
        svc = get_service()
        loop = asyncio.get_running_loop()
        hotspots = await loop.run_in_executor(
            None, svc.hotspots, repo_path, top_n, criteria, profile
        )
        return _fmt([h.model_dump() for h in hotspots])

    # ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="architecture_reuse_candidates",
        description=(
            "Given a proposed new function/file/module or a description of functionality to add, "
            "search the repository for existing symbols, functions, or modules that may provide equivalent or related functionality. "
            "Returns CANDIDATES for the agent to inspect before adding new abstractions."
        ),
    )
    async def architecture_reuse_candidates(
        repo_path: Annotated[str, "Absolute path to the repository root directory"],
        query: Annotated[str, "Description of functionality or proposed symbol name to search for (e.g. 'calculate payment tax' or 'parse_url')"],
        context: Annotated[Optional[str], "Optional additional context such as expected parameters or related keywords"] = None,
        top_n: Annotated[int, "Maximum candidates to return (default: 5)"] = 5,
    ) -> str:
        svc = get_service()
        loop = asyncio.get_running_loop()
        candidates = await loop.run_in_executor(
            None, svc.reuse_candidates, repo_path, query, context, top_n
        )
        
        return _fmt({
            "disclaimer": "These are CANDIDATES discovered via symbol and AST indexing, not definitive recommendations. Investigate before adding new mechanisms.",
            "query": query,
            "candidates_count": len(candidates),
            "candidates": [c.model_dump() for c in candidates],
        })

    return mcp


async def async_main() -> None:
    log.info("Starting Architecture Fitness MCP server...")
    mcp = make_mcp_server()
    await mcp.run_stdio_async()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        svc = get_service()
        print("Architecture Fitness Service initialized successfully.")
        sys.exit(0)
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
