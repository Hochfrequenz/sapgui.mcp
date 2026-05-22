"""Integration tests for intent logging."""

import json

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    IntentLogResult,
    KeyboardResult,
    LoginResult,
    TransactionResult,
)

from .conftest import call_tool_typed
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)


@pytest.mark.anyio
async def test_intent_logging_with_bp_transaction(
    sap_mcp_client: ClientSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test intent logging during BP (Business Partner) transaction.

    This test verifies that:
    1. log_intent tool can record intents during SAP operations
    2. The intent log messages are emitted with correct format
    3. The intent resource is accessible

    Steps:
    - Login to SAP
    - Run transaction BP
    - Press F5 to start creating a person
    - Log intents and verify log messages
    """
    # Login to SAP
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"sap_login failed: {login_result.error}"

    # Log intent at start
    intent_data = await call_tool_typed(
        sap_mcp_client,
        "log_intent",
        {
            "intent": "Create a new business partner of type Person",
            "context": {"tcode": "BP", "action": "create_person"},
        },
        IntentLogResult,
    )
    assert intent_data.success, f"log_intent failed: {intent_data.error}"
    assert intent_data.logged is True, "Intent should be logged"
    entry_id = intent_data.entry_id
    assert entry_id, "Intent should have an entry_id"
    session_id = intent_data.session_id
    assert session_id, "Intent should have a session_id"

    # Run transaction BP
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert tx_result.success, f"sap_transaction BP failed: {tx_result.error}"

    # Wait for BP screen (has Person/Organisation buttons)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Capture HTML snapshot for debugging
    await capture_html_snapshot(sap_mcp_client, "bp_initial")

    # Press F5 to start creating (opens new partner creation)
    kb_result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    assert kb_result.success, f"sap_press_key F5 failed: {kb_result.error}"

    # Wait a moment for the dialog to open
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture HTML snapshot after F5
    await capture_html_snapshot(sap_mcp_client, "bp_create_person")

    # Log another intent for the milestone
    intent2_data = await call_tool_typed(
        sap_mcp_client,
        "log_intent",
        {
            "intent": "Opened person creation dialog",
            "context": {"step": "dialog_open"},
        },
        IntentLogResult,
    )
    assert intent2_data.success, f"log_intent 2 failed: {intent2_data.error}"

    # Verify the intent resource template is available
    templates = await sap_mcp_client.list_resource_templates()
    template_uris = [str(t.uriTemplate) for t in templates.resourceTemplates]
    print(f"\nAvailable resource templates: {template_uris}")

    # Check that an intent resource template exists
    has_intent_template = any("intent://" in uri for uri in template_uris)
    assert has_intent_template, f"Expected intent:// template, got: {template_uris}"

    # Read the intent resource for the session using the session_id from log_intent
    intent_resource = await sap_mcp_client.read_resource(f"intent://session/{session_id}")
    intent_log = intent_resource.contents[0].text if intent_resource.contents else "[]"
    print(f"\nIntent log content for session {session_id}: {intent_log}")

    # Parse and verify the log has our entries
    entries = json.loads(intent_log)
    assert len(entries) >= 2, f"Expected at least 2 intent entries, got {len(entries)}"

    # Verify the entries have the expected structure
    for entry in entries:
        assert "timestamp" in entry, f"Entry missing timestamp: {entry}"
        assert "intent" in entry, f"Entry missing intent: {entry}"
        assert "entry_id" in entry, f"Entry missing entry_id: {entry}"

    # Verify our specific intents are in the log
    intents = [e["intent"] for e in entries]
    assert any("business partner" in i.lower() for i in intents), f"Expected BP intent: {intents}"
    assert any("dialog" in i.lower() for i in intents), f"Expected dialog intent: {intents}"

    # Verify entry_ids match what we received from the tool
    entry_ids = [e["entry_id"] for e in entries]
    assert entry_id in entry_ids, f"First entry_id {entry_id} not in log: {entry_ids}"
    assert intent2_data.entry_id in entry_ids, "Second entry_id not in log"

    # Press F3 to go back/cancel (avoid creating an actual partner)
    back_result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F3"}, KeyboardResult)
    print(f"\nBack result: {back_result}")
