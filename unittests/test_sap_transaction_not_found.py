"""``sap_transaction``: a transaction code that does not exist is a failure, not a success on the old screen."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.models import StatusBarInfo, TransactionResult
from sapguimcp.tools.sap_tools import register_sap_tools


async def _call(status: StatusBarInfo, backend_type: str = "desktop") -> dict[str, Any]:
    backend = MagicMock()
    backend.backend_type = backend_type
    backend.check_popup = AsyncMock(return_value=None)
    backend.wait = AsyncMock()
    backend.enter_transaction = AsyncMock(return_value=TransactionResult(tcode="NOSUCH1", page_title="SAP Easy Access"))
    backend.get_status_bar = AsyncMock(return_value=status)
    server = FastMCP("t")
    register_sap_tools(server)
    with patch("sapguimcp.tools.sap_tools.get_backend", new=AsyncMock(return_value=backend)):
        async with Client(server) as client:
            raw = await client.call_tool("sap_transaction", {"tcode": "NOSUCH1"}, raise_on_error=False)
    return json.loads(raw.content[0].text)  # type: ignore[no-any-return]


@pytest.mark.anyio
async def test_an_unknown_transaction_code_is_a_failure_with_the_status_bar_text() -> None:
    status = StatusBarInfo(
        type="S", message="Transaktion NOSUCH1 existiert nicht", message_id="S#", message_number="343"
    )
    data = await _call(status)
    assert data["success"] is False
    assert data["error"] == "Transaktion NOSUCH1 existiert nicht"


@pytest.mark.anyio
async def test_the_same_status_text_class_and_number_decide_not_the_language() -> None:
    status = StatusBarInfo(
        type="S", message="Transaction NOSUCH1 does not exist", message_id="S#", message_number="343"
    )
    assert (await _call(status))["success"] is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status",
    [
        StatusBarInfo(type="none", message=""),
        StatusBarInfo(type="S", message="Daten gesichert", message_id="00", message_number="344"),
        StatusBarInfo(type="E", message="Kein Eintrag gefunden", message_id="00", message_number="343"),
    ],
    ids=["empty", "other_success", "same_number_other_class"],
)
async def test_any_other_status_is_still_a_success(status: StatusBarInfo) -> None:
    assert (await _call(status))["success"] is True


@pytest.mark.anyio
async def test_the_webgui_backend_is_not_checked() -> None:
    status = StatusBarInfo(type="S", message="x", message_id="S#", message_number="343")
    assert (await _call(status, backend_type="webgui"))["success"] is True
