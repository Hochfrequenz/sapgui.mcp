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
        if len(app.connections) == 0:
            return False
        conn = app.connections[0]
        if len(conn.children) == 0:
            return False
        return True
    except Exception:
        return False


skip_no_sap = pytest.mark.skipif(not _sap_gui_available(), reason="SAP GUI not running")


def _get_session():
    """Helper: connect and return a wrapped GuiSession for the first session."""
    from sapwebguimcp.sapgui import SapGui

    app = SapGui.connect()
    conn = app.connections[0]
    return conn.children[0]


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
    assert len(app.connections) > 0


@skip_no_sap
def test_connection_has_sessions():
    from sapwebguimcp.sapgui import SapGui

    app = SapGui.connect()
    conn = app.connections[0]
    assert len(conn.children) > 0


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


# ---------------------------------------------------------------------------
# Login / Logoff integration tests
# ---------------------------------------------------------------------------


def _skip_no_connection_name():
    """Check whether SAP_CONNECTION_NAME is configured."""
    try:
        from sapwebguimcp.models.config import get_settings

        return not get_settings().sap_connection_name
    except Exception:
        return True


skip_no_login = pytest.mark.skipif(_skip_no_connection_name(), reason="SAP_CONNECTION_NAME not set")


@skip_no_sap
@skip_no_login
def test_login_and_logoff():
    """Login with real credentials, verify session info, then logoff."""
    from sapwebguimcp.models.config import get_settings
    from sapwebguimcp.sapgui._login import login, logoff

    settings = get_settings()
    session = login(
        connection_name=settings.sap_connection_name,
        client=settings.sap_mandant,
        user=settings.sap_user,
        password=settings.sap_password,
        language=settings.sap_language,
    )
    try:
        assert session.info.system_name != ""
        assert session.info.user.upper() == settings.sap_user.upper()
    finally:
        logoff(session)


@skip_no_sap
@skip_no_login
def test_login_handles_easy_access():
    """After login, session should be at Easy Access (not the login screen)."""
    from sapwebguimcp.models.config import get_settings
    from sapwebguimcp.sapgui._login import login, logoff

    settings = get_settings()
    session = login(
        connection_name=settings.sap_connection_name,
        client=settings.sap_mandant,
        user=settings.sap_user,
        password=settings.sap_password,
        language=settings.sap_language,
    )
    try:
        # After successful login we should NOT be on the login dynpro
        assert session.info.program != "SAPMSYST"
        # Typically SESSION_MANAGER or SAPLSMTR_NAVIGATION
        assert session.info.transaction in ("SESSION_MANAGER", "S000", "")
    finally:
        logoff(session)
