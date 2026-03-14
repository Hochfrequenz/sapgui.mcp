"""Integration tests that require a running SAP GUI instance.

These tests are skipped on non-Windows platforms and when SAP GUI is not available.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only")


def _sap_gui_available():
    """Check that SAP GUI is running with at least one active connection and session."""
    try:
        from sapwebguimcp.sapgui import SapGui

        app = SapGui.connect()
        if app is None:
            return False
        conns = app.connections
        if conns.Count == 0:
            return False
        conn = conns.Item(0)
        if conn.Sessions.Count == 0:
            return False
        return True
    except Exception:
        return False


skip_no_sap = pytest.mark.skipif(not _sap_gui_available(), reason="SAP GUI not running")


@skip_no_sap
def test_connect_returns_gui_application():
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui.components.application import GuiApplication

    app = SapGui.connect()
    assert isinstance(app, GuiApplication)


@skip_no_sap
def test_application_has_connections():
    from sapwebguimcp.sapgui import SapGui

    app = SapGui.connect()
    conns = app.connections
    assert conns.count > 0


@skip_no_sap
def test_connection_has_sessions():
    from sapwebguimcp.sapgui import SapGui

    app = SapGui.connect()
    conn = app.connections.item(0)
    sessions = conn.sessions
    assert sessions.count > 0


@skip_no_sap
def test_session_info():
    from sapwebguimcp.sapgui import SapGui

    app = SapGui.connect()
    conn = app.connections.item(0)
    session = conn.sessions.item(0)
    info = session.info
    assert info.system_name != ""
    assert info.user != ""
    assert info.language != ""


@skip_no_sap
def test_find_main_window():
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui.components.window import GuiMainWindow

    app = SapGui.connect()
    conn = app.connections.item(0)
    session = conn.sessions.item(0)
    wnd = session.find_by_id("wnd[0]")
    assert isinstance(wnd, GuiMainWindow)


@skip_no_sap
def test_find_statusbar():
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui.components.statusbar import GuiStatusbar

    app = SapGui.connect()
    conn = app.connections.item(0)
    session = conn.sessions.item(0)
    sbar = session.find_by_id("wnd[0]/sbar")
    assert isinstance(sbar, GuiStatusbar)


@skip_no_sap
def test_find_okcode_field():
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui.components.okcode import GuiOkCodeField

    app = SapGui.connect()
    conn = app.connections.item(0)
    session = conn.sessions.item(0)
    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    assert isinstance(okcode, GuiOkCodeField)


@skip_no_sap
def test_find_by_id_returns_typed_wrappers():
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui.components.base import GuiComponent

    app = SapGui.connect()
    conn = app.connections.item(0)
    session = conn.sessions.item(0)
    elem = session.find_by_id("wnd[0]")
    # Should be a Python wrapper, not a raw COM object
    assert isinstance(elem, GuiComponent)
    assert hasattr(elem, "com")


@skip_no_sap
def test_dump_tree_on_main_window():
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui.models import ElementInfo

    app = SapGui.connect()
    conn = app.connections.item(0)
    session = conn.sessions.item(0)
    wnd = session.find_by_id("wnd[0]")
    tree = wnd.dump_tree(max_depth=2)
    assert isinstance(tree, list)
    assert len(tree) > 0
    assert isinstance(tree[0], ElementInfo)


@skip_no_sap
def test_read_statusbar_text():
    from sapwebguimcp.sapgui import SapGui

    app = SapGui.connect()
    conn = app.connections.item(0)
    session = conn.sessions.item(0)
    sbar = session.find_by_id("wnd[0]/sbar")
    # text should be a string (may be empty)
    assert isinstance(sbar.text, str)
