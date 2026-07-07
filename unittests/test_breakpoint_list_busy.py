"""Unit tests for sap_breakpoint_list's busy-session error classification.

Regression test for a review finding: the tool's docstring promises a
distinguishable "busy" report when a modal debugger blocks the SAP GUI
message loop, but nothing implemented that classification — callers got an
opaque raw COM exception string instead.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.server import mcp

_PATCH_GET_BACKEND = "sapguimcp.tools.breakpoint_tools.get_backend"
_ARGS = {"object_type": "PROG", "object_name": "Z_TICTACTOE"}
_RPC_E_CALL_REJECTED = -2147418111


class _FakeComThread:
    """Runs the callable passed to backend.com.run() inline, synchronously."""

    async def run(self, fn):
        return fn()


def _make_desktop_backend() -> DesktopBackend:
    backend = DesktopBackend(com_thread=_FakeComThread())
    backend.require_session = lambda: object()
    return backend


def _busy_com_error(message: str = "busy") -> Exception:
    """Build an exception carrying a 'server busy' COM hresult, as pywin32's com_error does."""
    exc = RuntimeError(message)
    exc.hresult = _RPC_E_CALL_REJECTED  # type: ignore[attr-defined]
    return exc


def _parse_result(raw) -> dict:
    return json.loads(raw.content[0].text)


@pytest.mark.anyio
async def test_breakpoint_list_reports_busy_distinctly():
    backend = _make_desktop_backend()

    with (
        patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        patch("sapguimcp.tools.breakpoint_tools._navigate_to_editor", new=AsyncMock(return_value=None)),
        patch("sapguimcp.tools.breakpoint_tools._open_bp_list_dialog_com", side_effect=_busy_com_error()),
    ):
        async with Client(mcp) as client:
            raw = await client.call_tool("sap_breakpoint_list", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is False
    assert "busy" in data["error"].lower()
    assert "dismiss" in data["error"].lower()


@pytest.mark.anyio
async def test_breakpoint_list_reports_generic_error_for_non_busy_exception():
    """A non-busy exception must still surface as a generic error, not misclassified as busy."""
    backend = _make_desktop_backend()

    with (
        patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        patch("sapguimcp.tools.breakpoint_tools._navigate_to_editor", new=AsyncMock(return_value=None)),
        patch("sapguimcp.tools.breakpoint_tools._open_bp_list_dialog_com", side_effect=RuntimeError("boom")),
    ):
        async with Client(mcp) as client:
            raw = await client.call_tool("sap_breakpoint_list", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is False
    assert "unexpected error" in data["error"].lower()
    assert "busy" not in data["error"].lower()
