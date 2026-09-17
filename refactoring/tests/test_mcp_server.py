"""Tests for MCP server tool endpoints."""

import json
import pytest

from architecture_fitness.mcp_server import make_mcp_server


@pytest.mark.asyncio
async def test_mcp_tools(git_repo):
    server = make_mcp_server()

    # Verify tool registrations
    tool_names = [t.name for t in server._tool_manager._tools.values()]
    assert "architecture_baseline" in tool_names
    assert "architecture_measure" in tool_names
    assert "architecture_compare" in tool_names
    assert "architecture_hotspots" in tool_names
    assert "architecture_reuse_candidates" in tool_names

    # 1. architecture_baseline
    res_base = await server.call_tool("architecture_baseline", {"repo_path": str(git_repo), "name": "mcp-test-base"})
    base_data = json.loads(res_base.content[0].text)
    assert base_data["status"] == "BASELINE_CREATED"
    assert base_data["baseline_id"] == "mcp-test-base"

    # 2. architecture_measure
    res_measure = await server.call_tool("architecture_measure", {"repo_path": str(git_repo)})
    measure_data = json.loads(res_measure.content[0].text)
    assert "vector" in measure_data
    assert measure_data["vector"]["files_count"] >= 1

    # 3. architecture_compare
    res_compare = await server.call_tool("architecture_compare", {"repo_path": str(git_repo), "baseline_name": "mcp-test-base"})
    compare_data = json.loads(res_compare.content[0].text)
    assert "summary" in compare_data
    assert compare_data["classification"] == "NEUTRAL"

    # 4. architecture_hotspots
    res_hotspots = await server.call_tool("architecture_hotspots", {"repo_path": str(git_repo), "top_n": 5})
    hotspots_data = json.loads(res_hotspots.content[0].text)
    assert isinstance(hotspots_data, list)

    # 5. architecture_reuse_candidates
    res_reuse = await server.call_tool("architecture_reuse_candidates", {"repo_path": str(git_repo), "query": "hello greeting"})
    reuse_data = json.loads(res_reuse.content[0].text)
    assert "candidates" in reuse_data
    assert any("hello" in c["symbol_name"] for c in reuse_data["candidates"])
