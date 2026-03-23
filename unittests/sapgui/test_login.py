"""Unit tests for SAP GUI desktop login/logoff helpers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from sapsucker._errors import SapConnectionError, SapGuiTimeoutError
from sapsucker.login import (
    _FALLBACK_SAPLOGON_PATH,
    _discover_saplogon_path,
    _handle_multiple_logon_popup,
    _wait_for_session,
    cleanup_ghost_connections,
    login,
    logoff,
)


def _make_mock_session(program: str = "SAPMSYST", sbar_text: str = "", message_type: str = "") -> MagicMock:
    """Create a mock GuiSession with info and find_by_id support."""
    session = MagicMock()
    session.info.program = program

    fields: dict[str, MagicMock] = {}

    def find_by_id(element_id: str, raise_error: bool = True) -> MagicMock | None:
        if element_id not in fields:
            if raise_error:
                raise Exception(f"Element {element_id} not found")
            return None
        return fields[element_id]

    session.find_by_id = find_by_id

    # Standard login fields
    for fid in [
        "wnd[0]/usr/txtRSYST-MANDT",
        "wnd[0]/usr/txtRSYST-BNAME",
        "wnd[0]/usr/pwdRSYST-BCODE",
        "wnd[0]/usr/txtRSYST-LANGU",
    ]:
        fields[fid] = MagicMock()

    # Main window
    wnd0 = MagicMock()
    fields["wnd[0]"] = wnd0

    # Status bar
    sbar = MagicMock()
    sbar.text = sbar_text
    sbar.message_type = message_type
    fields["wnd[0]/sbar"] = sbar

    session._fields = fields
    return session


@pytest.mark.skipif(sys.platform != "win32", reason="winreg only available on Windows")
class TestDiscoverSaplogonPath:
    """Tests for _discover_saplogon_path()."""

    def test_reads_path_from_registry(self):
        """Returns saplogon.exe path from the SAPsysdir registry value."""
        import winreg  # pylint: disable=import-outside-toplevel

        mock_key = MagicMock()
        mock_key.__enter__ = lambda s: mock_key
        mock_key.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(winreg, "OpenKey", return_value=mock_key) as mock_open,
            patch.object(winreg, "QueryValueEx", return_value=(r"D:\SAP\FrontEnd\SAPGUI", 1)),
        ):
            result = _discover_saplogon_path()

        assert result == r"D:\SAP\FrontEnd\SAPGUI\saplogon.exe"
        mock_open.assert_called_once_with(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\SAP\SAP Shared")

    def test_falls_back_when_registry_missing(self):
        """Returns fallback path when registry key does not exist."""
        import winreg  # pylint: disable=import-outside-toplevel

        with patch.object(winreg, "OpenKey", side_effect=OSError("Key not found")):
            result = _discover_saplogon_path()

        assert result == _FALLBACK_SAPLOGON_PATH


class TestLogin:
    """Tests for login()."""

    @patch("sapsucker.login._wait_for_session")
    @patch("sapsucker.SapGui")
    @patch("sapsucker.login.time")
    def test_happy_path(self, mock_time, mock_sap_gui_cls, mock_wait):
        """login() fills credentials, presses Enter, and returns session."""
        session = _make_mock_session(program="SAPMSYST")
        mock_wait.return_value = session

        # After pressing Enter, program changes (simulated by side_effect)
        call_count = 0

        def program_side_effect():
            nonlocal call_count
            call_count += 1
            # First call: SAPMSYST (triggers login), second+: SAPLSMTR_NAVIGATION
            if call_count <= 1:
                return "SAPMSYST"
            return "SAPLSMTR_NAVIGATION"

        type(session.info).program = property(lambda self: program_side_effect())

        result = login(
            connection_name="TEST",
            client="100",
            user="TESTUSER",
            password="secret",
            language="EN",
        )

        assert result is session
        mock_sap_gui_cls.connect.assert_called_once()
        session._fields["wnd[0]"].send_v_key.assert_called_once_with(0)

    @patch("sapsucker.login._wait_for_session")
    @patch("sapsucker.SapGui")
    @patch("sapsucker.login.time")
    def test_handles_multiple_logon_popup(self, mock_time, mock_sap_gui_cls, mock_wait):
        """login() handles the multiple logon popup by selecting OPT2."""
        session = _make_mock_session(program="SAPMSYST")
        mock_wait.return_value = session

        # Add popup window and OPT2 radio button
        popup = MagicMock()
        opt2 = MagicMock()
        session._fields["wnd[1]"] = popup
        session._fields["wnd[1]/usr/radMULTI_LOGON_OPT2"] = opt2

        call_count = 0

        def program_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return "SAPMSYST"
            return "SAPLSMTR_NAVIGATION"

        type(session.info).program = property(lambda self: program_side_effect())

        login(
            connection_name="TEST",
            client="100",
            user="TESTUSER",
            password="secret",
        )

        assert opt2.selected is True
        # send_v_key is called twice: once by _dismiss_system_message_popups (which
        # tries to dismiss it, sees it persists, and stops), then once by
        # _handle_multiple_logon_popup after selecting OPT2.
        assert popup.send_v_key.call_count == 2

    @patch("sapsucker.login._wait_for_session")
    @patch("sapsucker.SapGui")
    @patch("sapsucker.login.time")
    def test_raises_on_bad_credentials(self, mock_time, mock_sap_gui_cls, mock_wait):
        """login() raises SapConnectionError when login screen stays after Enter."""
        session = _make_mock_session(program="SAPMSYST", sbar_text="Login failed: bad password")
        mock_wait.return_value = session
        # Program stays SAPMSYST (login screen) after pressing Enter
        type(session.info).program = property(lambda self: "SAPMSYST")

        with pytest.raises(SapConnectionError, match="Login failed"):
            login(
                connection_name="TEST",
                client="100",
                user="TESTUSER",
                password="wrong",
            )

    @patch("sapsucker.login._wait_for_session")
    @patch("sapsucker.SapGui")
    @patch("sapsucker.login.time")
    def test_launches_sap_gui_when_connect_fails(self, mock_time, mock_sap_gui_cls, mock_wait):
        """login() launches SAP GUI when connect() raises SapConnectionError."""
        mock_sap_gui_cls.connect.side_effect = SapConnectionError("Not running")
        session = _make_mock_session(program="SAPLSMTR_NAVIGATION")
        mock_wait.return_value = session

        login(
            connection_name="TEST",
            client="100",
            user="TESTUSER",
            password="secret",
        )

        mock_sap_gui_cls.launch.assert_called_once()


class TestLogoff:
    """Tests for logoff()."""

    @patch("sapsucker.login.cleanup_ghost_connections")
    def test_closes_parent_connection(self, mock_cleanup):
        """logoff() closes the parent connection via CloseConnection()."""
        session = MagicMock()
        logoff(session)
        session.com.Parent.CloseConnection.assert_called_once()
        mock_cleanup.assert_called_once()

    @patch("sapsucker.login.cleanup_ghost_connections")
    def test_no_fallback_to_nex(self, mock_cleanup):
        """logoff() does NOT fall back to /nEX — it just swallows the error."""
        session = MagicMock()
        session.com.Parent.CloseConnection.side_effect = Exception("COM error")
        logoff(session)
        session.send_command.assert_not_called()
        mock_cleanup.assert_called_once()

    @patch("sapsucker.login.cleanup_ghost_connections")
    def test_handles_already_closed_session(self, mock_cleanup):
        """logoff() does not raise when session is already closed."""
        session = MagicMock()
        session.com.Parent.CloseConnection.side_effect = Exception("Closed")
        logoff(session)  # Should not raise
        mock_cleanup.assert_called_once()


class TestCleanupGhostConnections:
    """Tests for cleanup_ghost_connections()."""

    @patch("sapsucker.SapGui")
    def test_closes_ghost_connections(self, mock_sap_gui_cls):
        """Ghost connections (0 sessions) are closed."""
        ghost_conn = MagicMock()
        ghost_conn.Children.Count = 0

        app = mock_sap_gui_cls.connect.return_value
        app.com.Children.Count = 1
        app.com.Children.side_effect = lambda i: ghost_conn

        cleanup_ghost_connections()
        ghost_conn.CloseConnection.assert_called_once()

    @patch("sapsucker.SapGui")
    def test_keeps_healthy_connections(self, mock_sap_gui_cls):
        """Connections with sessions are NOT closed."""
        healthy_conn = MagicMock()
        healthy_conn.Children.Count = 1

        app = mock_sap_gui_cls.connect.return_value
        app.com.Children.Count = 1
        app.com.Children.side_effect = lambda i: healthy_conn

        cleanup_ghost_connections()
        healthy_conn.CloseConnection.assert_not_called()

    @patch("sapsucker.SapGui")
    def test_sap_gui_not_running_returns_silently(self, mock_sap_gui_cls):
        """When SAP GUI is not running, cleanup returns without error."""
        mock_sap_gui_cls.connect.side_effect = Exception("Not running")
        cleanup_ghost_connections()  # Should not raise


class TestHandleMultipleLogonPopup:
    """Tests for _handle_multiple_logon_popup()."""

    def test_selects_opt2_and_sends_enter(self):
        """_handle_multiple_logon_popup() selects OPT2 and presses Enter."""
        session = MagicMock()
        popup = MagicMock()
        opt2 = MagicMock()

        def find_by_id(element_id: str, raise_error: bool = True):
            if element_id == "wnd[1]":
                return popup
            if element_id == "wnd[1]/usr/radMULTI_LOGON_OPT2":
                return opt2
            return None

        session.find_by_id = find_by_id

        with patch("sapsucker.login.time"):
            _handle_multiple_logon_popup(session)

        assert opt2.selected is True
        popup.send_v_key.assert_called_once_with(0)

    def test_does_nothing_when_no_popup(self):
        """_handle_multiple_logon_popup() returns silently when no popup exists."""
        session = MagicMock()
        session.find_by_id.return_value = None

        _handle_multiple_logon_popup(session)

        # No send_v_key should be called — the session mock's find_by_id
        # returned None, so the function should return early


class TestWaitForSession:
    """Tests for _wait_for_session()."""

    def test_returns_first_session(self):
        """_wait_for_session() returns the first child when it's a GuiSession."""
        from sapsucker.components.session import GuiSession as GuiSessionCls

        conn = MagicMock()
        mock_session = MagicMock(spec=GuiSessionCls)

        conn.children.__len__ = lambda self: 1
        conn.children.__getitem__ = lambda self, i: mock_session

        result = _wait_for_session(conn, timeout=2)
        assert result is mock_session

    def test_raises_timeout(self):
        """_wait_for_session() raises SapGuiTimeoutError when no session appears."""
        conn = MagicMock()
        conn.children.__len__ = lambda self: 0

        with pytest.raises(SapGuiTimeoutError, match="No session available"):
            _wait_for_session(conn, timeout=1)
