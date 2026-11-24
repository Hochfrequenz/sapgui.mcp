"""``sap_transaction`` / ``sap_press_key`` wait for the session to be idle, bounded by the former fixed wait (#928)."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.models import KeyboardResult, StatusBarInfo, TransactionResult
from sapguimcp.tools.sap_tools import register_sap_tools


def _backend(wait_for_ready: AsyncMock) -> MagicMock:
    backend = MagicMock()
    backend.check_popup = AsyncMock(return_value=None)
    backend.wait = AsyncMock()
    backend.wait_for_ready = wait_for_ready
    backend.enter_transaction = AsyncMock(return_value=TransactionResult(tcode="SE16", page_title="Data Browser"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="none", message=""))
    backend.press_key = AsyncMock(return_value=KeyboardResult(key="Enter", page_title="Data Browser"))
    return backend


async def _call(backend: MagicMock, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    server = FastMCP("t")
    register_sap_tools(server)
    with patch("sapguimcp.tools.sap_tools.get_backend", new=AsyncMock(return_value=backend)):
        async with Client(server) as client:
            raw = await client.call_tool(tool, args, raise_on_error=False)
    return json.loads(raw.content[0].text)  # type: ignore[no-any-return]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "args", "bound_ms"),
    [("sap_transaction", {"tcode": "SE16"}, 200), ("sap_press_key", {"key": "Enter"}, 300)],
)
async def test_waits_for_readiness_instead_of_a_fixed_time(tool: str, args: dict[str, Any], bound_ms: int) -> None:
    backend = _backend(AsyncMock())
    assert (await _call(backend, tool, args))["success"] is True
    backend.wait_for_ready.assert_awaited_once_with(timeout_ms=bound_ms)
    backend.wait.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "args"), [("sap_transaction", {"tcode": "SE16"}), ("sap_press_key", {"key": "Enter"})]
)
async def test_a_failing_readiness_poll_does_not_fail_the_step(tool: str, args: dict[str, Any]) -> None:
    backend = _backend(AsyncMock(side_effect=RuntimeError("COM call failed")))
    assert (await _call(backend, tool, args))["success"] is True
