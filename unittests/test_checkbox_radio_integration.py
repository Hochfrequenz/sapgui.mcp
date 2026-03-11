"""
Integration tests for sap_set_checkbox, sap_set_radio_button, and FormField.checked.

These tests run against a real SAP system to verify that:
1. sap_set_checkbox can toggle checkboxes on selection screens
2. sap_set_radio_button can select radio buttons on selection screens
3. sap_get_form_fields returns the correct checked state for checkboxes/radios
4. State changes persist and are visible to subsequent reads
5. ARIA snapshots reflect checkbox/radio changes (snapshot-diff tests)

These tests use SE09 (checkboxes) and SE11 (radio buttons) as test screens.
"""

import json

import pytest
from mcp import ClientSession

from sapwebguimcp.models import FormFieldsResult, LoginResult, TransactionResult
from sapwebguimcp.models.sap_results import SetFieldResult
from sapwebguimcp.parsers.screen_state_parser import parse_selection_screen_state

from .conftest import call_tool_typed


# =============================================================================
# sap_set_checkbox tests (using SE09 selection screen)
# =============================================================================


@pytest.mark.anyio
async def test_set_checkbox_check(sap_mcp_client: ClientSession) -> None:
    """Test checking a checkbox on the SE09 selection screen."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    result = await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Workbench", "checked": True}, SetFieldResult,
    )
    assert result.success, f"set_checkbox failed: {result.error}"


@pytest.mark.anyio
async def test_set_checkbox_uncheck(sap_mcp_client: ClientSession) -> None:
    """Test unchecking a checkbox on the SE09 selection screen."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    result = await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Workbench", "checked": False}, SetFieldResult,
    )
    assert result.success, f"set_checkbox failed: {result.error}"


@pytest.mark.anyio
async def test_set_checkbox_not_found(sap_mcp_client: ClientSession) -> None:
    """Setting a non-existent checkbox should return an error."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    result = await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "NonExistentCheckbox99", "checked": True}, SetFieldResult,
    )
    assert not result.success


@pytest.mark.anyio
async def test_set_checkbox_state_visible_in_form_fields(sap_mcp_client: ClientSession) -> None:
    """After setting a checkbox, sap_get_form_fields should reflect the new state."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    # Uncheck Workbench
    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Workbench", "checked": False}, SetFieldResult,
    )

    # Read form fields and verify checked state
    fields = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {}, FormFieldsResult,
    )
    assert fields.success

    workbench_fields = [f for f in fields.fields if "Workbench" in f.label and f.field_type == "checkbox"]
    assert len(workbench_fields) >= 1, "Expected Workbench checkbox in form fields"
    assert workbench_fields[0].checked is False, "Workbench should be unchecked"


# =============================================================================
# sap_set_radio_button tests (using SE11 selection screen)
# =============================================================================


@pytest.mark.anyio
async def test_set_radio_button(sap_mcp_client: ClientSession) -> None:
    """Test selecting a radio button on the SE11 selection screen."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success

    result = await call_tool_typed(
        sap_mcp_client, "sap_set_radio_button",
        {"label": "Datenbanktabelle"}, SetFieldResult,
    )
    assert result.success, f"set_radio_button failed: {result.error}"


@pytest.mark.anyio
async def test_set_radio_button_switch(sap_mcp_client: ClientSession) -> None:
    """Test switching between radio buttons on SE11."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success

    # Select "View" radio
    result = await call_tool_typed(
        sap_mcp_client, "sap_set_radio_button",
        {"label": "View"}, SetFieldResult,
    )
    assert result.success

    # Switch to "Datenbanktabelle" radio
    result = await call_tool_typed(
        sap_mcp_client, "sap_set_radio_button",
        {"label": "Datenbanktabelle"}, SetFieldResult,
    )
    assert result.success


@pytest.mark.anyio
async def test_set_radio_button_not_found(sap_mcp_client: ClientSession) -> None:
    """Setting a non-existent radio button should return an error."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success

    result = await call_tool_typed(
        sap_mcp_client, "sap_set_radio_button",
        {"label": "NonExistentRadio99"}, SetFieldResult,
    )
    assert not result.success


@pytest.mark.anyio
async def test_set_radio_button_state_visible_in_form_fields(sap_mcp_client: ClientSession) -> None:
    """After selecting a radio, sap_get_form_fields should show it as checked."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success

    # Select "View" radio
    await call_tool_typed(
        sap_mcp_client, "sap_set_radio_button",
        {"label": "View"}, SetFieldResult,
    )

    # Read form fields and verify checked state
    fields = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {}, FormFieldsResult,
    )
    assert fields.success

    view_radios = [f for f in fields.fields if f.label == "View" and f.field_type == "radio"]
    assert len(view_radios) >= 1, "Expected View radio in form fields"
    assert view_radios[0].checked is True, "View radio should be checked"


# =============================================================================
# Snapshot-diff integration tests
# =============================================================================

async def _get_screen_text(client: ClientSession) -> str:
    """Get screen text content as a raw string for snapshot comparison."""
    result = await client.call_tool("sap_get_screen_text", {})
    assert result.content
    text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
    return text


async def _get_checkbox_states(client: ClientSession) -> dict[str, bool]:
    """Get all checkbox states from form fields as {label: checked}."""
    fields = await call_tool_typed(client, "sap_get_form_fields", {}, FormFieldsResult)
    assert fields.success
    return {
        f.label: f.checked
        for f in fields.fields
        if f.field_type == "checkbox" and f.checked is not None
    }


async def _get_radio_states(client: ClientSession) -> dict[str, bool]:
    """Get all radio states from form fields as {label: checked}."""
    fields = await call_tool_typed(client, "sap_get_form_fields", {}, FormFieldsResult)
    assert fields.success
    return {
        f.label: f.checked
        for f in fields.fields
        if f.field_type == "radio" and f.checked is not None
    }


@pytest.mark.anyio
async def test_checkbox_toggle_changes_snapshot(sap_mcp_client: ClientSession) -> None:
    """Toggle a checkbox and verify the form fields state actually changed."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    # Read state before
    states_before = await _get_checkbox_states(sap_mcp_client)
    # Find a checkbox we can toggle (pick one that's currently checked)
    togglable = [label for label, checked in states_before.items() if checked]
    assert togglable, "Expected at least one checked checkbox on SE09"
    target_label = togglable[0]

    # Uncheck it
    result = await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": target_label, "checked": False}, SetFieldResult,
    )
    assert result.success, f"set_checkbox failed: {result.error}"

    # Read state after
    states_after = await _get_checkbox_states(sap_mcp_client)

    # The toggled checkbox should now be unchecked
    assert states_after[target_label] is False, (
        f"Expected '{target_label}' to be unchecked after toggle. "
        f"Before: {states_before[target_label]}, After: {states_after[target_label]}"
    )

    # Restore: check it again
    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": target_label, "checked": True}, SetFieldResult,
    )


@pytest.mark.anyio
async def test_radio_switch_changes_snapshot(sap_mcp_client: ClientSession) -> None:
    """Switch a radio button and verify the form fields state reflects the change."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success

    # Read state before
    radios_before = await _get_radio_states(sap_mcp_client)
    currently_selected = [label for label, checked in radios_before.items() if checked]
    currently_unselected = [label for label, checked in radios_before.items() if not checked]
    assert currently_selected, "Expected a selected radio on SE11"
    assert currently_unselected, "Expected at least one unselected radio on SE11"

    # Switch to a different radio
    new_selection = currently_unselected[0]
    result = await call_tool_typed(
        sap_mcp_client, "sap_set_radio_button",
        {"label": new_selection}, SetFieldResult,
    )
    assert result.success, f"set_radio_button failed: {result.error}"

    # Read state after
    radios_after = await _get_radio_states(sap_mcp_client)

    # The new selection should be checked
    assert radios_after[new_selection] is True, (
        f"Expected '{new_selection}' to be selected. Got: {radios_after[new_selection]}"
    )
    # The old selection should be unchecked (radio buttons are mutually exclusive)
    old_selection = currently_selected[0]
    assert radios_after[old_selection] is False, (
        f"Expected '{old_selection}' to be deselected. Got: {radios_after[old_selection]}"
    )


@pytest.mark.anyio
async def test_multiple_checkbox_toggles_are_independent(sap_mcp_client: ClientSession) -> None:
    """Toggling multiple checkboxes should each be independently reflected."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    states_before = await _get_checkbox_states(sap_mcp_client)
    assert len(states_before) >= 2, "Need at least 2 checkboxes for this test"

    # Toggle the first two checkboxes
    labels = list(states_before.keys())[:2]
    for label in labels:
        new_value = not states_before[label]
        result = await call_tool_typed(
            sap_mcp_client, "sap_set_checkbox",
            {"label": label, "checked": new_value}, SetFieldResult,
        )
        assert result.success, f"set_checkbox failed for '{label}': {result.error}"

    # Verify both changed
    states_after = await _get_checkbox_states(sap_mcp_client)
    for label in labels:
        assert states_after[label] != states_before[label], (
            f"Checkbox '{label}' should have toggled. "
            f"Before: {states_before[label]}, After: {states_after[label]}"
        )

    # Restore original state
    for label in labels:
        await call_tool_typed(
            sap_mcp_client, "sap_set_checkbox",
            {"label": label, "checked": states_before[label]}, SetFieldResult,
        )
