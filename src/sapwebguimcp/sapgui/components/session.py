"""GuiSession and GuiSessionInfo — session-level wrappers."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiContainer


class GuiSessionInfo:
    """Wraps the COM GuiSessionInfo object (read-only session metadata)."""

    def __init__(self, com_object) -> None:
        self._com = com_object

    @property
    def system_name(self) -> str:
        return self._com.SystemName

    @property
    def client(self) -> str:
        return self._com.Client

    @property
    def user(self) -> str:
        return self._com.User

    @property
    def language(self) -> str:
        return self._com.Language

    @property
    def transaction(self) -> str:
        return self._com.Transaction

    @property
    def program(self) -> str:
        return self._com.Program

    @property
    def screen_number(self) -> int:
        return self._com.ScreenNumber

    @property
    def application_server(self) -> str:
        return self._com.ApplicationServer

    @property
    def response_time(self) -> int:
        return self._com.ResponseTime

    @property
    def round_trips(self) -> int:
        return self._com.RoundTrips

    @property
    def session_number(self) -> int:
        return self._com.SessionNumber

    @property
    def system_number(self) -> int:
        return self._com.SystemNumber

    @property
    def codepage(self) -> int:
        return self._com.Codepage

    @property
    def flushes(self) -> int:
        return self._com.Flushes

    @property
    def group(self) -> str:
        return self._com.Group

    @property
    def message_server(self) -> str:
        return self._com.MessageServer

    @property
    def system_session_id(self) -> str:
        return self._com.SystemSessionId

    @property
    def is_low_speed_connection(self) -> bool:
        return bool(self._com.IsLowSpeedConnection)

    @property
    def scripting_mode_read_only(self) -> bool:
        return bool(self._com.ScriptingModeReadOnly)

    @property
    def scripting_mode_recording_disabled(self) -> bool:
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
        return bool(self._com.Busy)

    @property
    def active_window(self):
        """Return the active window wrapped in the correct Python class."""
        from sapwebguimcp.sapgui._factory import wrap_com_object

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
        return self._com.GetVKeyDescription(v_key)

    def get_object_tree(self, element_id: str):
        """Return the object tree starting from the given element ID."""
        return self._com.GetObjectTree(element_id)
