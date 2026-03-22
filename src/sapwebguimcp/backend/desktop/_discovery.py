"""SAP connection discovery helpers for the desktop backend.

These functions open a SAP connection at the login screen without logging in,
so the caller can inspect available clients (MANDT field, info text).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sapsucker.components.session import GuiSession


def open_for_discovery(
    connection_name: str,
    saplogon_exe_path: str | None = None,
    timeout: int = 30,
) -> tuple[Any, str, str]:
    """Open a SAP connection and return (session, default_client, info_text).

    Leaves the session at the login screen WITHOUT filling in credentials.
    The caller is responsible for registering and (eventually) closing the session.

    Returns:
        session: raw GuiSession at the login screen
        default_client: pre-filled client value from the MANDT field (may be empty)
        info_text: all visible text from the login screen for client list parsing
    """
    from sapsucker import SapGui  # pylint: disable=import-outside-toplevel
    from sapsucker._errors import SapConnectionError  # pylint: disable=import-outside-toplevel
    from sapsucker.login import (  # pylint: disable=import-outside-toplevel
        _discover_saplogon_path,
        _dismiss_system_message_popups,
        _wait_for_session,
    )

    try:
        app = SapGui.connect()
    except SapConnectionError:
        app = SapGui.launch(exe_path=saplogon_exe_path or _discover_saplogon_path(), timeout=timeout)

    conn = app.open_connection(connection_name, sync=True)
    session = _wait_for_session(conn, timeout=timeout)
    _dismiss_system_message_popups(session)

    default_client = ""
    info_text = ""

    if session.info.program == "SAPMSYST":
        try:
            mandt_field = session.find_by_id("wnd[0]/usr/txtRSYST-MANDT", raise_error=False)
            if mandt_field is not None:
                default_client = str(cast(Any, mandt_field).text or "")
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        info_text = _collect_window_text(session)

    return session, default_client, info_text


def _collect_window_text(session: GuiSession) -> str:
    """Collect all visible text from the SAP session window via COM tree traversal."""
    texts: list[str] = []

    def _traverse(elem: Any) -> None:
        try:
            t = str(getattr(elem, "Text", None) or "").strip()
            if t:
                texts.append(t)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        try:
            children = elem.Children
            for i in range(children.Count):
                try:
                    _traverse(children(i))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    try:
        window_com = cast(Any, session.com).findById("wnd[0]")
        _traverse(window_com)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return "\n".join(texts)
