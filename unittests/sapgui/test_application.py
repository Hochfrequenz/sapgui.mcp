"""Tests for GuiApplication component."""

from unittest.mock import MagicMock

from sapsucker.components.application import GuiApplication
from sapsucker.components.base import GuiContainer
from unittests.sapgui.conftest import make_mock_com


class TestGuiApplicationInheritance:
    def test_extends_gui_container(self):
        assert issubclass(GuiApplication, GuiContainer)

    def test_instance_is_gui_container(self):
        com = make_mock_com()
        app = GuiApplication(com)
        assert isinstance(app, GuiContainer)


class TestGuiApplicationProperties:
    def test_connections(self):
        com = make_mock_com(container_type=True, children=[make_mock_com(type_as_number=11, type_name="GuiConnection")])
        app = GuiApplication(com)
        from sapsucker.components.collection import GuiComponentCollection

        assert isinstance(app.connections, GuiComponentCollection)
        assert len(app.connections) == 1

    def test_active_session(self):
        session = make_mock_com(type_as_number=12, type_name="GuiSession")
        com = make_mock_com(ActiveSession=session)
        app = GuiApplication(com)
        result = app.active_session
        from sapsucker.components.session import GuiSession

        assert isinstance(result, GuiSession)

    def test_connection_error_text(self):
        com = make_mock_com(ConnectionErrorText="some error")
        app = GuiApplication(com)
        assert app.connection_error_text == "some error"

    def test_history_enabled_getter(self):
        com = make_mock_com(HistoryEnabled=True)
        app = GuiApplication(com)
        assert app.history_enabled is True

    def test_history_enabled_setter(self):
        com = make_mock_com()
        app = GuiApplication(com)
        app.history_enabled = False
        assert com.HistoryEnabled is False

    def test_buttonbar_visible_getter(self):
        com = make_mock_com(ButtonbarVisible=True)
        app = GuiApplication(com)
        assert app.buttonbar_visible is True

    def test_buttonbar_visible_setter(self):
        com = make_mock_com()
        app = GuiApplication(com)
        app.buttonbar_visible = False
        assert com.ButtonbarVisible is False

    def test_allow_system_messages_getter(self):
        com = make_mock_com(AllowSystemMessages=False)
        app = GuiApplication(com)
        assert app.allow_system_messages is False

    def test_allow_system_messages_setter(self):
        com = make_mock_com()
        app = GuiApplication(com)
        app.allow_system_messages = True
        assert com.AllowSystemMessages is True


class TestGuiApplicationMethods:
    def test_open_connection(self):
        com = make_mock_com()
        conn_com = make_mock_com(type_as_number=11, type_name="GuiConnection")
        com.OpenConnection.return_value = conn_com
        app = GuiApplication(com)
        result = app.open_connection("DEV", sync=True, raise_error=True)
        com.OpenConnection.assert_called_once_with("DEV", True, True)
        assert result.com is conn_com

    def test_open_connection_by_connection_string(self):
        com = make_mock_com()
        conn_com = make_mock_com(type_as_number=11, type_name="GuiConnection")
        com.OpenConnectionByConnectionString.return_value = conn_com
        app = GuiApplication(com)
        result = app.open_connection_by_connection_string("/H/server/S/3200")
        com.OpenConnectionByConnectionString.assert_called_once_with("/H/server/S/3200", True, True)
        assert result.com is conn_com

    def test_create_gui_collection(self):
        com = make_mock_com()
        app = GuiApplication(com)
        app.create_gui_collection()
        com.CreateGuiCollection.assert_called_once()


class TestGuiApplicationContextManager:
    def test_enter_returns_self(self):
        com = make_mock_com()
        app = GuiApplication(com)
        assert app.__enter__() is app

    def test_exit_closes_connections_best_effort(self):
        conn_com = MagicMock()
        com = make_mock_com(children=[conn_com])
        app = GuiApplication(com)
        app.__exit__(None, None, None)
        conn_com.CloseConnection.assert_called_once()

    def test_exit_suppresses_connection_close_errors(self):
        conn_com = MagicMock()
        conn_com.CloseConnection.side_effect = Exception("COM error")
        com = make_mock_com(children=[conn_com])
        app = GuiApplication(com)
        # Should not raise
        app.__exit__(None, None, None)

    def test_exit_with_no_connections(self):
        com = make_mock_com(children=[])
        app = GuiApplication(com)
        # Should not raise
        app.__exit__(None, None, None)

    def test_exit_closes_multiple_connections(self):
        conn1 = MagicMock()
        conn2 = MagicMock()
        com = make_mock_com(children=[conn1, conn2])
        app = GuiApplication(com)
        app.__exit__(None, None, None)
        conn1.CloseConnection.assert_called_once()
        conn2.CloseConnection.assert_called_once()

    def test_used_as_context_manager(self):
        com = make_mock_com(children=[])
        with GuiApplication(com) as app:
            assert isinstance(app, GuiApplication)
