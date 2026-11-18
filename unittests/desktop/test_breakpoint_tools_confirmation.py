"""Unit tests for the elicitation-based confirmation gate on sap_breakpoint_set.

Uses a real DesktopBackend instance (with a fake COM thread that just runs the
passed callable inline) so `isinstance(backend, DesktopBackend)` and the
`backend_type` property behave exactly as in production, without touching real
SAP GUI COM objects.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.breakpoint_models import BreakpointSetResult
from sapguimcp.server import mcp

_PATCH_GET_BACKEND = "sapguimcp.tools.breakpoint_tools.get_backend"
_ARGS = {"object_type": "PROG", "object_name": "Z_TICTACTOE", "line_number": 250}


class _FakeComThread:
    """Runs the callable passed to backend.com.run() inline, synchronously."""

    async def run(self, fn):
        return fn()


def _make_desktop_backend() -> DesktopBackend:
    backend = DesktopBackend(com_thread=_FakeComThread())
    backend.require_session = lambda: object()  # never dereferenced when patches below are in place
    return backend


def _parse_result(raw) -> dict:
    return json.loads(raw.content[0].text)


@pytest.fixture(params=["legacy", "2026-07-28"])
def client_mode(request) -> str:
    """Run each test over a handshake-era connection (the server confirms via
    ctx.elicit()) and a 2026-07-28 connection (the server confirms by returning
    an InputRequiredResult, SEP-2322)."""
    return request.param


def _patches(backend):
    """Common patches: real navigation/COM steps replaced with stand-ins so only
    the confirmation gate itself is under test."""
    return (
        patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        patch("sapguimcp.tools.breakpoint_tools._navigate_to_editor", new=AsyncMock(return_value=None)),
        patch("sapguimcp.tools.breakpoint_tools._resolve_line_number", new=AsyncMock(return_value=(250, None))),
        patch(
            "sapguimcp.tools.breakpoint_tools._resolve_shell_path_com", return_value="usr/cntlEDITOR/shellcont/shell"
        ),
        patch(
            "sapguimcp.tools.breakpoint_tools._toggle_breakpoint_com", return_value=(True, "Breakpoint wurde gesetzt")
        ),
    )


@pytest.mark.anyio
async def test_breakpoint_set_aborts_on_decline(client_mode):
    backend = _make_desktop_backend()

    async def decline_handler(message, response_type, params, context):
        assert "Z_TICTACTOE" in message
        assert "250" in message
        return ElicitResult(action="decline")

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=decline_handler, mode=client_mode) as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is False
    assert "aborted" in data["error"].lower()
    mock_toggle.assert_not_called()


@pytest.mark.anyio
async def test_breakpoint_set_aborts_on_confirm_false(client_mode):
    backend = _make_desktop_backend()

    async def decline_via_false(message, response_type, params, context):
        return False

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=decline_via_false, mode=client_mode) as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is False
    assert "aborted" in data["error"].lower()
    mock_toggle.assert_not_called()


@pytest.mark.anyio
async def test_breakpoint_set_proceeds_on_accept(client_mode):
    backend = _make_desktop_backend()

    async def accept_handler(message, response_type, params, context):
        return True

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=accept_handler, mode=client_mode) as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is True
    assert data["line_number"] == 250
    assert data["confirmation_skipped"] is False
    mock_toggle.assert_called_once()


@pytest.mark.anyio
async def test_breakpoint_set_proceeds_when_client_lacks_elicitation(client_mode):
    """Fail-open: a client with no elicitation_handler must not block the tool,
    but the result must record that confirmation was skipped."""
    backend = _make_desktop_backend()

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, mode=client_mode) as client:  # no elicitation_handler configured
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is True
    assert data["confirmation_skipped"] is True
    mock_toggle.assert_called_once()


@pytest.mark.anyio
async def test_breakpoint_set_uses_input_required_on_2026_07_28():
    """On a 2026-07-28 connection the tool asks via InputRequiredResult: it runs twice
    (ask, then re-call with the answer) and never falls back to ctx.elicit()."""
    backend = _make_desktop_backend()

    async def accept_handler(message, response_type, params, context):
        return True

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav as mock_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=accept_handler, mode="2026-07-28") as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    assert _parse_result(raw)["success"] is True
    assert mock_nav.await_count == 2
    mock_toggle.assert_called_once()


@pytest.mark.anyio
async def test_breakpoint_set_reasks_when_line_changes_between_rounds():
    """A yes given for line 250 must not set a breakpoint on line 251."""
    backend = _make_desktop_backend()
    asked = []

    async def accept_handler(message, response_type, params, context):
        asked.append(message)
        return True

    p_backend, p_nav, _, p_shell, p_toggle = _patches(backend)
    p_line = patch(
        "sapguimcp.tools.breakpoint_tools._resolve_line_number",
        new=AsyncMock(side_effect=[(250, None), (251, None), (251, None)]),
    )
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=accept_handler, mode="2026-07-28") as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert len(asked) == 2
    assert "251" in asked[1]
    assert data["line_number"] == 251
    mock_toggle.assert_called_once()


@pytest.mark.anyio
async def test_breakpoint_set_output_schema_excludes_input_required():
    """The InputRequiredResult arm of the return type must not leak into outputSchema."""
    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    schema_properties = set(tools["sap_breakpoint_set"].output_schema["properties"])
    assert set(BreakpointSetResult.model_json_schema()["properties"]) == schema_properties
