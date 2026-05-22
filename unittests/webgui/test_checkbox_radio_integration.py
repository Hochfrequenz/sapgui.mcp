"""
Integration tests for sap_set_checkbox, sap_set_radio_button, and screen state verification.

These tests run against a real SAP system to verify that:
1. sap_set_checkbox can toggle checkboxes on selection screens
2. sap_set_radio_button can select radio buttons on selection screens
3. ARIA snapshots reflect checkbox/radio changes after set operations
4. State changes persist and are visible to subsequent reads

These tests use SE09 (checkboxes) and SE11 (radio buttons) as test screens.
State verification uses browser_snapshot + parse_selection_screen_state
(ARIA snapshot) rather than sap_get_form_fields (JS DOM), because SAP
checkbox/radio controls are reliably represented in ARIA snapshots.
"""

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.backend.webgui.parsers.screen_state_parser import parse_selection_screen_state
from sapguimcp.models import LoginResult, TransactionResult
from sapguimcp.models.sap_results import SetFieldResult

from .conftest import call_tool_typed


async def _get_screen_state(client: ClientSession) -> dict[str, dict[str, bool]]:
    """Read ARIA snapshot via browser_snapshot, parse into checkbox/radio state dicts.

    Returns {"checkboxes": {label: checked}, "radios": {label: checked}}.
    """
    snap = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    assert snap.success, f"browser_snapshot failed: {snap.error}"
    assert snap.snapshot, "browser_snapshot returned empty snapshot"

    state = parse_selection_screen_state(snap.snapshot)
    return {"checkboxes": state.checkboxes, "radios": state.radios}


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
        sap_mcp_client,
        "sap_set_checkbox",
        {"label": "Workbench", "checked": True},
        SetFieldResult,
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
        sap_mcp_client,
        "sap_set_checkbox",
        {"label": "Workbench", "checked": False},
        SetFieldResult,
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
        sap_mcp_client,
        "sap_set_checkbox",
        {"label": "NonExistentCheckbox99", "checked": True},
        SetFieldResult,
    )
    assert not result.success


@pytest.mark.anyio
async def test_set_checkbox_state_visible_in_snapshot(sap_mcp_client: ClientSession) -> None:
    """After setting a checkbox, the ARIA snapshot should reflect the new state."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    # Read current state to find a checkbox label
    state_before = await _get_screen_state(sap_mcp_client)
    assert state_before["checkboxes"], "Expected checkboxes on SE09"

    # Pick a checkbox and set it to unchecked
    target_label = list(state_before["checkboxes"].keys())[0]
    await call_tool_typed(
        sap_mcp_client,
        "sap_set_checkbox",
        {"label": target_label, "checked": False},
        SetFieldResult,
    )

    # Verify via ARIA snapshot
    state_after = await _get_screen_state(sap_mcp_client)
    assert (
        target_label in state_after["checkboxes"]
    ), f"'{target_label}' should still appear in snapshot after unchecking"
    assert state_after["checkboxes"][target_label] is False, f"'{target_label}' should be unchecked in snapshot"


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
        sap_mcp_client,
        "sap_set_radio_button",
        {"label": "Datenbanktabelle"},
        SetFieldResult,
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
        sap_mcp_client,
        "sap_set_radio_button",
        {"label": "View"},
        SetFieldResult,
    )
    assert result.success

    # Switch to "Datenbanktabelle" radio
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_set_radio_button",
        {"label": "Datenbanktabelle"},
        SetFieldResult,
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
        sap_mcp_client,
        "sap_set_radio_button",
        {"label": "NonExistentRadio99"},
        SetFieldResult,
    )
    assert not result.success


@pytest.mark.anyio
async def test_set_radio_button_state_visible_in_snapshot(sap_mcp_client: ClientSession) -> None:
    """After selecting a radio, the ARIA snapshot should show it as checked."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success

    # Read current state
    state_before = await _get_screen_state(sap_mcp_client)
    assert state_before["radios"], "Expected radios on SE11"

    # Find an unselected radio
    unselected = [l for l, checked in state_before["radios"].items() if not checked]
    assert unselected, "Expected at least one unselected radio on SE11"
    target_label = unselected[0]

    # Select it
    await call_tool_typed(
        sap_mcp_client,
        "sap_set_radio_button",
        {"label": target_label},
        SetFieldResult,
    )

    # Verify via ARIA snapshot
    state_after = await _get_screen_state(sap_mcp_client)
    assert (
        state_after["radios"][target_label] is True
    ), f"'{target_label}' should be selected in snapshot after set_radio_button"


# =============================================================================
# Snapshot-diff integration tests: verify state A → state B
# =============================================================================


@pytest.mark.anyio
async def test_checkbox_toggle_changes_snapshot(sap_mcp_client: ClientSession) -> None:
    """Toggle a checkbox and verify the ARIA snapshot state actually changed."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    # Read state before
    state_before = await _get_screen_state(sap_mcp_client)
    checkboxes = state_before["checkboxes"]
    togglable = [label for label, checked in checkboxes.items() if checked]
    assert togglable, "Expected at least one checked checkbox on SE09"
    target_label = togglable[0]

    # Uncheck it
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_set_checkbox",
        {"label": target_label, "checked": False},
        SetFieldResult,
    )
    assert result.success, f"set_checkbox failed: {result.error}"

    # Read state after — the checkbox should now be unchecked
    state_after = await _get_screen_state(sap_mcp_client)
    assert state_after["checkboxes"][target_label] is False, (
        f"Expected '{target_label}' unchecked after toggle. "
        f"Before: {checkboxes[target_label]}, After: {state_after['checkboxes'][target_label]}"
    )

    # Restore original state
    await call_tool_typed(
        sap_mcp_client,
        "sap_set_checkbox",
        {"label": target_label, "checked": True},
        SetFieldResult,
    )


@pytest.mark.anyio
async def test_radio_switch_changes_snapshot(sap_mcp_client: ClientSession) -> None:
    """Switch a radio button and verify the ARIA snapshot reflects the change."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success

    # Read state before
    state_before = await _get_screen_state(sap_mcp_client)
    radios = state_before["radios"]
    currently_selected = [l for l, checked in radios.items() if checked]
    currently_unselected = [l for l, checked in radios.items() if not checked]
    assert currently_selected, "Expected a selected radio on SE11"
    assert currently_unselected, "Expected an unselected radio on SE11"

    new_selection = currently_unselected[0]
    old_selection = currently_selected[0]

    # Switch to a different radio
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_set_radio_button",
        {"label": new_selection},
        SetFieldResult,
    )
    assert result.success, f"set_radio_button failed: {result.error}"

    # Read state after
    state_after = await _get_screen_state(sap_mcp_client)
    assert state_after["radios"][new_selection] is True, f"Expected '{new_selection}' selected after switch"
    assert state_after["radios"][old_selection] is False, f"Expected '{old_selection}' deselected after switch"


@pytest.mark.anyio
async def test_multiple_checkbox_toggles_are_independent(sap_mcp_client: ClientSession) -> None:
    """Toggling multiple checkboxes should each be independently reflected in the snapshot."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    state_before = await _get_screen_state(sap_mcp_client)
    checkboxes = state_before["checkboxes"]
    assert len(checkboxes) >= 2, "Need at least 2 checkboxes for this test"

    # Toggle the first two checkboxes
    labels = list(checkboxes.keys())[:2]
    for label in labels:
        new_value = not checkboxes[label]
        result = await call_tool_typed(
            sap_mcp_client,
            "sap_set_checkbox",
            {"label": label, "checked": new_value},
            SetFieldResult,
        )
        assert result.success, f"set_checkbox failed for '{label}': {result.error}"

    # Verify both changed in snapshot
    state_after = await _get_screen_state(sap_mcp_client)
    for label in labels:
        assert state_after["checkboxes"][label] != checkboxes[label], (
            f"Checkbox '{label}' should have toggled. "
            f"Before: {checkboxes[label]}, After: {state_after['checkboxes'][label]}"
        )

    # Restore original state
    for label in labels:
        await call_tool_typed(
            sap_mcp_client,
            "sap_set_checkbox",
            {"label": label, "checked": checkboxes[label]},
            SetFieldResult,
        )
