"""sapsucker — Pythonic SAP GUI Scripting Library."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sapsucker.components.application import GuiApplication

__all__ = ["SapGui"]


class SapGui:
    """High-level facade for launching or connecting to SAP GUI."""

    @staticmethod
    def connect() -> GuiApplication:
        """Connect to an already-running SAP GUI instance.

        Returns:
            A GuiApplication wrapping the SAP GUI Scripting engine.
        """
        from sapsucker._com import _connect_to_running_sap_gui

        return _connect_to_running_sap_gui()

    @staticmethod
    def launch(
        exe_path: str,
        connection_string: str | None = None,
        timeout: int = 30,
    ) -> GuiApplication:
        """Launch SAP GUI from *exe_path* and wait for it to become scriptable.

        Args:
            exe_path: Path to the SAP GUI executable (saplogon.exe).
            connection_string: Optional connection string to open immediately.
            timeout: Seconds to wait for the scripting engine to become available.

        Returns:
            A GuiApplication wrapping the SAP GUI Scripting engine.
        """
        from sapsucker._com import _wait_for_sap_gui

        cmd = [exe_path]
        if connection_string:
            cmd.extend(["-command", connection_string])
        subprocess.Popen(cmd)  # pylint: disable=consider-using-with
        return _wait_for_sap_gui(timeout=timeout)
