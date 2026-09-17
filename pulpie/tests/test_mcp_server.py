"""Tests for Pulpie MCP server endpoints."""

import json
import pytest
from pulpie_service.mcp_server import make_mcp_server, get_service


@pytest.mark.asyncio
async def test_mcp_server_tools_registered():
    mcp = make_mcp_server()
    # List registered tool names
    tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
    assert "clean_html" in tool_names
    assert "clean_web_page" in tool_names
    assert "pulpie_status" in tool_names
    assert "pulpie_preload" in tool_names


@pytest.mark.asyncio
async def test_mcp_pulpie_status():
    mcp = make_mcp_server()
    # Call pulpie_status tool directly through manager
    tool = mcp._tool_manager.get_tool("pulpie_status")
    assert tool is not None
    res_str = await tool.fn()
    data = json.loads(res_str)
    assert data["service"] == "pulpie-preprocessing"
    assert "model_configured" in data
    assert "device" in data or data.get("error") is not None


@pytest.mark.asyncio
async def test_mcp_clean_html():
    mcp = make_mcp_server()
    tool = mcp._tool_manager.get_tool("clean_html")
    assert tool is not None
    sample_html = "<html><body><h1>Test Title</h1><p>Test content body</p></body></html>"
    res_str = await tool.fn(html=sample_html, output_format="markdown", fallback=True)
    data = json.loads(res_str)
    assert "content" in data
    assert "stats" in data
    assert "status" in data
    assert "Test Title" in data["content"] or "Test content body" in data["content"]
