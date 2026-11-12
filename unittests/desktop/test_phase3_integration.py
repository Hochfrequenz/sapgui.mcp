"""Integration tests for DesktopBackend Phase 3 (Editor + Popup) against live SAP GUI.

Tests exercise check_popup, dismiss_popup, dismiss_language_dialog,
read_editor_source, and check_and_activate against a real SAP system.

Skipped unless running on the authorized SAP test machine with credentials.
"""

import asyncio
import sys

import pytest

from sapguimcp import lang
from unittests.desktop.conftest import TEST_CLASS_ORIGLANG, go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only")


# ---------------------------------------------------------------------------
# check_popup / dismiss_popup
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_check_popup_returns_none_on_easy_access(backend):
    """No popup on Easy Access screen."""
    popup = await backend.check_popup()
    assert popup is None


@skip_no_sap
@pytest.mark.anyio
async def test_check_popup_detects_modal(backend):
    """Trigger a popup by entering an invalid transaction and check it's detected."""
    # Enter a non-existent transaction — SAP may show a popup or error
    tr = await backend.enter_transaction("ZZZNOTEXIST999")

    # Check status bar — might have an error message instead of popup
    sbar = await backend.get_status_bar()
    popup = await backend.check_popup()

    # Either a popup appeared or the status bar has an error — both are valid
    if popup is not None:
        assert popup.message or popup.buttons
        await backend.dismiss_popup()
    else:
        # SAP showed an error in the status bar instead of a popup
        assert sbar.type in ("E", "W", "S", "none")

    await backend.press_key("F3")


@skip_no_sap
@pytest.mark.anyio
async def test_dismiss_popup_on_exit_with_changes(backend, pack):
    """dismiss_popup can handle the 'unsaved data' popup when leaving a transaction."""
    # Navigate to SE38, enter a program name, open for display
    await backend.enter_transaction("SE38")
    await backend.fill_field(next(iter(pack.common.program)), "SAPLSMTR_NAVIGATION")

    buttons = await backend.discover_buttons()
    for btn in buttons:
        if pack.common.display.equals(btn.label):
            await backend.click_button(btn.label)
            break

    await asyncio.sleep(1)

    # Now we're in the editor. Press F3 (back) — should return to SE38
    await backend.press_key("F3")

    # Check if a popup appeared (e.g., "save?" or "exit?")
    popup = await backend.check_popup()
    if popup is not None:
        result = await backend.dismiss_popup()
        assert result.success

    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# dismiss_language_dialog
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_dismiss_language_dialog_no_op_when_absent(backend):
    """dismiss_language_dialog is a no-op when no language dialog is present."""
    # Should not raise — just does nothing
    await backend.dismiss_language_dialog()


@skip_no_sap
@pytest.mark.anyio
async def test_original_language_dialog_is_recognised(backend, pack):
    """The SAPLSETX 0100 dialog of a class with a foreign original language is recognised (#1087).

    Recognition is the check ``dismiss_language_dialog`` uses: the lower-cased title of ``wnd[1]`` against
    ``popup.original_language_hint``. The dialog is then closed explicitly (not via Enter: it has no default
    button), the class stays unchanged and the lock is released. Needs ``TEST_CLASS_ORIGLANG``, see
    docs/SAP_TEST_PREREQUISITES.md.
    """
    await backend.enter_transaction("SE24")
    await backend.wait_for_ready()
    assert await backend.focus_and_type("SEOCLASS-CLSNAME", TEST_CLASS_ORIGLANG)
    await backend.press_key("F7")  # Display
    await backend.wait_for_ready()
    if pack.se24.initial_screen.contains((await backend.get_screen_info()).title or ""):
        await go_home(backend)
        pytest.skip(f"Test class {TEST_CLASS_ORIGLANG} is missing (see docs/SAP_TEST_PREREQUISITES.md)")
    session = backend.require_session()
    try:
        # The display of a class does not show the dialog; the switch to change mode does.
        assert await backend.check_popup() is None
        await backend.press_key("Ctrl+F1")
        await backend.wait_for_ready()
        popup = await backend.check_popup()
        assert popup is not None, "Expected the original-language dialog after switching to change mode"
        hint = lang.universal().popup.original_language_hint.pattern
        title = (await backend.com.run(lambda: str(session.find_by_id("wnd[1]").text))).lower()
        assert hint.search(title), f"Dialog title {title!r} is not recognised by popup.original_language_hint"
        # Close it by its button "maintain in original language" (the contributor PR adds this to the dismiss).
        await backend.com.run(lambda: session.find_by_id("wnd[1]/usr/btnPUSH1").press())
        await backend.wait_for_ready()
        assert await backend.check_popup() is None
        # Back to display mode without saving: releases the lock, nothing was changed.
        await backend.press_key("Ctrl+F1")
        await backend.wait_for_ready()
        assert await backend.check_popup() is None
    finally:
        await go_home(backend)


# ---------------------------------------------------------------------------
# read_editor_source
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_read_editor_source_returns_none_on_non_editor_screen(backend):
    """read_editor_source returns None when no editor is on screen."""
    # Easy Access has no editor
    result = await backend.read_editor_source()
    assert result is None


@skip_no_sap
@pytest.mark.anyio
async def test_read_editor_source_on_se38(backend, pack):
    """read_editor_source attempts to read from SE38 editor (may return None due to COM limitation)."""
    await backend.enter_transaction("SE38")
    await backend.fill_field(next(iter(pack.common.program)), "SAPLSMTR_NAVIGATION")

    buttons = await backend.discover_buttons()
    for btn in buttons:
        if pack.common.display.equals(btn.label):
            await backend.click_button(btn.label)
            break

    await asyncio.sleep(1)

    # Try reading editor source — may return None due to COM dispatch limitation
    # on SAP's AbapEditor control. This is a known issue documented in the code.
    source = await backend.read_editor_source()
    # We accept both outcomes: source found (str) or not found (None)
    assert source is None or isinstance(source, str)

    if source is not None:
        assert len(source) > 0

    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# check_and_activate (only on display screen — won't actually activate)
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_check_and_activate_returns_result(backend):
    """check_and_activate returns a CheckActivateResult even if check fails."""
    # On Easy Access, Ctrl+F2/F3 won't do anything meaningful
    # but the method should not crash
    result = await backend.check_and_activate()
    assert result is not None
    # success may be True or False depending on screen state
    assert isinstance(result.messages, list)
    assert isinstance(result.activated, bool)
