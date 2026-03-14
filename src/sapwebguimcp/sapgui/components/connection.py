"""GuiConnection — a single SAP system connection."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiContainer


class GuiConnection(GuiContainer):
    """Wraps the COM GuiConnection interface (TypeAsNumber 11).

    Represents one connection to an SAP application server.
    Contains one or more sessions.
    """

    @property
    def sessions(self):
        """Return the GuiComponentCollection of sessions."""
        from sapwebguimcp.sapgui.components.collection import GuiComponentCollection

        return GuiComponentCollection(self._com.Children)

    @property
    def connection_string(self) -> str:
        return self._com.ConnectionString

    @property
    def description(self) -> str:
        return self._com.Description

    @property
    def disabled_by_server(self) -> bool:
        return bool(self._com.DisabledByServer)

    def close_connection(self) -> None:
        """Close this connection and all its sessions."""
        self._com.CloseConnection()

    def close_session(self, session_id: str) -> None:
        """Close a specific session by its ID."""
        self._com.CloseSession(session_id)
