"""Integration tests for screen text, screen info, and status bar."""

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    LoginResult,
    ScreenInfo,
    ScreenText,
    StatusBarInfo,
    TransactionResult,
)

from .conftest import call_tool_typed
from .integration_helpers import _wait_for_transaction_screen


@pytest.mark.anyio
async def test_sap_get_screen_text_structure(sap_mcp_client: ClientSession) -> None:
    """Test that sap_get_screen_text returns structured output."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SU3"}, TransactionResult)
    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    result = await call_tool_typed(sap_mcp_client, "sap_get_screen_text", {}, ScreenText)
    assert result.success, f"sap_get_screen_text failed: {result.error}"

    # Check for expected structure
    assert result.title, "Should contain title"

    # Should have some labels or content
    has_labels = bool(result.labels)
    has_content = bool(result.main_content)
    has_buttons = bool(result.buttons)

    assert (
        has_labels or has_content or has_buttons
    ), f"Screen text should contain labels, content, or buttons. Got: {result}"


@pytest.mark.anyio
async def test_sap_read_status_bar_after_navigation(sap_mcp_client: ClientSession) -> None:
    """Test reading status bar after successful navigation."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SU3"}, TransactionResult)
    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    # Should return with type or message fields
    assert (
        result.type is not None or result.message is not None
    ), f"Status bar should return type/message info: {result}"


@pytest.mark.anyio
async def test_sap_read_status_bar_after_error(sap_mcp_client: ClientSession) -> None:
    """Test reading status bar after triggering an error."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Try invalid transaction to trigger error
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "ZZZZINVALID999"}, TransactionResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    # Should indicate error type or contain error message
    is_error = result.type == "E"
    has_error_msg = result.message and any(
        ind in result.message.lower() for ind in ["error", "fehler", "existiert nicht", "does not exist"]
    )

    assert is_error or has_error_msg, f"Status bar should indicate error after invalid transaction: {result}"


@pytest.mark.anyio
async def test_sap_get_screen_info_different_transactions(sap_mcp_client: ClientSession) -> None:
    """Test that screen info changes between transactions."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Get info from SE16
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")
    result1 = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)

    # Get info from SM37
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")
    result2 = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)

    # The title or content should be different
    assert (
        result1.title != result2.title or result1.url != result2.url
    ), "Screen info should differ between SE16 and SM37"
