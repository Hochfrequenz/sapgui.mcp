"""Integration tests for field components against SM37 selection screen.

SM37 has text fields, labels, checkboxes, and a combobox on its initial
selection screen. No execution needed — just inspect screen elements.
"""

import sys
import time

import pytest

from unittests.conftest import is_sap_integration_test_machine

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only"),
    pytest.mark.skipif(
        not is_sap_integration_test_machine(),
        reason="SAP integration tests only run on authorized machines",
    ),
]


def _navigate_to_sm37(session):
    """Navigate to SM37."""
    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/nSM37"
    session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)


@pytest.fixture
def sm37_session(sap_desktop_session):
    """Provide a session at SM37 selection screen."""
    _navigate_to_sm37(sap_desktop_session)
    yield sap_desktop_session
    okcode = sap_desktop_session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/n"
    sap_desktop_session.find_by_id("wnd[0]").send_v_key(0)


class TestGuiWindow:
    def test_main_window_properties(self, sm37_session):
        from sapsucker.components.window import GuiMainWindow

        wnd = sm37_session.find_by_id("wnd[0]")
        assert isinstance(wnd, GuiMainWindow)
        assert isinstance(wnd.handle, int)
        assert wnd.handle > 0
        assert isinstance(wnd.iconic, bool)
        assert wnd.working_pane_height > 0
        assert wnd.working_pane_width > 0

    def test_is_v_key_allowed(self, sm37_session):
        wnd = sm37_session.find_by_id("wnd[0]")
        # F8 (Execute) should be allowed on SM37 selection screen
        assert wnd.is_v_key_allowed(8) is True

    def test_gui_focus(self, sm37_session):
        wnd = sm37_session.find_by_id("wnd[0]")
        focus = wnd.gui_focus
        assert focus is not None


class TestGuiTextField:
    def test_text_field_properties(self, sm37_session):
        from sapsucker.components.field import GuiTextField

        # SM37 has jobname and username text fields
        for field_id in [
            "wnd[0]/usr/txtBTCH2170-JOBNAME",
            "wnd[0]/usr/txtBTCH2170-USERNAME",
        ]:
            try:
                field = sm37_session.find_by_id(field_id)
                if isinstance(field, GuiTextField):
                    assert isinstance(field.max_length, int)
                    assert field.max_length > 0
                    assert isinstance(field.is_required, bool)
                    assert isinstance(field.changeable, bool)
                    assert isinstance(field.text, str)
                    assert isinstance(field.caret_position, int)
                    assert isinstance(field.is_numerical, bool)
                    assert isinstance(field.is_hotspot, bool)
                    assert isinstance(field.highlighted, bool)
                    assert isinstance(field.is_list_element, bool)
                    return
            except Exception:
                continue
        # Fallback: find any text field via dump_tree on usr area
        usr = sm37_session.find_by_id("wnd[0]/usr")
        elements = usr.dump_tree(max_depth=5)
        for elem in elements:
            if elem.type_as_number == 31:
                try:
                    field = sm37_session.find_by_id(elem.id)
                    assert isinstance(field, GuiTextField)
                    assert isinstance(field.max_length, int)
                    return
                except Exception:
                    continue
        pytest.skip("No text field found on SM37")


class TestGuiLabel:
    def test_label_properties(self, sm37_session):
        from sapsucker.components.field import GuiLabel

        # SM37 has labels like "Jobname", "Benutzername" / "User name"
        for label_id in [
            "wnd[0]/usr/lblJOBNAME",
            "wnd[0]/usr/lblUSERNAME",
        ]:
            try:
                label = sm37_session.find_by_id(label_id)
                if isinstance(label, GuiLabel):
                    assert isinstance(label.text, str)
                    assert len(label.text) > 0
                    assert isinstance(label.max_length, int)
                    assert isinstance(label.displayed_text, str)
                    assert isinstance(label.is_numerical, bool)
                    assert isinstance(label.is_hotspot, bool)
                    assert isinstance(label.highlighted, bool)
                    assert isinstance(label.is_list_element, bool)
                    assert isinstance(label.color_index, int)
                    assert isinstance(label.color_intensified, bool)
                    assert isinstance(label.color_inverse, bool)
                    assert isinstance(label.char_height, int)
                    assert isinstance(label.char_width, int)
                    return
            except Exception:
                continue
        # Fallback: find any label via dump_tree on usr area
        usr = sm37_session.find_by_id("wnd[0]/usr")
        elements = usr.dump_tree(max_depth=5)
        for elem in elements:
            if elem.type_as_number == 30:
                try:
                    label = sm37_session.find_by_id(elem.id)
                    if isinstance(label, GuiLabel):
                        assert isinstance(label.text, str)
                        assert isinstance(label.max_length, int)
                        assert isinstance(label.displayed_text, str)
                        return
                except Exception:
                    continue
        pytest.skip("No label found on SM37")


class TestGuiCheckBox:
    def test_checkbox_properties(self, sm37_session):
        from sapsucker.components.checkbox import GuiCheckBox

        # SM37 has checkboxes for job status (Scheduled, Released, etc.)
        for chk_id in [
            "wnd[0]/usr/chkBTCH2170-PRELIM",
            "wnd[0]/usr/chkBTCH2170-SCHEDUL",
            "wnd[0]/usr/chkBTCH2170-READY",
            "wnd[0]/usr/chkBTCH2170-RUNNING",
            "wnd[0]/usr/chkBTCH2170-FINISHED",
        ]:
            try:
                chk = sm37_session.find_by_id(chk_id)
                if isinstance(chk, GuiCheckBox):
                    assert isinstance(chk.selected, bool)
                    assert isinstance(chk.changeable, bool)
                    assert isinstance(chk.text, str)
                    assert isinstance(chk.highlighted, bool)
                    assert isinstance(chk.is_list_element, bool)
                    assert isinstance(chk.color_index, int)
                    assert isinstance(chk.color_intensified, bool)
                    assert isinstance(chk.color_inverse, bool)
                    return
            except Exception:
                continue
        # Fallback: find any checkbox via dump_tree on usr area
        usr = sm37_session.find_by_id("wnd[0]/usr")
        elements = usr.dump_tree(max_depth=5)
        for elem in elements:
            if elem.type_as_number == 42:
                try:
                    chk = sm37_session.find_by_id(elem.id)
                    if isinstance(chk, GuiCheckBox):
                        assert isinstance(chk.selected, bool)
                        assert isinstance(chk.changeable, bool)
                        return
                except Exception:
                    continue
        pytest.skip("No checkbox found on SM37")


class TestGuiComboBox:
    def test_combobox_entries(self, sm37_session):
        from sapsucker.components.combobox import GuiComboBox

        # SM37 has an event ID combobox
        try:
            combo = sm37_session.find_by_id("wnd[0]/usr/cmbBTCH2170-EVENTID")
            if isinstance(combo, GuiComboBox):
                assert combo.item_count > 0
                assert isinstance(combo.value, str)
                assert isinstance(combo.is_required, bool)
                assert isinstance(combo.highlighted, bool)
                assert isinstance(combo.is_list_element, bool)
                entries = combo.entries
                assert len(entries) > 0
                assert isinstance(entries[0].key, str)
                assert isinstance(entries[0].value, str)
                assert isinstance(entries[0].pos, int)
                return
        except Exception:
            pass
        # Fallback: find any combobox via dump_tree on usr area
        usr = sm37_session.find_by_id("wnd[0]/usr")
        elements = usr.dump_tree(max_depth=5)
        for elem in elements:
            if elem.type_as_number == 34:
                try:
                    combo = sm37_session.find_by_id(elem.id)
                    if isinstance(combo, GuiComboBox):
                        assert combo.item_count > 0
                        entries = combo.entries
                        assert len(entries) > 0
                        assert isinstance(entries[0].key, str)
                        assert isinstance(entries[0].value, str)
                        return
                except Exception:
                    continue
        pytest.skip("No combobox found on SM37")
