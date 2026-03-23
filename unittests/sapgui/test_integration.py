"""Integration tests for the pysapgui library.

Tests are skipped unless:
- Running on Windows (COM is Windows-only)
- Running on the authorized SAP test machine (same check as WebGUI tests)
- SAP credentials are configured in .env

The login tests auto-launch SAP Logon if it's not running — no manual
startup needed. The read-only tests (test_connect_*, test_find_*) require
an existing logged-in session.
"""

import sys
import time

import pytest
from dotenv import load_dotenv

from unittests.conftest import is_sap_integration_test_machine

# Skip everything on non-Windows
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only")

# Skip on non-authorized machines (same guard as WebGUI integration tests)
skip_not_sap_machine = pytest.mark.skipif(
    not is_sap_integration_test_machine(),
    reason="SAP integration tests only run on authorized machines",
)


def _has_active_session() -> bool:
    """Check if SAP GUI has at least one logged-in session (for read-only tests)."""
    try:
        from sapsucker import SapGui

        app = SapGui.connect()
        if len(app.connections) == 0:
            return False
        conn = app.connections[0]
        return len(conn.children) > 0
    except Exception:
        return False


def _login_creds_configured() -> bool:
    """Check whether all SAP login credentials are configured in .env."""
    try:
        load_dotenv()

        from sapwebguimcp.models.config import get_settings

        s = get_settings()
        return bool(s.sap_connection_name and s.sap_user and s.sap_password and s.sap_mandant)
    except Exception:
        return False


# Guards for different test categories
skip_no_active_session = pytest.mark.skipif(not _has_active_session(), reason="No active SAP GUI session")
skip_no_login_creds = pytest.mark.skipif(not _login_creds_configured(), reason="SAP login credentials not configured")


# ---------------------------------------------------------------------------
# Read-only tests (require an existing logged-in session)
# ---------------------------------------------------------------------------


def _get_session():
    """Helper: connect and return a wrapped GuiSession for the first session."""
    from sapsucker import SapGui

    app = SapGui.connect()
    conn = app.connections[0]
    return conn.children[0]


@skip_not_sap_machine
@skip_no_active_session
def test_connect_returns_gui_application():
    from sapsucker import SapGui
    from sapsucker.components.application import GuiApplication

    app = SapGui.connect()
    assert isinstance(app, GuiApplication)


@skip_not_sap_machine
@skip_no_active_session
def test_application_has_connections():
    from sapsucker import SapGui

    app = SapGui.connect()
    assert len(app.connections) > 0


@skip_not_sap_machine
@skip_no_active_session
def test_connection_has_sessions():
    from sapsucker import SapGui

    app = SapGui.connect()
    conn = app.connections[0]
    assert len(conn.children) > 0


@skip_not_sap_machine
@skip_no_active_session
def test_session_info():
    session = _get_session()
    info = session.info
    assert info.system_name != ""
    assert info.user != ""
    assert info.language != ""


@skip_not_sap_machine
@skip_no_active_session
def test_find_main_window():
    from sapsucker.components.window import GuiMainWindow

    session = _get_session()
    wnd = session.find_by_id("wnd[0]")
    assert isinstance(wnd, GuiMainWindow)


@skip_not_sap_machine
@skip_no_active_session
def test_find_statusbar():
    from sapsucker.components.statusbar import GuiStatusbar

    session = _get_session()
    sbar = session.find_by_id("wnd[0]/sbar")
    assert isinstance(sbar, GuiStatusbar)


@skip_not_sap_machine
@skip_no_active_session
def test_find_okcode_field():
    from sapsucker.components.okcode import GuiOkCodeField

    session = _get_session()
    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    assert isinstance(okcode, GuiOkCodeField)


@skip_not_sap_machine
@skip_no_active_session
def test_find_by_id_returns_typed_wrappers():
    from sapsucker.components.base import GuiComponent

    session = _get_session()
    elem = session.find_by_id("wnd[0]")
    assert isinstance(elem, GuiComponent)
    assert hasattr(elem, "com")


@skip_not_sap_machine
@skip_no_active_session
def test_dump_tree_on_main_window():
    from sapsucker.models import ElementInfo

    session = _get_session()
    wnd = session.find_by_id("wnd[0]")
    tree = wnd.dump_tree(max_depth=2)
    assert isinstance(tree, list)
    assert len(tree) > 0
    assert isinstance(tree[0], ElementInfo)


@skip_not_sap_machine
@skip_no_active_session
def test_read_statusbar_text():
    session = _get_session()
    sbar = session.find_by_id("wnd[0]/sbar")
    assert isinstance(sbar.text, str)


# ---------------------------------------------------------------------------
# Login / Logoff integration tests
#
# These auto-launch SAP Logon if not running. They only need credentials
# configured — no pre-existing session required.
# ---------------------------------------------------------------------------


@skip_not_sap_machine
@skip_no_login_creds
def test_login_and_logoff():
    """Login with real credentials, verify session info, then logoff."""
    from sapsucker.login import login, logoff
    from sapwebguimcp.models.config import get_settings

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


@skip_not_sap_machine
@skip_no_login_creds
def test_login_handles_easy_access():
    """After login, session should be at Easy Access (not the login screen)."""
    from sapsucker.login import login, logoff
    from sapwebguimcp.models.config import get_settings

    settings = get_settings()
    session = login(
        connection_name=settings.sap_connection_name,
        client=settings.sap_mandant,
        user=settings.sap_user,
        password=settings.sap_password,
        language=settings.sap_language,
    )
    try:
        assert session.info.program != "SAPMSYST"
        assert session.info.transaction in ("SESSION_MANAGER", "S000", "")
    finally:
        logoff(session)


# ---------------------------------------------------------------------------
# Multi-mode / multi-connection integration tests
#
# Tests the key distinction:
# - Connection = separate TCP link, separate login (open_connection)
# - Session/Mode = window within a connection, shared login (create_session / /o)
# ---------------------------------------------------------------------------


@skip_not_sap_machine
@skip_no_login_creds
def test_create_additional_mode():
    """Opening a new mode (/o) creates a session within the SAME connection."""
    from sapsucker import SapGui
    from sapsucker.login import cleanup_ghost_connections, login
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
        for i in range(len(app.connections)):
            conn = app.connections[i]
            if conn.id == conn_id:
                assert len(conn.children) == 2, f"Expected 2 sessions, got {len(conn.children)}"
                break
        else:
            pytest.fail(f"Connection {conn_id} not found")
    finally:
        try:
            session1.com.Parent.CloseConnection()
        except Exception:
            pass
        cleanup_ghost_connections()


@skip_not_sap_machine
@skip_no_login_creds
def test_two_connections_independent():
    """Two separate logins create independent connections (not modes)."""
    from sapsucker.login import cleanup_ghost_connections, login
    from sapwebguimcp.models.config import get_settings

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
