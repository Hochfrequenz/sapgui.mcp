"""Integration tests for sap_run_script against a live SAP GUI session.

These tests call the MCP tool endpoint directly (not _run_in_sandbox) so the
full execution path is exercised: early compile → backend gate → COM thread →
sandbox. get_backend is patched to return the live backend fixture so no
network/session-lookup side-effects occur.
"""

import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

from sapguimcp.tools.script_tools import register_script_tools
from unittests.desktop.conftest import skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def _make_tool_fn(mcp: FastMCP):
    return mcp._local_provider._components["tool:sap_run_script@"].fn


@skip_no_sap
@pytest.mark.anyio
async def test_script_reads_window_title(backend):
    """Script reads the main window title via the full MCP tool path."""
    mcp = FastMCP("test")
    register_script_tools(mcp)
    tool_fn = _make_tool_fn(mcp)

    with patch("sapguimcp.tools.script_tools.get_backend", AsyncMock(return_value=backend)):
        result = await tool_fn(
            script='output(session.find_by_id("wnd[0]").text)',
            session=None,
            agent_id=None,
        )

    assert result.success, f"Failed: {result.error}"
    assert len(result.output) == 1
    title = result.output[0]
    assert isinstance(title, str)
    assert title.strip(), "Window title should not be blank"
    assert "SAP" in title, f"Expected SAP in window title, got: {title!r}"


@skip_no_sap
@pytest.mark.anyio
async def test_script_loop_collects_multiple_outputs(backend):
    """Script calls output(i) for i in range(3) — collects [0, 1, 2]."""
    mcp = FastMCP("test")
    register_script_tools(mcp)
    tool_fn = _make_tool_fn(mcp)

    with patch("sapguimcp.tools.script_tools.get_backend", AsyncMock(return_value=backend)):
        result = await tool_fn(
            script="for i in range(3):\n    output(i)",
            session=None,
            agent_id=None,
        )

    assert result.success, f"Failed: {result.error}"
    assert result.output == [0, 1, 2]


@skip_no_sap
@pytest.mark.anyio
async def test_script_conditional_branching(backend):
    """Script branches on a known condition — verifies both the decision and the value."""
    script = (
        'title = session.find_by_id("wnd[0]").text\n'
        'if "SAP" in title:\n'
        "    output(title)\n"
        "else:\n"
        '    output("no_sap_in_title")\n'
    )
    mcp = FastMCP("test")
    register_script_tools(mcp)
    tool_fn = _make_tool_fn(mcp)

    with patch("sapguimcp.tools.script_tools.get_backend", AsyncMock(return_value=backend)):
        result = await tool_fn(script=script, session=None, agent_id=None)

    assert result.success, f"Failed: {result.error}"
    assert len(result.output) == 1
    assert "SAP" in result.output[0], f"Expected SAP branch, got: {result.output[0]!r}"


@skip_no_sap
@pytest.mark.anyio
async def test_script_runtime_error_preserves_partial_output(backend):
    """Partial output collected before an error is preserved in the result."""
    mcp = FastMCP("test")
    register_script_tools(mcp)
    tool_fn = _make_tool_fn(mcp)

    with patch("sapguimcp.tools.script_tools.get_backend", AsyncMock(return_value=backend)):
        result = await tool_fn(
            script='output("before")\nraise ValueError("intentional")',
            session=None,
            agent_id=None,
        )

    assert not result.success
    assert result.error is not None
    assert "ValueError" in result.error
    assert result.output == ["before"]


@skip_no_sap
@pytest.mark.anyio
async def test_script_import_raises_name_error_not_import_error(backend):
    """import is blocked and must surface as NameError (core security contract)."""
    mcp = FastMCP("test")
    register_script_tools(mcp)
    tool_fn = _make_tool_fn(mcp)

    with patch("sapguimcp.tools.script_tools.get_backend", AsyncMock(return_value=backend)):
        result = await tool_fn(script="import os", session=None, agent_id=None)

    assert not result.success
    assert result.error is not None
    assert result.error.startswith("NameError"), f"Expected NameError, got: {result.error}"


@skip_no_sap
@pytest.mark.anyio
async def test_script_empty_output_succeeds(backend):
    """An empty script completes successfully with an empty output list."""
    mcp = FastMCP("test")
    register_script_tools(mcp)
    tool_fn = _make_tool_fn(mcp)

    with patch("sapguimcp.tools.script_tools.get_backend", AsyncMock(return_value=backend)):
        result = await tool_fn(script="", session=None, agent_id=None)

    assert result.success, f"Failed: {result.error}"
    assert result.output == []
