"""Exploratory integration tests for SE18/SE19 using generic tools.

Validates that the generic discover_fields/set_radio_button/click_button/fill_field
tools work for BAdI transactions without SE18/SE19-specific code.
"""

import sys

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_se18_discover_shows_full_screen_structure(backend):
    """SE18: discover_fields returns radios, text fields, and pushbuttons."""
    await backend.enter_transaction("SE18")
    await backend.wait_for_ready()

    fields = await backend.discover_fields()
    types = {f.type for f in fields}

    # Must see all three element types
    assert "GuiRadioButton" in types, f"Missing radios. Types: {types}"
    assert "GuiCTextField" in types, f"Missing text fields. Types: {types}"
    assert "GuiButton" in types, f"Missing buttons. Types: {types}"

    # Radio buttons should have meaningful labels
    radios = [f for f in fields if f.type == "GuiRadioButton"]
    assert len(radios) >= 2, f"SE18 should have at least 2 radios, got {len(radios)}"
    radio_labels = {r.label for r in radios}
    assert len(radio_labels) == 2, f"Radio labels should be distinct: {radio_labels}"

    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se18_radio_then_display_badi(backend):
    """SE18: switch radio to BAdI-Name, fill, click Display — navigate to definition."""
    await backend.enter_transaction("SE18")
    await backend.wait_for_ready()

    # Select the BAdI-Name radio (DE: "BAdI-Name", EN: "BAdI Name")
    radio_selected = False
    for label in ["BAdI-Name", "BAdI Name"]:
        try:
            await backend.set_radio_button(label)
            radio_selected = True
            break
        except ValueError:
            continue
    assert radio_selected, "Could not find BAdI radio button (tried 'BAdI-Name', 'BAdI Name')"

    await backend.wait_for_ready()

    # Fill BAdI name field — uses element name as label, resolved via
    # find_field_by_label's name-prefix strategy (ctxtG_BADINAME).
    await backend.fill_field("G_BADINAME", "BADI_SD_SALES")

    # Click Display button (DE: "Anzeigen", EN: "Display")
    button_clicked = False
    for label in ["Anzeigen", "Display"]:
        try:
            await backend.click_button(label)
            button_clicked = True
            break
        except ValueError:
            continue
    assert button_clicked, "Could not find Display button (tried 'Anzeigen', 'Display')"

    await backend.wait_for_ready()

    # Verify we navigated to the BAdI definition screen
    info = await backend.get_screen_info()
    assert "BADI_SD_SALES" in info.title, f"Expected BADI_SD_SALES in title, got: {info.title}"

    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se18_enhancement_spot_display(backend):
    """SE18: fill Enhancement Spot name (default radio), click Display."""
    await backend.enter_transaction("SE18")
    await backend.wait_for_ready()

    # Default radio is already "Erweiterungsspot", so G_ENHSPOTNAME is changeable.
    # BADI_SD_SALES is both a valid Enhancement Spot name and BAdI name on standard
    # SAP systems (migrated classic BAdI creates a spot with the same name).
    await backend.fill_field("G_ENHSPOTNAME", "BADI_SD_SALES")

    # Click Display
    button_clicked = False
    for label in ["Anzeigen", "Display"]:
        try:
            await backend.click_button(label)
            button_clicked = True
            break
        except ValueError:
            continue
    assert button_clicked, "Could not find Display button (tried 'Anzeigen', 'Display')"

    await backend.wait_for_ready()

    info = await backend.get_screen_info()
    assert "BADI_SD_SALES" in info.title, f"Expected BADI_SD_SALES in title, got: {info.title}"

    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se19_discover_shows_full_screen_structure(backend):
    """SE19: discover_fields returns both radio groups, fields, and buttons."""
    await backend.enter_transaction("SE19")
    await backend.wait_for_ready()

    fields = await backend.discover_fields()
    types = {f.type for f in fields}

    assert "GuiRadioButton" in types, f"Missing radios. Types: {types}"
    assert "GuiCTextField" in types, f"Missing text fields. Types: {types}"
    assert "GuiButton" in types, f"Missing buttons. Types: {types}"

    # SE19 has 4 radio buttons (2 per section: New/Classic x Edit/Create)
    radios = [f for f in fields if f.type == "GuiRadioButton"]
    assert len(radios) >= 4, f"SE19 should have at least 4 radios, got {len(radios)}"

    await go_home(backend)
