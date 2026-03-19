"""Integration tests for BP (Business Partner) — BDT screen support.

Requires SAP GUI with BP transaction access.
Verifies that BDT fields (invisible to standard dump_tree) are now
discoverable and interactable via the improved COM tools.
"""

import pytest

from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap

pytestmark = [skip_not_sap, skip_no_creds]


@pytest.mark.anyio
async def test_bp_snapshot_shows_fields(backend):
    """sap_com_snapshot on BP detail screen returns BDT fields."""
    await backend.enter_transaction("BP")
    await backend.press_key("F5")  # Create person

    snapshot = await backend.get_snapshot()
    snapshot_text = str(snapshot)
    # BDT fields should now appear in the snapshot (BUS_JOEL on create screen,
    # BUT000 on detail screen — either confirms the BDT fallback works)
    assert (
        "BUS_JOEL" in snapshot_text or "BUT000" in snapshot_text
    ), f"BDT fields not found in snapshot. First 500 chars: {snapshot_text[:500]}"
    await go_home(backend)


@pytest.mark.anyio
async def test_bp_discover_fields_returns_fields(backend):
    """sap_discover_fields on BP detail screen returns > 0 fields."""
    await backend.enter_transaction("BP")
    await backend.press_key("F5")

    fields = await backend.discover_fields()
    assert len(fields) > 0, "discover_fields returned 0 fields on BP detail screen"
    await go_home(backend)


@pytest.mark.anyio
async def test_bp_com_evaluate_find_by_name_read(backend):
    """sap_com_evaluate with FindByName can read a BDT field."""
    from sapwebguimcp.tools.com_tools import ComOperationInput, FindByNameRef, _execute_single_op

    await backend.enter_transaction("BP")
    await backend.press_key("F5")

    session = backend._require_session()
    op = ComOperationInput(
        element_id="wnd[0]/usr",
        action="get",
        property_or_method="Text",
        find_by_name=FindByNameRef(name="BUT000-NAME_LAST", type_name="GuiTextField"),
    )

    result = await backend._com.run(lambda: _execute_single_op(session, op))
    assert result.success, f"FindByName read failed: {result.error}"
    await go_home(backend)


@pytest.mark.anyio
async def test_bp_com_evaluate_find_by_name_write(backend):
    """sap_com_evaluate with FindByName can write a BDT field."""
    from sapwebguimcp.tools.com_tools import ComOperationInput, FindByNameRef, _execute_single_op

    await backend.enter_transaction("BP")
    await backend.press_key("F5")

    session = backend._require_session()
    op = ComOperationInput(
        element_id="wnd[0]/usr",
        action="set",
        property_or_method="Text",
        args=["TestName"],
        find_by_name=FindByNameRef(name="BUT000-NAME_LAST", type_name="GuiTextField"),
    )

    result = await backend._com.run(lambda: _execute_single_op(session, op))
    assert result.success, f"FindByName write failed: {result.error}"
    assert '"TestName"' in (result.result or ""), f"Value not written back: {result.result}"
    await go_home(backend)


@pytest.mark.anyio
async def test_bp_fill_form_with_labels(backend):
    """sap_fill_form fills BP fields by label including composite labels."""
    await backend.enter_transaction("BP")
    await backend.press_key("F5")
    await backend.wait(1000)
    await backend.press_key("Enter")
    await backend.wait(1000)

    result = await backend.fill_form({"Nachname": "IntegTest", "Vorname": "Max", "Land": "DE"})
    assert result.success, f"fill_form failed: {result.error}"
    assert "Nachname" in result.filled
    assert "Vorname" in result.filled
    assert "Land" in result.filled
    assert len(result.not_found) == 0, f"Fields not found: {result.not_found}"
    await go_home(backend)


@pytest.mark.anyio
async def test_bp_fill_form_with_dropdown(backend):
    """sap_fill_form sets dropdown fields (Anrede) by display text."""
    await backend.enter_transaction("BP")
    await backend.press_key("F5")
    await backend.wait(1000)
    await backend.press_key("Enter")
    await backend.wait(1000)

    result = await backend.fill_form(
        {
            "Anrede": "Herr",
            "Vorname": "DropdownTest",
            "Nachname": "Integration",
        }
    )
    assert result.success, f"fill_form failed: {result.error}"
    assert "Anrede" in result.filled, f"Anrede not filled. Errors: {result.errors}"
    assert "Vorname" in result.filled
    assert "Nachname" in result.filled
    assert len(result.not_found) == 0, f"Fields not found: {result.not_found}"
    assert len(result.errors) == 0, f"Errors: {result.errors}"
    await go_home(backend)


@pytest.mark.anyio
async def test_se16_regression(backend):
    """SE16 still works after dump_tree changes (regression check)."""
    await backend.enter_transaction("SE16")
    fields = await backend.discover_fields()
    assert len(fields) > 0, "discover_fields returned 0 fields on SE16"
    await go_home(backend)
