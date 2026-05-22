"""Integration tests for SAP keyboard operations (F3 back, F8 execute)."""

import os

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    KeyboardResult,
    LoginResult,
    TransactionResult,
)

from .conftest import call_tool_typed, get_html_content
from .integration_helpers import (
    _wait_for_easy_access,
    _wait_for_transaction_screen,
)


@pytest.mark.anyio
async def test_sap_press_key_f3_navigates_back(sap_mcp_client: ClientSession) -> None:
    """Test F3 (Back) returns from transaction to previous screen."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Press F3 to go back
    result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F3"}, KeyboardResult)
    assert result.success, f"Keyboard F3 failed: {result.error}"
    assert result.key == "F3", f"Expected key F3: {result}"

    # Wait for Easy Access (OK-Code field visible means we're back on main menu)
    await _wait_for_easy_access(sap_mcp_client)

    # Should be back on Easy Access or previous screen
    page_html = (await get_html_content(sap_mcp_client)).lower()

    # SE16 specific content should be gone or we should be on Easy Access
    se16_gone = "data browser" not in page_html and "tabelleninhalt" not in page_html
    on_easy_access = "sap easy access" in page_html or "toolbarokcode" in page_html

    assert se16_gone or on_easy_access, "F3 should have navigated away from SE16"


@pytest.mark.anyio
async def test_sap_press_key_f8_triggers_execution(sap_mcp_client: ClientSession) -> None:
    """Test F8 (Execute) triggers action in SE16.

    When F8 is pressed in SE16 without a table name, SAP should show an error
    message about missing table name - this proves F8 was received.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Try to execute without entering a table name - should trigger error
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Check for error message in page or status bar
    page_html = (await get_html_content(sap_mcp_client)).lower()

    # SAP should show error about missing table name
    if sap_language == "DE":
        expected_phrases = ["eingabe", "tabelle", "fehler", "pflichtfeld", "füllen"]
    else:
        expected_phrases = ["enter", "table", "error", "required", "specify", "fill"]

    assert any(
        phrase in page_html for phrase in expected_phrases
    ), f"F8 without input should trigger error or prompt. Language: {sap_language}"
