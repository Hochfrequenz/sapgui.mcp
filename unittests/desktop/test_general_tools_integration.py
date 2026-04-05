"""Integration tests for general-purpose backend methods on desktop backend.

Tests click_button, click_tab, select_dropdown, take_screenshot against live SAP GUI.
"""

import sys

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only"),
    skip_no_sap,
]


# ============================================================================
# click_button
# ============================================================================


@pytest.mark.anyio
async def test_click_button_on_se38(backend) -> None:
    """click_button clicks 'Anzeigen'/'Display' on SE38 initial screen."""
    await backend.enter_transaction("SE38")
    await backend.fill_field("Programm", "SAPLSMTR_NAVIGATION")

    buttons = await backend.discover_buttons()
    display_labels = ["Anzeigen", "Display"]
    matched = [b for b in buttons if b.label in display_labels]
    assert matched, f"Expected a Display button, got: {[b.label for b in buttons]}"

    # click_button should not raise
    await backend.click_button(matched[0].label)
    await backend.wait_for_ready()
    await go_home(backend)


@pytest.mark.anyio
async def test_click_button_nonexistent(backend) -> None:
    """click_button raises ValueError for non-existent button."""
    await backend.enter_transaction("SE16")
    with pytest.raises(ValueError, match="not found"):
        await backend.click_button("NONEXISTENT_BUTTON_XYZ")
    await go_home(backend)


# ============================================================================
# click_tab
# ============================================================================


@pytest.mark.anyio
async def test_click_tab_nonexistent(backend) -> None:
    """click_tab raises ValueError for non-existent tab."""
    await backend.enter_transaction("SE16")
    with pytest.raises(ValueError, match="not found"):
        await backend.click_tab("NONEXISTENT_TAB_XYZ")
    await go_home(backend)


# ============================================================================
# select_dropdown
# ============================================================================


@pytest.mark.anyio
async def test_select_dropdown_nonexistent_field(backend) -> None:
    """select_dropdown returns failure for non-existent field."""
    await backend.enter_transaction("SE16")

    result = await backend.select_dropdown("NONEXISTENT_DROPDOWN_XYZ", "value")
    assert result.success is False
    assert result.error_message
    await go_home(backend)


# ============================================================================
# take_screenshot
# ============================================================================


@pytest.mark.anyio
async def test_take_screenshot_returns_bytes(backend) -> None:
    """take_screenshot returns non-empty PNG bytes."""
    screenshot = await backend.take_screenshot()
    assert isinstance(screenshot, bytes)
    assert len(screenshot) > 100, "Screenshot too small to be valid"
    # PNG magic bytes
    assert screenshot[:4] == b"\x89PNG", f"Not a PNG: {screenshot[:8]!r}"


@pytest.mark.anyio
async def test_take_screenshot_after_navigation(backend) -> None:
    """take_screenshot works after navigating to a transaction."""
    await backend.enter_transaction("SE16")
    screenshot = await backend.take_screenshot()
    assert isinstance(screenshot, bytes)
    assert len(screenshot) > 100
    await go_home(backend)
