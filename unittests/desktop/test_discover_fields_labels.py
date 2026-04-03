"""Test that discover_fields populates labels and includes radios/buttons."""

import sys

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_discover_fields_has_labels_se16(backend):
    """SE16 initial screen fields should have labels (e.g. 'Tabellenname')."""
    await backend.enter_transaction("SE16")
    await backend.wait_for_ready()

    fields = await backend.discover_fields()
    assert len(fields) > 0, "SE16 should have at least one field"

    # At least one field must have a real label (not just the element name fallback)
    real_labels = [f for f in fields if f.label and f.label != f.name]
    assert len(real_labels) > 0, (
        f"Expected at least one field with a label from GuiLabel, got only name fallbacks: "
        f"{[(f.name, f.label) for f in fields]}"
    )

    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_discover_fields_includes_radio_buttons_se18(backend):
    """SE18 has radio buttons for Spot/BAdI mode — discover_fields should include them."""
    await backend.enter_transaction("SE18")
    await backend.wait_for_ready()

    fields = await backend.discover_fields()
    types = {f.type for f in fields}
    assert "GuiRadioButton" in types, f"Expected GuiRadioButton in discovered field types, got: {types}"

    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_discover_fields_includes_pushbuttons_se18(backend):
    """SE18 has Display/Change/Create pushbuttons — discover_fields should include them."""
    await backend.enter_transaction("SE18")
    await backend.wait_for_ready()

    fields = await backend.discover_fields()
    types = {f.type for f in fields}
    assert "GuiButton" in types, f"Expected GuiButton in discovered field types, got: {types}"

    # Verify the pushbuttons have labels
    buttons = [f for f in fields if f.type == "GuiButton"]
    labeled = [b for b in buttons if b.label and b.label.strip()]
    assert len(labeled) > 0, f"Expected pushbuttons with labels, got: {[b.name for b in buttons]}"

    await go_home(backend)
