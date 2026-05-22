"""Unit tests for sap_keepalive_start/stop session parameter routing.

Regression tests for issue #703: previously the tools had no session parameter,
causing a race condition in parallel multi-agent setups where one agent could stop
the keepalive of another. These tests verify that the session and agent_id params
are forwarded to get_backend correctly.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock, patch

import pytest

_PATCH_GET_BACKEND = "sapguimcp.tools.sap_tools.get_backend"


def _make_mock_backend() -> AsyncMock:
    backend = AsyncMock()
    backend.start_keepalive.return_value = None
    backend.stop_keepalive.return_value = True
    return backend


@pytest.fixture
async def start_fn() -> Callable[..., Any]:
    from sapguimcp.server import mcp

    tool = await mcp.get_tool("sap_keepalive_start")
    return tool.fn


@pytest.fixture
async def stop_fn() -> Callable[..., Any]:
    from sapguimcp.server import mcp

    tool = await mcp.get_tool("sap_keepalive_stop")
    return tool.fn


class TestKeepaliveSessionParam:
    """sap_keepalive_start/stop forward session and agent_id to get_backend."""

    @pytest.mark.anyio
    async def test_start_forwards_session_id(self, start_fn) -> None:
        """session='s2' must be forwarded to get_backend."""
        backend = _make_mock_backend()
        mock_get_backend = AsyncMock(return_value=backend)

        with patch(_PATCH_GET_BACKEND, new=mock_get_backend):
            await start_fn(session="s2", interval_seconds=300, agent_id=None)

        mock_get_backend.assert_called_once_with(session="s2", agent_id=None, tool_name="sap_keepalive_start")
        backend.start_keepalive.assert_called_once()

    @pytest.mark.anyio
    async def test_stop_forwards_session_id(self, stop_fn) -> None:
        """session='s2' must be forwarded to get_backend on stop."""
        backend = _make_mock_backend()
        mock_get_backend = AsyncMock(return_value=backend)

        with patch(_PATCH_GET_BACKEND, new=mock_get_backend):
            await stop_fn(session="s2", agent_id=None)

        mock_get_backend.assert_called_once_with(session="s2", agent_id=None, tool_name="sap_keepalive_stop")
        backend.stop_keepalive.assert_called_once()

    @pytest.mark.anyio
    async def test_start_none_session_passes_none(self, start_fn) -> None:
        """Omitting session defaults to None (primary session routing)."""
        backend = _make_mock_backend()
        mock_get_backend = AsyncMock(return_value=backend)

        with patch(_PATCH_GET_BACKEND, new=mock_get_backend):
            await start_fn(session=None, interval_seconds=300, agent_id=None)

        mock_get_backend.assert_called_once_with(session=None, agent_id=None, tool_name="sap_keepalive_start")

    @pytest.mark.anyio
    async def test_start_unknown_session_returns_error_result(self, start_fn) -> None:
        """An unknown session_id must return a structured error, not raise."""
        mock_get_backend = AsyncMock(side_effect=ValueError("Session 's99' not found"))

        with patch(_PATCH_GET_BACKEND, new=mock_get_backend):
            result = await start_fn(session="s99", interval_seconds=300, agent_id=None)

        assert result.success is False
        assert result.running is False
        assert "s99" in result.error

    @pytest.mark.anyio
    async def test_stop_unknown_session_returns_error_result(self, stop_fn) -> None:
        """An unknown session_id on stop must return a structured error, not raise."""
        mock_get_backend = AsyncMock(side_effect=ValueError("Session 's99' not found"))

        with patch(_PATCH_GET_BACKEND, new=mock_get_backend):
            result = await stop_fn(session="s99", agent_id=None)

        assert result.success is False
        assert result.running is False
        assert "s99" in result.error

    @pytest.mark.anyio
    async def test_start_forwards_agent_id(self, start_fn) -> None:
        """agent_id is forwarded alongside session."""
        backend = _make_mock_backend()
        mock_get_backend = AsyncMock(return_value=backend)

        with patch(_PATCH_GET_BACKEND, new=mock_get_backend):
            await start_fn(session="s1", interval_seconds=300, agent_id="agent-42")

        mock_get_backend.assert_called_once_with(session="s1", agent_id="agent-42", tool_name="sap_keepalive_start")
