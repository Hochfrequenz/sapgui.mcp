"""Tests for sapgui.__init__.py — SapGui facade."""

from unittest.mock import MagicMock, patch


class TestSapGuiConnect:
    """Tests for SapGui.connect()."""

    @patch("sapsucker._com._connect_to_running_sap_gui")
    def test_delegates_to_connect_helper(self, mock_connect):
        app = MagicMock()
        mock_connect.return_value = app

        from sapsucker import SapGui

        result = SapGui.connect()
        assert result is app
        mock_connect.assert_called_once()


class TestSapGuiLaunch:
    """Tests for SapGui.launch()."""

    @patch("sapsucker._com._wait_for_sap_gui")
    @patch("sapsucker.subprocess.Popen")
    def test_launches_exe_and_waits(self, mock_popen, mock_wait):
        app = MagicMock()
        mock_wait.return_value = app

        from sapsucker import SapGui

        result = SapGui.launch("saplogon.exe", timeout=10)
        assert result is app
        mock_popen.assert_called_once_with(["saplogon.exe"])
        mock_wait.assert_called_once_with(timeout=10)

    @patch("sapsucker._com._wait_for_sap_gui")
    @patch("sapsucker.subprocess.Popen")
    def test_passes_connection_string(self, mock_popen, mock_wait):
        app = MagicMock()
        mock_wait.return_value = app

        from sapsucker import SapGui

        result = SapGui.launch("saplogon.exe", connection_string="/H/myserver/S/3200")
        assert result is app
        mock_popen.assert_called_once_with(["saplogon.exe", "-command", "/H/myserver/S/3200"])
