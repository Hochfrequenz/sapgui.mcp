"""Integration tests for GuiShell, GuiToolbarControl, GuiHTMLViewer against SE80.

SE80 has:
- A toolbar at wnd[0]/shellcont/shell/shellcont[0]/shell (SubType=Toolbar)
- An HTMLViewer at wnd[0]/usr/cntlIMAGE/shellcont/shell (SubType=HTMLViewer)
- The tree is also a GuiShell (SubType=Tree) — tested in test_tree_integration.py
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


@pytest.fixture
def se80_session(sap_desktop_session):
    """Navigate to SE80 and yield the session."""
    okcode = sap_desktop_session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/nSE80"
    sap_desktop_session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)
    yield sap_desktop_session
    okcode = sap_desktop_session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/n"
    sap_desktop_session.find_by_id("wnd[0]").send_v_key(0)


class TestGuiShellBase:
    def test_shell_properties_on_toolbar(self, se80_session):
        """Test GuiShell base properties on the SE80 toolbar."""
        from sapsucker.components.shell import GuiShell

        toolbar = se80_session.find_by_id("wnd[0]/shellcont/shell/shellcont[0]/shell")
        assert isinstance(toolbar, GuiShell)
        assert toolbar.sub_type == "Toolbar"
        assert isinstance(toolbar.handle, int)
        assert toolbar.handle > 0
        assert isinstance(toolbar.drag_drop_supported, bool)


class TestGuiToolbarViaCom:
    def test_toolbar_button_access(self, se80_session):
        """Test toolbar button COM methods on SE80's toolbar shell.

        SE80's toolbar has SubType "Toolbar" (not "ToolbarControl"), so the
        factory returns GuiShell. We test the COM methods directly to verify
        they work — these are the same methods wrapped by GuiToolbarControl.
        """
        from sapsucker.components.shell import GuiShell

        toolbar = se80_session.find_by_id("wnd[0]/shellcont/shell/shellcont[0]/shell")
        assert isinstance(toolbar, GuiShell)

        # ButtonCount, GetButtonId, GetButtonText etc. are COM methods
        # available on any toolbar-type shell
        count = toolbar.com.ButtonCount
        assert isinstance(count, int)
        assert count > 0

        btn_id = str(toolbar.com.GetButtonId(0))
        assert isinstance(btn_id, str)

        btn_text = str(toolbar.com.GetButtonText(0))
        assert isinstance(btn_text, str)

        btn_type = toolbar.com.GetButtonType(0)
        assert isinstance(btn_type, (int, str))

        btn_enabled = bool(toolbar.com.GetButtonEnabled(0))
        assert isinstance(btn_enabled, bool)


class TestGuiHTMLViewer:
    def test_html_viewer_sub_type(self, se80_session):
        """Verify the HTML viewer is found and has correct sub_type."""
        from sapsucker.components.shell import GuiShell

        html = se80_session.find_by_id("wnd[0]/usr/cntlIMAGE/shellcont/shell")
        assert isinstance(html, GuiShell)
        assert html.sub_type == "HTMLViewer"
        assert isinstance(html.handle, int)
        assert html.handle > 0
