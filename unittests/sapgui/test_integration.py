"""Integration tests that require a running SAP GUI instance.

These tests are skipped on non-Windows platforms and when SAP GUI is not available.
"""

import sys
import time

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


def _sap_gui_running():
    """Check SAP GUI is running (SAP Logon open), regardless of active connections."""
    try:
        from sapwebguimcp.sapgui import SapGui

        app = SapGui.connect()
        return app is not None
    except Exception:
        return False


skip_no_sap = pytest.mark.skipif(not _sap_gui_available(), reason="SAP GUI not running")
skip_no_sap_logon = pytest.mark.skipif(not _sap_gui_running(), reason="SAP GUI not running")


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


def _login_creds_configured():
    """Check whether all SAP login credentials are configured."""
    try:
        from dotenv import load_dotenv

        from sapwebguimcp.models.config import get_settings

        load_dotenv()
        s = get_settings()
        return bool(s.sap_connection_name and s.sap_user and s.sap_password and s.sap_mandant)
    except Exception:
        return False


skip_no_login_creds = pytest.mark.skipif(not _login_creds_configured(), reason="SAP login credentials not configured")


@skip_no_sap_logon
@skip_no_login_creds
def test_login_and_logoff():
    """Login with real credentials, verify session info, then logoff."""
    from dotenv import load_dotenv

    from sapwebguimcp.models.config import get_settings
    from sapwebguimcp.sapgui._login import login, logoff

    load_dotenv()
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


@skip_no_sap_logon
@skip_no_login_creds
def test_login_handles_easy_access():
    """After login, session should be at Easy Access (not the login screen)."""
    from dotenv import load_dotenv

    from sapwebguimcp.models.config import get_settings
    from sapwebguimcp.sapgui._login import login, logoff

    load_dotenv()
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


# ---------------------------------------------------------------------------
# Multi-mode / multi-connection integration tests
# ---------------------------------------------------------------------------


@skip_no_sap_logon
@skip_no_login_creds
def test_create_additional_mode():
    """Opening a new mode (/o) creates a session within the SAME connection."""
    from dotenv import load_dotenv

    from sapwebguimcp.sapgui import SapGui
    from sapwebguimcp.sapgui._login import cleanup_ghost_connections, login

    load_dotenv()

    from sapwebguimcp.models.config import get_settings

    settings = get_settings()

    session1 = login(
        connection_name=settings.sap_connection_name,
        client=settings.sap_mandant,
        user=settings.sap_user,
        password=settings.sap_password,
        language=settings.sap_language,
    )
    try:
        # session1 is on con[N]/ses[0]
        conn_id = session1.id.rsplit("/ses[", 1)[0]  # e.g. "/app/con[0]"

        # Create a new mode within the SAME connection
        session1.create_session()
        time.sleep(2)

        # The new session should be on the same connection
        app = SapGui.connect()
        # Find our connection
        for i in range(len(app.connections)):
            conn = app.connections[i]
            if conn.id == conn_id:
                # Should now have 2 sessions
                assert len(conn.children) == 2, f"Expected 2 sessions, got {len(conn.children)}"
                break
        else:
            pytest.fail(f"Connection {conn_id} not found")
    finally:
        # Close the entire connection (all modes)
        try:
            session1.com.Parent.CloseConnection()
        except Exception:
            pass
        cleanup_ghost_connections()


@skip_no_sap_logon
@skip_no_login_creds
def test_two_connections_with_modes():
    """Two separate connections, each with multiple modes -- full matrix."""
    from dotenv import load_dotenv

    from sapwebguimcp.models.config import get_settings
    from sapwebguimcp.sapgui._login import cleanup_ghost_connections, login

    load_dotenv()
    settings = get_settings()

    creds = dict(
        connection_name=settings.sap_connection_name,
        client=settings.sap_mandant,
        user=settings.sap_user,
        password=settings.sap_password,
        language=settings.sap_language,
    )

    # Login 1 (new connection)
    s1 = login(**creds)
    conn1_id = s1.id.rsplit("/ses[", 1)[0]

    # Login 2 (new connection, triggers multiple logon popup)
    s2 = login(**creds)
    conn2_id = s2.id.rsplit("/ses[", 1)[0]

    try:
        assert conn1_id != conn2_id, "Should be different connections"

        # Both should be logged in
        assert s1.info.user != ""
        assert s2.info.user != ""
    finally:
        try:
            s2.com.Parent.CloseConnection()
        except Exception:
            pass
        try:
            s1.com.Parent.CloseConnection()
        except Exception:
            pass
        cleanup_ghost_connections()
