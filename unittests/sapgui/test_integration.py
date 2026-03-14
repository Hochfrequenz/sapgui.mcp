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
        if app.connections.Count == 0:
            return False
        conn = app.connections.Item(0)
        if conn.Children.Count == 0:
            return False
        return True
    except Exception:
        return False


skip_no_sap = pytest.mark.skipif(not _sap_gui_available(), reason="SAP GUI not running")


def _get_session():
    """Helper: connect and return a wrapped GuiSession for the first session."""
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui._factory import wrap_com_object

    app = SapGui.connect()
    conn_com = app.connections.Item(0)
    ses_com = conn_com.Children.Item(0)
    return wrap_com_object(ses_com)


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
    assert app.connections.Count > 0


@skip_no_sap
def test_connection_has_sessions():
    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui._factory import wrap_com_object

    app = SapGui.connect()
    conn = wrap_com_object(app.connections.Item(0))
    assert conn.children.Count > 0


@skip_no_sap
def test_session_info():
    session = _get_session()
    info = session.info
    assert info.system_name != ""
    assert info.user != ""
    assert info.language != ""


@skip_no_sap
def test_find_main_window():
    from sapwebguimcp.sapgui.components.window import GuiMainWindow

    session = _get_session()
    wnd = session.find_by_id("wnd[0]")
    assert isinstance(wnd, GuiMainWindow)


@skip_no_sap
def test_find_statusbar():
    from sapwebguimcp.sapgui.components.statusbar import GuiStatusbar

    session = _get_session()
    sbar = session.find_by_id("wnd[0]/sbar")
    assert isinstance(sbar, GuiStatusbar)


@skip_no_sap
def test_find_okcode_field():
    from sapwebguimcp.sapgui.components.okcode import GuiOkCodeField

    session = _get_session()
    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    assert isinstance(okcode, GuiOkCodeField)


@skip_no_sap
def test_find_by_id_returns_typed_wrappers():
    from sapwebguimcp.sapgui.components.base import GuiComponent

    session = _get_session()
    elem = session.find_by_id("wnd[0]")
    assert isinstance(elem, GuiComponent)
    assert hasattr(elem, "com")


@skip_no_sap
def test_dump_tree_on_main_window():
    from sapwebguimcp.sapgui.models import ElementInfo

    session = _get_session()
    wnd = session.find_by_id("wnd[0]")
    tree = wnd.dump_tree(max_depth=2)
    assert isinstance(tree, list)
    assert len(tree) > 0
    assert isinstance(tree[0], ElementInfo)


@skip_no_sap
def test_read_statusbar_text():
    session = _get_session()
    sbar = session.find_by_id("wnd[0]/sbar")
    assert isinstance(sbar.text, str)
