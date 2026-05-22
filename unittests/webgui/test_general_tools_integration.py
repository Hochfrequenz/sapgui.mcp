"""Integration tests for general-purpose tools against real SAP WebGUI.

Tests sap_click_button, sap_select_tab, sap_select_dropdown, sap_screenshot
via the MCP client connected to a live SAP system.
"""

import os

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    ClickButtonResult,
    LoginResult,
    SelectDropdownResult,
    SelectTabResult,
    TransactionResult,
)

from .conftest import call_tool_typed
from .integration_helpers import _wait_for_transaction_screen

# ============================================================================
# sap_click_button
# ============================================================================


@pytest.mark.anyio
async def test_sap_click_button_nonexistent(sap_mcp_client: ClientSession) -> None:
    """Clicking a button that doesn't exist returns success=False."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(
        sap_mcp_client, "sap_click_button", {"label": "NONEXISTENT_BUTTON_XYZ"}, ClickButtonResult
    )
    assert result.success is False
    assert result.error
    assert result.label == "NONEXISTENT_BUTTON_XYZ"


@pytest.mark.anyio
async def test_sap_click_button_empty_label(sap_mcp_client: ClientSession) -> None:
    """Empty label returns failure without hitting the backend."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(sap_mcp_client, "sap_click_button", {"label": ""}, ClickButtonResult)
    assert result.success is False
    assert "empty" in result.error.lower()


# ============================================================================
# sap_select_tab
# ============================================================================


@pytest.mark.anyio
async def test_sap_select_tab_on_su3(sap_mcp_client: ClientSession) -> None:
    """SU3 (User Profile) has tabs — selecting one succeeds."""
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SU3"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    # SU3 has tabs: Festwerte/Defaults, Parameter/Parameters, Adresse/Address
    # Pick the "Festwerte" / "Defaults" tab which is NOT the default active tab
    tab_label = "Festwerte" if sap_language == "DE" else "Defaults"

    result = await call_tool_typed(sap_mcp_client, "sap_select_tab", {"label": tab_label}, SelectTabResult)
    assert result.success, f"sap_select_tab failed: {result.error}"
    assert result.label == tab_label


@pytest.mark.anyio
async def test_sap_select_tab_nonexistent(sap_mcp_client: ClientSession) -> None:
    """Selecting a non-existent tab returns failure."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SU3"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    result = await call_tool_typed(sap_mcp_client, "sap_select_tab", {"label": "NONEXISTENT_TAB_XYZ"}, SelectTabResult)
    assert result.success is False
    assert result.error


# ============================================================================
# sap_select_dropdown — uses SE16 "Max. Trefferzahl" / "Maximum No. of Hits"
# which is reliably present and has a simpler form than BP
# ============================================================================


@pytest.mark.anyio
async def test_sap_select_dropdown_nonexistent_field(sap_mcp_client: ClientSession) -> None:
    """Selecting from a non-existent dropdown returns failure."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_select_dropdown",
        {"label": "NONEXISTENT_DROPDOWN_XYZ", "value": "anything"},
        SelectDropdownResult,
    )
    assert result.success is False
    assert result.error


# ============================================================================
# sap_screenshot
# ============================================================================


@pytest.mark.anyio
async def test_sap_screenshot_returns_content(sap_mcp_client: ClientSession) -> None:
    """Taking a screenshot returns non-empty content."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await sap_mcp_client.call_tool("sap_screenshot", {})
    assert result.content, "Screenshot should return content"
    assert len(result.content) > 0
    # The content should be an image (not a JSON error)
    assert not result.isError, f"Screenshot returned error: {result.content}"


@pytest.mark.anyio
async def test_sap_screenshot_after_transaction(sap_mcp_client: ClientSession) -> None:
    """Screenshot works after navigating to a transaction."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    result = await sap_mcp_client.call_tool("sap_screenshot", {})
    assert result.content
    assert not result.isError
