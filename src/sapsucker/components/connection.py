"""GuiConnection — a single SAP system connection."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

from typing import TYPE_CHECKING

from sapsucker.components.base import GuiContainer

if TYPE_CHECKING:
    from sapsucker.components.collection import GuiComponentCollection

__all__ = ["GuiConnection"]


class GuiConnection(GuiContainer):
    """Wraps the COM GuiConnection interface (TypeAsNumber 11).

    Represents one connection to an SAP application server.
    Contains one or more sessions.
    """

    @property
    def sessions(self) -> GuiComponentCollection:
        """Return the GuiComponentCollection of sessions."""
        from sapsucker.components.collection import GuiComponentCollection

        return GuiComponentCollection(self._com.Children)

    @property
    def connection_string(self) -> str:
        """Raw connection string."""
        return str(self._com.ConnectionString)

    @property
    def description(self) -> str:
        """Human-readable connection description."""
        return str(self._com.Description)

    @property
    def disabled_by_server(self) -> bool:
        """Whether scripting is disabled by the server."""
        return bool(self._com.DisabledByServer)

    def close_connection(self) -> None:
        """Close this connection and all its sessions."""
        self._com.CloseConnection()

    def close_session(self, session_id: str) -> None:
        """Close a specific session by its ID."""
        self._com.CloseSession(session_id)
