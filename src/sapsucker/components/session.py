"""GuiSession and GuiSessionInfo — session-level wrappers."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

from typing import Any

from sapsucker.components.base import GuiComponent, GuiContainer

__all__ = ["GuiSession", "GuiSessionInfo"]


class GuiSessionInfo:
    """Wraps the COM GuiSessionInfo object (read-only session metadata)."""

    def __init__(self, com_object: Any) -> None:
        self._com = com_object

    @property
    def system_name(self) -> str:
        """SAP system name (SID)."""
        return str(self._com.SystemName)

    @property
    def client(self) -> str:
        """SAP client number."""
        return str(self._com.Client)

    @property
    def user(self) -> str:
        """Logged-in user name."""
        return str(self._com.User)

    @property
    def language(self) -> str:
        """Session logon language."""
        return str(self._com.Language)

    @property
    def transaction(self) -> str:
        """Currently running transaction code."""
        return str(self._com.Transaction)

    @property
    def program(self) -> str:
        """Currently running ABAP program name."""
        return str(self._com.Program)

    @property
    def screen_number(self) -> int:
        """Current dynpro screen number."""
        return int(self._com.ScreenNumber)

    @property
    def application_server(self) -> str:
        """Application server host name."""
        return str(self._com.ApplicationServer)

    @property
    def response_time(self) -> int:
        """Last server response time in milliseconds."""
        return int(self._com.ResponseTime)

    @property
    def round_trips(self) -> int:
        """Number of server round trips."""
        return int(self._com.RoundTrips)

    @property
    def session_number(self) -> int:
        """Session number within the connection."""
        return int(self._com.SessionNumber)

    @property
    def system_number(self) -> int:
        """SAP system number."""
        return int(self._com.SystemNumber)

    @property
    def codepage(self) -> int:
        """Character codepage number."""
        return int(self._com.Codepage)

    @property
    def flushes(self) -> int:
        """Number of automation queue flushes."""
        return int(self._com.Flushes)

    @property
    def group(self) -> str:
        """Logon group name."""
        return str(self._com.Group)

    @property
    def message_server(self) -> str:
        """Message server host name."""
        return str(self._com.MessageServer)

    @property
    def system_session_id(self) -> str:
        """Unique system session identifier."""
        return str(self._com.SystemSessionId)

    @property
    def is_low_speed_connection(self) -> bool:
        """Whether this is a low-speed connection."""
        return bool(self._com.IsLowSpeedConnection)

    @property
    def scripting_mode_read_only(self) -> bool:
        """Whether scripting is restricted to read-only mode."""
        return bool(self._com.ScriptingModeReadOnly)

    @property
    def scripting_mode_recording_disabled(self) -> bool:
        """Whether script recording is disabled."""
        return bool(self._com.ScriptingModeRecordingDisabled)

    def __repr__(self) -> str:
        return (
            f"GuiSessionInfo(system={self._com.SystemName!r}, "
            f"client={self._com.Client!r}, "
            f"user={self._com.User!r}, "
            f"transaction={self._com.Transaction!r})"
        )


class GuiSession(GuiContainer):
    """Wraps the COM GuiSession interface (TypeAsNumber 12).

    The session is the main entry point for interacting with an SAP screen.
    """

    @property
    def info(self) -> GuiSessionInfo:
        """Return session metadata wrapped in GuiSessionInfo."""
        return GuiSessionInfo(self._com.Info)

    @property
    def busy(self) -> bool:
        """Whether the session is currently processing a server request."""
        return bool(self._com.Busy)

    @property
    def active_window(self) -> GuiComponent:
        """Return the active window wrapped in the correct Python class."""
        from sapsucker._factory import wrap_com_object

        return wrap_com_object(self._com.ActiveWindow)

    def create_session(self) -> None:
        """Open an additional session (like /o in the OK-code field)."""
        self._com.CreateSession()

    def end_transaction(self) -> None:
        """End the current transaction (like /n in the OK-code field)."""
        self._com.EndTransaction()

    def send_command(self, command: str) -> None:
        """Execute a command string synchronously (e.g. '/nSE38')."""
        self._com.SendCommand(command)

    def send_command_async(self, command: str) -> None:
        """Execute a command string asynchronously."""
        self._com.SendCommandAsync(command)

    def lock_session_ui(self) -> None:
        """Lock the session UI to prevent user interaction during scripting."""
        self._com.LockSessionUI()

    def unlock_session_ui(self) -> None:
        """Unlock the session UI."""
        self._com.UnlockSessionUI()

    def get_v_key_description(self, v_key: int) -> str:
        """Return a human-readable description for a virtual key number."""
        return str(self._com.GetVKeyDescription(v_key))

    def get_object_tree(self, element_id: str) -> Any:
        """Return the object tree starting from the given element ID."""
        return self._com.GetObjectTree(element_id)
