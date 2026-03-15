"""GuiApplication — top-level SAP GUI Scripting engine wrapper."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sapwebguimcp.sapgui.components.base import GuiContainer

if TYPE_CHECKING:
    from sapwebguimcp.sapgui.components.collection import GuiComponentCollection


class GuiApplication(GuiContainer):
    """Wraps the COM GuiApplication interface (TypeAsNumber 10).

    This is the root object obtained from the SAP GUI ROT entry.
    It manages connections and global application settings.
    """

    @property
    def connections(self) -> GuiComponentCollection:
        """Return the GuiComponentCollection of open connections."""
        from sapwebguimcp.sapgui.components.collection import GuiComponentCollection

        return GuiComponentCollection(self._com.Children)

    @property
    def active_session(self) -> Any:
        """Return the COM object for the currently active session."""
        return self._com.ActiveSession

    @property
    def connection_error_text(self) -> str:
        """Last connection error message, or empty string."""
        return str(self._com.ConnectionErrorText)

    @property
    def history_enabled(self) -> bool:
        """Whether command history recording is enabled."""
        return bool(self._com.HistoryEnabled)

    @history_enabled.setter
    def history_enabled(self, value: bool) -> None:
        self._com.HistoryEnabled = value

    @property
    def buttonbar_visible(self) -> bool:
        """Whether the application button bar is visible."""
        return bool(self._com.ButtonbarVisible)

    @buttonbar_visible.setter
    def buttonbar_visible(self, value: bool) -> None:
        self._com.ButtonbarVisible = value

    @property
    def allow_system_messages(self) -> bool:
        """Whether system messages are allowed."""
        return bool(self._com.AllowSystemMessages)

    @allow_system_messages.setter
    def allow_system_messages(self, value: bool) -> None:
        self._com.AllowSystemMessages = value

    def open_connection(self, description: str, sync: bool = True, raise_error: bool = True) -> Any:
        """Open a connection by system description (as shown in SAP Logon).

        Returns Any because wrap_com_object returns GuiComponent but the
        runtime object is always a GuiConnection.
        """
        from sapwebguimcp.sapgui._factory import wrap_com_object

        return wrap_com_object(self._com.OpenConnection(description, sync, raise_error))

    def open_connection_by_connection_string(
        self, conn_string: str, sync: bool = True, raise_error: bool = True
    ) -> Any:
        """Open a connection using a raw connection string.

        Returns Any because wrap_com_object returns GuiComponent but the
        runtime object is always a GuiConnection.
        """
        from sapwebguimcp.sapgui._factory import wrap_com_object

        return wrap_com_object(self._com.OpenConnectionByConnectionString(conn_string, sync, raise_error))

    def create_gui_collection(self) -> Any:
        """Create a new empty GuiCollection COM object."""
        return self._com.CreateGuiCollection()
