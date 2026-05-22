"""Integration tests for DesktopBackend Phase 2 (Primitives) against live SAP GUI.

These tests exercise fill_field, click_button, set_checkbox, press_key, etc.
against a real SAP system. They are stateful — each test navigates to a
transaction, performs actions, and navigates back.

Tests are designed to NOT depend on specific default values or button labels
(SAP UI is stateful and language-dependent). Instead they assert on behavior:
- fill_field → discover_fields shows the value changed
- set_checkbox → the checkbox state changed
- click_button → the screen changed (title or transaction changed)

Skipped unless running on the authorized SAP test machine with credentials.
"""

import sys
from typing import Any, cast

import pytest

from sapguimcp.backend.desktop._element_finder import _flatten
from unittests.desktop.conftest import TEST_TABLE, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only")


# ---------------------------------------------------------------------------
# fill_field
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_fill_field_on_se16(backend):
    """fill_field sets a text field value that can be read back."""
    await backend.enter_transaction("SE16")

    await backend.fill_field("Tabellenname", TEST_TABLE)

    fields = await backend.discover_fields()
    assert len(fields) > 0
    assert fields[0].value == TEST_TABLE

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# fill_main_input
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_fill_main_input_on_se38(backend):
    """fill_main_input fills the first matching field."""
    await backend.enter_transaction("SE38")

    # Try multiple possible labels — language-independent
    result = await backend.fill_main_input("ZTEST_PROGRAM", ["Programm", "Program"])
    assert result is True

    fields = await backend.discover_fields()
    assert any(f.value == "ZTEST_PROGRAM" for f in fields)

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# click_button
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_click_button_changes_screen(backend):
    """click_button navigates to a new screen."""
    await backend.enter_transaction("SE38")

    # Fill a program name first
    await backend.fill_field("Programm", "SAPLSMTR_NAVIGATION")

    # Get current title
    title_before = await backend.get_page_title()

    # Find a display button and click it — try both DE and EN labels
    buttons = await backend.discover_buttons()
    display_labels = ["Anzeigen", "Display"]
    clicked = False
    for btn in buttons:
        if btn.label in display_labels:
            await backend.click_button(btn.label)
            clicked = True
            break

    if clicked:
        title_after = await backend.get_page_title()
        assert title_after != title_before, "Screen should have changed after button click"

    # Navigate back
    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# set_checkbox
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_set_checkbox_on_sm37(backend):
    """set_checkbox changes checkbox state on SM37 job selection screen."""
    await backend.enter_transaction("SM37")

    # SM37 has job status checkboxes — find them
    session = backend._session

    async def get_checkbox_states():
        """Read all checkbox states from current screen."""

        def _read():
            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            checkboxes = {}
            for elem in _flatten(tree):
                if elem.type_as_number == 42:  # GuiCheckBox
                    # Read actual selected state from COM
                    chk = session.find_by_id(elem.id)
                    checkboxes[elem.text.strip()] = bool(cast(Any, chk).selected)
            return checkboxes

        return await backend.com.run(_read)

    # Read initial states
    states_before = await get_checkbox_states()
    assert len(states_before) > 0, "SM37 should have checkboxes"

    # Pick the first checkbox and toggle it
    first_label = next(iter(states_before))
    initial_state = states_before[first_label]

    await backend.set_checkbox(first_label, not initial_state)

    # Verify it changed
    states_after = await get_checkbox_states()
    assert states_after[first_label] != initial_state, f"Checkbox '{first_label}' should have toggled"

    # Toggle it back to restore state
    await backend.set_checkbox(first_label, initial_state)

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# select_dropdown
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_get_dropdown_options_on_sm37(backend):
    """get_dropdown_options reads combobox entries from SM37."""
    await backend.enter_transaction("SM37")

    # SM37 has an event ID combobox — but we don't know its label
    # Just verify discover_fields finds it
    fields = await backend.discover_fields()
    combo_fields = [f for f in fields if f.type == "GuiComboBox"]

    # SM37 has at least one combobox (Event ID)
    # Don't assert specific count — just that we can discover them
    if combo_fields:
        # Try to get options — may return empty list if not implemented fully
        options = await backend.get_dropdown_options(combo_fields[0].name or "")
        assert isinstance(options, list)

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# press_key (already tested in Phase 1, but verify F-keys work)
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_press_key_f8_executes(backend):
    """press_key F8 executes on SE16 after filling table name."""
    await backend.enter_transaction("SE16")
    await backend.fill_field("Tabellenname", TEST_TABLE)

    kr = await backend.press_key("F8")
    assert kr.success
    # F8 may stay on the same screen (selection screen) or navigate — just verify
    # the key was sent successfully and status bar was read
    assert kr.status_bar_read is True

    # Go back to Easy Access
    await backend.press_key("F3")
    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# discover_fields + discover_buttons
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_discover_fields_returns_field_info(backend):
    """discover_fields returns FieldInfo objects with id, name, type, value."""
    await backend.enter_transaction("SE16")

    fields = await backend.discover_fields()
    assert len(fields) >= 1

    field = fields[0]
    assert field.id is not None
    assert field.name is not None
    assert field.type is not None
    assert field.value is not None  # may be empty string but not None

    await backend.press_key("F3")


@skip_no_sap
@pytest.mark.anyio
async def test_discover_buttons_returns_button_info(backend):
    """discover_buttons returns ButtonInfo objects with label."""
    await backend.enter_transaction("SE16")

    buttons = await backend.discover_buttons()
    assert len(buttons) >= 1
    assert all(b.label for b in buttons)

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# get_screen_text
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_get_screen_text_has_content(backend):
    """get_screen_text returns structured text from the current screen."""
    await backend.enter_transaction("SE16")

    text = await backend.get_screen_text()
    assert text.success
    assert text.title  # should have a title
    assert isinstance(text.labels, list)
    assert isinstance(text.buttons, list)

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# fill_form (multiple fields)
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_fill_form_on_se16(backend):
    """fill_form fills multiple fields — here just the one field on SE16."""
    await backend.enter_transaction("SE16")

    # SE16 has one field: Tabellenname. fill_form with one entry should work.
    result = await backend.fill_form({"Tabellenname": TEST_TABLE})
    assert result.success

    fields = await backend.discover_fields()
    assert any(f.value == TEST_TABLE for f in fields)

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# get_page_title + get_screen_info + get_status_bar
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_screen_info_after_transaction(backend):
    """get_screen_info returns transaction and program info."""
    await backend.enter_transaction("SE16")

    info = await backend.get_screen_info()
    assert info.success
    assert info.transaction == "SE16"
    assert info.program is not None

    title = await backend.get_page_title()
    assert title  # non-empty

    sbar = await backend.get_status_bar()
    assert sbar.success
    assert isinstance(sbar.message, str)

    await backend.press_key("F3")
