"""Exploratory tests: reproduce popup/modal dialog issues (#600, #609).

Run one at a time:
  pytest unittests/desktop/test_popup_rework_exploration.py::test_NAME -v -s
"""

from __future__ import annotations

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap


@pytest.fixture(autouse=True)
async def _cleanup_popups_and_go_home(backend):
    """Ensure popups are dismissed and SAP returns to Easy Access after each test."""
    yield
    # Dismiss any remaining popups (wnd[2], wnd[1])
    for _ in range(3):
        popup = await backend.check_popup()
        if popup is None:
            break
        try:
            await backend.dismiss_popup(use_close_button=True)
            await backend.wait(200)
        except Exception:
            break
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_01_discover_se21_fields(backend):
    """Step 1: Just discover what fields SE21 has on its initial screen."""
    await backend.enter_transaction("SE21")
    await backend.wait_for_ready()

    fields = await backend.discover_fields()
    print(f"\n=== SE21 discover_fields ({len(fields)}) ===")
    for f in fields:
        print(f"  {f.selector} | label={f.label} | type={f.type}")

    form = await backend.get_form_fields()
    print(f"\n=== SE21 get_form_fields ({len(form.fields)}) ===")
    for f in form.fields:
        print(f"  {f.id} | {f.label} | type={f.field_type} | val={f.current_value!r}")

    buttons = await backend.discover_buttons()
    print(f"\n=== SE21 buttons ({len(buttons)}) ===")
    for b in buttons:
        print(f"  {b.id} | {b.label}")


@skip_no_sap
@pytest.mark.anyio
async def test_02_se21_trigger_popup(backend):
    """Step 2: Fill SE21 and trigger the create popup, then explore wnd[1]."""
    await backend.enter_transaction("SE21")
    await backend.wait_for_ready()

    session = backend.require_session()

    # Fill package name via fill_form (discovered label from test_01)
    form = await backend.get_form_fields()
    text_fields = [f for f in form.fields if str(f.field_type) == "text"]
    print(f"\n  Text fields: {[f.label for f in text_fields]}")
    assert text_fields, "SE21 should have at least one text field"
    await backend.fill_form({text_fields[0].label: "ZTEST_POPUP_XYZ99"})

    await backend.wait(300)
    # Enter doesn't trigger popup; F5 (= click "Anlegen") does
    await backend.press_key("Enter")
    await backend.wait(500)

    popup = await backend.check_popup()
    print(f"\n=== After Enter: popup={popup is not None} ===")

    if popup is None:
        await backend.press_key("F5")
        await backend.wait(500)
        popup = await backend.check_popup()
        print(f"=== After F5: popup={popup is not None} ===")

    if popup:
        print(f"  type: {popup.popup_type}")
        print(f"  message: {popup.message}")
        print(f"  buttons: {[(b.label, b.id) for b in popup.buttons]}")

    # Manually explore wnd[1] via COM to see what's there
    def _explore_wnd1():
        wnd1 = session.find_by_id("wnd[1]", raise_error=False)
        if wnd1 is None:
            return None
        title = str(wnd1.text)
        tree = wnd1.dump_tree()
        from sapguimcp.backend.desktop import _flatten

        flat = _flatten(tree)
        return {
            "title": title,
            "elements": [
                {
                    "id": e.id,
                    "type": e.type,
                    "type_num": e.type_as_number,
                    "name": e.name,
                    "text": e.text,
                }
                for e in flat
            ],
        }

    wnd1_data = await backend.com.run(_explore_wnd1)
    if wnd1_data:
        print(f"\n=== wnd[1] contents (what tools MISS) ===")
        print(f"  title: {wnd1_data['title']}")
        for e in wnd1_data["elements"]:
            marker = ""
            if e["type_num"] in (31, 32, 33):
                marker = " [INPUT]"
            elif e["type_num"] == 40:
                marker = " [BUTTON]"
            elif e["type_num"] == 34:
                marker = " [DROPDOWN]"
            elif e["type_num"] == 42:
                marker = " [CHECKBOX]"
            print(f"    {e['id']} | {e['type']}[{e['name']}] = {e['text']!r}{marker}")
    else:
        print("\n  wnd[1] not found")

    # Show what standard tools see with popup open (wnd[0] only)
    print(f"\n=== What tools see WITH popup open ===")
    form2 = await backend.get_form_fields()
    print(f"  get_form_fields: {len(form2.fields)} fields")
    fields2 = await backend.discover_fields()
    print(f"  discover_fields: {len(fields2)} fields")

    # Verify the fix: tools now see popup fields
    assert popup is not None, "Expected SE21 create to open a popup"
    assert wnd1_data is not None, "Expected wnd[1] to exist"
    assert len(form2.fields) > 0, "get_form_fields should see wnd[1] fields"
    assert len(fields2) > 0, "discover_fields should see wnd[1] fields"


@skip_no_sap
@pytest.mark.anyio
async def test_03_se38_create_popup(backend):
    """Step 3: SE38 create new report triggers confirmation popup."""
    await backend.enter_transaction("SE38")
    await backend.wait_for_ready()

    session = backend.require_session()

    # Fill report name directly via COM
    async def _fill_report():
        def _do():
            field = session.find_by_id("wnd[0]/usr/ctxtRS38M-PROGRAMM", raise_error=False)
            if field is None:
                return False
            field.text = "ZTEST_POPUP_NONEXIST_99"
            return True

        return await backend.com.run(_do)

    ok = await _fill_report()
    if not ok:
        form = await backend.get_form_fields()
        print(f"  SE38 fields: {[(f.label, f.id) for f in form.fields]}")
        if form.fields:
            await backend.fill_form({form.fields[0].label: "ZTEST_POPUP_NONEXIST_99"})
            ok = True

    assert ok, "Could not fill SE38 report name"
    await backend.wait(200)

    # F5 = Create → should trigger "Program does not exist. Create?" popup
    await backend.press_key("F5")
    await backend.wait(500)

    popup = await backend.check_popup()
    print(f"\n=== SE38 after F5 (Create) ===")
    print(f"  popup: {popup is not None}")
    if popup:
        print(f"  type: {popup.popup_type}")
        print(f"  message: {popup.message}")
        print(f"  buttons: {[(b.label, b.id) for b in popup.buttons]}")

    # Explore wnd[1]
    def _explore():
        wnd1 = session.find_by_id("wnd[1]", raise_error=False)
        if wnd1 is None:
            return None
        tree = wnd1.dump_tree()
        from sapguimcp.backend.desktop import _flatten

        return [
            {"id": e.id, "type": e.type, "type_num": e.type_as_number, "name": e.name, "text": e.text}
            for e in _flatten(tree)
        ]

    elems = await backend.com.run(_explore)
    if elems:
        print(f"\n=== wnd[1] elements ===")
        for e in elems:
            print(f"    {e['id']} | {e['type']}({e['type_num']})[{e['name']}] = {e['text']!r}")

    assert popup is not None, "Expected SE38 create to trigger a popup"


@skip_no_sap
@pytest.mark.anyio
async def test_04_fill_popup_field_e2e(backend):
    """End-to-end: fill a field INSIDE a popup dialog via fill_form.

    This proves #609 is fixed: fill_form targets the active window (wnd[1]).
    """
    await backend.enter_transaction("SE21")
    await backend.wait_for_ready()

    # Open the create popup
    form = await backend.get_form_fields()
    text_fields = [f for f in form.fields if str(f.field_type) == "text"]
    await backend.fill_form({text_fields[0].label: "ZTEST_POPUP_XYZ99"})
    await backend.wait(300)
    await backend.press_key("F5")
    await backend.wait(500)

    # Popup should be open — get_form_fields should return wnd[1] fields
    popup_form = await backend.get_form_fields()
    assert len(popup_form.fields) > 0, "Should see popup fields"
    print(f"\n=== Popup fields: {[f.label for f in popup_form.fields]} ===")

    # Find the "Kurzbeschreibung" (short description) field and fill it
    desc_fields = [f for f in popup_form.fields if "Kurzbeschreibung" in (f.label or "")]
    assert desc_fields, "Should find Kurzbeschreibung field in popup"

    # THIS is the critical test: fill_form targeting a popup field
    result = await backend.fill_form({"Kurzbeschreibung": "Test popup fill"})
    print(f"\n=== fill_form result: filled={result.filled}, not_found={result.not_found} ===")
    assert result.success, f"fill_form in popup should succeed, got: {result.error}"
    assert "Kurzbeschreibung" in result.filled, "Kurzbeschreibung should be in filled list"

    # Verify the value was actually set by re-reading
    popup_form2 = await backend.get_form_fields()
    desc_field = [f for f in popup_form2.fields if "Kurzbeschreibung" in (f.label or "")][0]
    assert (
        desc_field.current_value == "Test popup fill"
    ), f"Field value should be 'Test popup fill', got '{desc_field.current_value}'"
    print(f"  Verified: Kurzbeschreibung = '{desc_field.current_value}'")


@skip_no_sap
@pytest.mark.anyio
async def test_05_press_key_closes_popup(backend):
    """End-to-end: press Escape on popup closes it, active_window returns to wnd[0].

    This proves #609 is fixed: keyboard targets the active window.
    """
    await backend.enter_transaction("SE21")
    await backend.wait_for_ready()

    # Open the create popup
    form = await backend.get_form_fields()
    text_fields = [f for f in form.fields if str(f.field_type) == "text"]
    await backend.fill_form({text_fields[0].label: "ZTEST_POPUP_XYZ99"})
    await backend.wait(300)
    await backend.press_key("F5")
    await backend.wait(500)

    # Verify popup is open
    popup = await backend.check_popup()
    assert popup is not None, "Popup should be open"

    # Press Escape — should close the popup and return to wnd[0]
    result = await backend.press_key("Escape")
    assert result.success, f"Escape should succeed, got: {result.error}"
    print(f"\n=== After Escape: active_window={result.active_window} ===")
    assert (
        result.active_window == "wnd[0]"
    ), f"After closing popup, active_window should be wnd[0], got {result.active_window}"

    # Verify popup is gone
    popup_after = await backend.check_popup()
    assert popup_after is None, "Popup should be closed after Escape"


@skip_no_sap
@pytest.mark.anyio
async def test_06_baseline_no_popup(backend):
    """Baseline: verify check_popup returns None on a normal screen."""
    await backend.enter_transaction("SE38")
    await backend.wait_for_ready()

    popup = await backend.check_popup()
    print(f"\n=== check_popup on clean screen: {popup} ===")
    assert popup is None
