"""Tests for GuiConnection component."""

from unittest.mock import MagicMock

from sapwebguimcp.sapgui.components.base import GuiContainer
from sapwebguimcp.sapgui.components.connection import GuiConnection
from unittests.sapgui.conftest import make_mock_com


class TestGuiConnectionInheritance:
    def test_extends_gui_container(self):
        assert issubclass(GuiConnection, GuiContainer)

    def test_instance_is_gui_container(self):
        com = make_mock_com()
        conn = GuiConnection(com)
        assert isinstance(conn, GuiContainer)


class TestGuiConnectionProperties:
    def test_sessions(self):
        sessions = MagicMock()
        com = make_mock_com(Sessions=sessions)
        conn = GuiConnection(com)
        assert conn.sessions is sessions

    def test_connection_string(self):
        com = make_mock_com(ConnectionString="/H/server/S/3200")
        conn = GuiConnection(com)
        assert conn.connection_string == "/H/server/S/3200"

    def test_description(self):
        com = make_mock_com(Description="DEV System")
        conn = GuiConnection(com)
        assert conn.description == "DEV System"

    def test_disabled_by_server(self):
        com = make_mock_com(DisabledByServer=False)
        conn = GuiConnection(com)
        assert conn.disabled_by_server is False


class TestGuiConnectionMethods:
    def test_close_connection(self):
        com = make_mock_com()
        conn = GuiConnection(com)
        conn.close_connection()
        com.CloseConnection.assert_called_once()

    def test_close_session(self):
        com = make_mock_com()
        conn = GuiConnection(com)
        conn.close_session("/app/con[0]/ses[1]")
        com.CloseSession.assert_called_once_with("/app/con[0]/ses[1]")
