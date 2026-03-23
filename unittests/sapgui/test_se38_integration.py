"""Integration tests for GuiAbapEditor against SE38.

Opens SE38 in display mode for report RSPARAM and tests editor
properties and methods. All tests are read-only.

Note: Tested on S/4 HANA. The AbapEditor COM surface may differ on R/3
(e.g. NumberOfLines may work on R/3 but not on S/4 where GetLineCount
is the correct method).
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


def _open_se38_display(session):
    """Navigate to SE38, display report RSPARAM."""
    from sapsucker.components.editor import GuiAbapEditor

    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/nSE38"
    session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)

    try:
        report_field = session.find_by_id("wnd[0]/usr/ctxtRS38M-PROGRAMM")
        report_field.text = "RSPARAM"
    except Exception:
        pytest.skip("Could not find SE38 program field")

    # Press F7 (Display)
    session.find_by_id("wnd[0]").send_v_key(7)
    time.sleep(2)

    # Find the editor
    for editor_id in [
        "wnd[0]/usr/cntlEDITOR/shellcont/shell",
        "wnd[0]/usr/cntlEDITOR1/shellcont/shell",
        "wnd[0]/usr/cntlGRID1/shellcont/shell",
    ]:
        try:
            elem = session.find_by_id(editor_id)
            if isinstance(elem, GuiAbapEditor):
                return elem
        except Exception:
            continue
    pytest.skip("Could not find ABAP editor in SE38")


@pytest.fixture
def se38_editor(sap_desktop_session):
    """Provide a GuiAbapEditor from SE38 displaying RSPARAM."""
    editor = _open_se38_display(sap_desktop_session)
    yield editor
    okcode = sap_desktop_session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/n"
    sap_desktop_session.find_by_id("wnd[0]").send_v_key(0)


class TestGuiAbapEditorProperties:
    def test_sub_type(self, se38_editor):
        """Editor sub_type should be 'AbapEditor'."""
        assert se38_editor.sub_type == "AbapEditor"

    def test_get_line_text(self, se38_editor):
        """Line 1 of RSPARAM contains the REPORT statement."""
        line1 = se38_editor.get_line_text(1)
        assert isinstance(line1, str)
        assert len(line1) > 0

    def test_get_line_text_line_zero(self, se38_editor):
        """Line 0 in AbapEditor is accessible (may be empty header)."""
        line0 = se38_editor.get_line_text(0)
        assert isinstance(line0, str)

    def test_changeable(self, se38_editor):
        """The changeable property should be a bool."""
        assert isinstance(se38_editor.changeable, bool)

    def test_type_is_gui_shell(self, se38_editor):
        """AbapEditor reports its type as GuiShell."""
        assert se38_editor.type == "GuiShell"

    def test_raw_com_get_line_count(self, se38_editor):
        """GetLineCount is the S/4 COM method for total line count.

        Uses raw COM because GuiAbapEditor has no wrapper for this yet —
        the existing number_of_lines property wraps NumberOfLines which
        may only work on R/3, not S/4. See issue #516.
        """
        count = se38_editor.com.GetLineCount()
        assert isinstance(count, int)
        assert count > 0


# ---------------------------------------------------------------------------
# New methods added in PR #521 (editor methods #475)
# ---------------------------------------------------------------------------


class TestGuiAbapEditorNewMethods:
    def test_first_visible_line_not_on_s4(self, se38_editor):
        """On S/4, FirstVisibleLine raises AttributeError on AbapEditor.

        The property exists on GuiTextedit but not on the S/4 AbapEditor
        COM object. This test documents the known limitation.
        """
        try:
            fvl = se38_editor.first_visible_line
            # If it works (R/3 or newer S/4), verify it's an int
            assert isinstance(fvl, int)
        except AttributeError:
            pytest.skip("FirstVisibleLine not available on S/4 AbapEditor")
