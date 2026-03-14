"""Tests for _com.py — low-level COM helpers."""

from unittest.mock import MagicMock, patch

import pytest

from sapwebguimcp.sapgui._errors import SapConnectionError, SapGuiTimeoutError, ScriptingDisabledError


class TestConnectToRunningSapGui:
    """Tests for _connect_to_running_sap_gui."""

    @patch("sapwebguimcp.sapgui._com.pythoncom")
    @patch("sapwebguimcp.sapgui._com.win32com")
    def test_returns_gui_application_on_success(self, mock_win32com, mock_pythoncom):
        engine = MagicMock()
        rot_entry = MagicMock()
        rot_entry.GetScriptingEngine = engine
        mock_win32com.client.GetObject.return_value = rot_entry

        from sapwebguimcp.sapgui._com import _connect_to_running_sap_gui
        from sapwebguimcp.sapgui.components.application import GuiApplication

        result = _connect_to_running_sap_gui()

        assert isinstance(result, GuiApplication)
        assert result._com is engine
        mock_pythoncom.CoInitialize.assert_called_once()
        mock_win32com.client.GetObject.assert_called_once_with("SAPGUI")

    @patch("sapwebguimcp.sapgui._com.pythoncom")
    @patch("sapwebguimcp.sapgui._com.win32com")
    def test_raises_connection_error_when_not_running(self, mock_win32com, mock_pythoncom):
        mock_win32com.client.GetObject.side_effect = Exception("Not running")

        from sapwebguimcp.sapgui._com import _connect_to_running_sap_gui

        with pytest.raises(SapConnectionError, match="SAP GUI is not running"):
            _connect_to_running_sap_gui()

    @patch("sapwebguimcp.sapgui._com.pythoncom")
    @patch("sapwebguimcp.sapgui._com.win32com")
    def test_raises_scripting_disabled_when_engine_is_none(self, mock_win32com, mock_pythoncom):
        rot_entry = MagicMock()
        rot_entry.GetScriptingEngine = None
        mock_win32com.client.GetObject.return_value = rot_entry

        from sapwebguimcp.sapgui._com import _connect_to_running_sap_gui

        with pytest.raises(ScriptingDisabledError, match="Scripting engine not available"):
            _connect_to_running_sap_gui()

    @patch("sapwebguimcp.sapgui._com.pythoncom", None)
    @patch("sapwebguimcp.sapgui._com.win32com")
    def test_skips_coinitialize_when_pythoncom_is_none(self, mock_win32com):
        engine = MagicMock()
        rot_entry = MagicMock()
        rot_entry.GetScriptingEngine = engine
        mock_win32com.client.GetObject.return_value = rot_entry

        from sapwebguimcp.sapgui._com import _connect_to_running_sap_gui

        result = _connect_to_running_sap_gui()
        assert result._com is engine


class TestWaitForSapGui:
    """Tests for _wait_for_sap_gui."""

    @patch("sapwebguimcp.sapgui._com.time")
    @patch("sapwebguimcp.sapgui._com.pythoncom")
    @patch("sapwebguimcp.sapgui._com.win32com")
    def test_returns_immediately_on_first_success(self, mock_win32com, mock_pythoncom, mock_time):
        engine = MagicMock()
        rot_entry = MagicMock()
        rot_entry.GetScriptingEngine = engine
        mock_win32com.client.GetObject.return_value = rot_entry
        mock_time.monotonic.side_effect = [0.0, 1.0]

        from sapwebguimcp.sapgui._com import _wait_for_sap_gui

        result = _wait_for_sap_gui(timeout=30)
        assert result._com is engine

    @patch("sapwebguimcp.sapgui._com.time")
    @patch("sapwebguimcp.sapgui._com.pythoncom")
    @patch("sapwebguimcp.sapgui._com.win32com")
    def test_raises_timeout_error_after_deadline(self, mock_win32com, mock_pythoncom, mock_time):
        mock_win32com.client.GetObject.side_effect = Exception("Not running")
        # First monotonic() call sets the deadline, subsequent ones exceed it
        mock_time.monotonic.side_effect = [0.0, 31.0]

        from sapwebguimcp.sapgui._com import _wait_for_sap_gui

        with pytest.raises(SapGuiTimeoutError, match="SAP GUI not available after 30s"):
            _wait_for_sap_gui(timeout=30)

    @patch("sapwebguimcp.sapgui._com.time")
    @patch("sapwebguimcp.sapgui._com.pythoncom")
    @patch("sapwebguimcp.sapgui._com.win32com")
    def test_retries_until_success(self, mock_win32com, mock_pythoncom, mock_time):
        engine = MagicMock()
        rot_entry_ok = MagicMock()
        rot_entry_ok.GetScriptingEngine = engine

        # First call fails, second succeeds
        mock_win32com.client.GetObject.side_effect = [Exception("Not running"), rot_entry_ok]
        mock_time.monotonic.side_effect = [0.0, 1.0, 2.0]

        from sapwebguimcp.sapgui._com import _wait_for_sap_gui

        result = _wait_for_sap_gui(timeout=30)
        assert result._com is engine
        mock_time.sleep.assert_called_once_with(1)
