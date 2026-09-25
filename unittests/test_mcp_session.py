"""Tests for protocol-era aware MCP session identification."""

from types import SimpleNamespace

import pytest
from fastmcp import Client

from sapguimcp.mcp_session import get_mcp_session_id, is_modern_connection
from sapguimcp.middleware.logging import _sessions_ref
from sapguimcp.server import mcp


def _ctx(protocol_version: str, session_id: str) -> SimpleNamespace:
    return SimpleNamespace(request_context=SimpleNamespace(protocol_version=protocol_version), session_id=session_id)


def test_no_context_has_no_session():
    assert get_mcp_session_id(None) is None


def test_handshake_era_uses_the_mcp_session_id():
    ctx = _ctx("2025-11-25", "abc")
    assert not is_modern_connection(ctx)
    assert get_mcp_session_id(ctx) == "abc"


def test_2026_07_28_uses_one_id_for_the_whole_process():
    """fastmcp mints a new ctx.session_id per request on 2026-07-28 connections; it must not be used."""
    first, second = _ctx("2026-07-28", "per-request-1"), _ctx("2026-07-28", "per-request-2")
    assert is_modern_connection(first)
    assert get_mcp_session_id(first) == get_mcp_session_id(second)
    assert get_mcp_session_id(first) not in ("per-request-1", "per-request-2")


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["legacy", "2026-07-28"])
async def test_tool_calls_share_one_logging_session(mode):
    """Repeated calls from one client must accumulate in one SessionStats, not one per call."""
    _sessions_ref.clear()
    async with Client(mcp, mode=mode) as client:
        for _ in range(3):
            await client.call_tool("search_tables", {"query": "TSTC"})
    assert len(_sessions_ref) == 1
    assert next(iter(_sessions_ref.values())).call_count == 3
