"""GuiApplication — top-level SAP GUI Scripting engine wrapper."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sapwebguimcp.sapgui.components.base import GuiContainer

if TYPE_CHECKING:
    from sapwebguimcp.sapgui.components.collection import GuiComponentCollection

__all__ = ["GuiApplication"]


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

        Raises:
            SapConnectionError: If the SAP server is unreachable or the
                connection name is not found in SAP Logon.
        """
        from sapwebguimcp.sapgui._errors import SapConnectionError
        from sapwebguimcp.sapgui._factory import wrap_com_object

        try:
            return wrap_com_object(self._com.OpenConnection(description, sync, raise_error))
        except Exception as e:
            # Check ConnectionErrorText for server-unreachable details
            detail = ""
            try:
                detail = str(self._com.ConnectionErrorText).strip()
            except Exception:
                pass
            if detail:
                raise SapConnectionError(
                    f"SAP server unreachable for connection '{description}'. " f"Check VPN and server status.\n{detail}"
                ) from e
            raise SapConnectionError(
                f"Could not open connection '{description}'. " f"Verify the name matches an entry in SAP Logon."
            ) from e

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

    def __enter__(self) -> GuiApplication:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close all connections on exit. Best-effort — errors are suppressed."""
        try:
            # Reverse iteration: COM Children collection mutates on close,
            # so closing from the end avoids skipping connections.
            for i in range(self._com.Children.Count - 1, -1, -1):
                try:
                    self._com.Children.Item(i).CloseConnection()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
