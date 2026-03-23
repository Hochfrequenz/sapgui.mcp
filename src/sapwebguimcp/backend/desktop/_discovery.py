"""SAP connection discovery helpers for the desktop backend.

Opens a SAP connection, logs in with the default client, and queries T000
to reliably discover all available clients (Mandanten) in the system.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sapsucker.components.session import GuiSession

logger = logging.getLogger(__name__)


def open_and_discover_clients(
    connection_name: str,
    user: str,
    password: str,
    language: str = "EN",
    saplogon_exe_path: str | None = None,
    timeout: int = 30,
) -> tuple[Any, str, list[dict[str, str]]]:
    """Open a SAP connection, log in, and query T000 for available clients.

    Logs in with the default client from the login screen (or via SSO),
    then reads table T000 via SE16N to get all clients in the system.

    Returns:
        session: logged-in GuiSession
        default_client: the client used for login
        clients: list of {"id": "NNN", "description": "..."} from T000
    """
    import sapsucker.login as _login_mod  # pylint: disable=import-outside-toplevel
    from sapsucker import SapGui  # pylint: disable=import-outside-toplevel
    from sapsucker._errors import SapConnectionError  # pylint: disable=import-outside-toplevel

    try:
        app = SapGui.connect()
    except SapConnectionError:
        app = SapGui.launch(
            exe_path=saplogon_exe_path or _login_mod._discover_saplogon_path(),
            timeout=timeout,
        )

    conn = app.open_connection(connection_name, sync=True)
    session = _login_mod._wait_for_session(conn, timeout=timeout)
    _login_mod._dismiss_system_message_popups(session)

    if session.info.program == "SAPMSYST":
        # At login screen — read default client, fill credentials, log in
        default_client = ""
        try:
            mandt_field = session.find_by_id("wnd[0]/usr/txtRSYST-MANDT", raise_error=False)
            if mandt_field is not None:
                default_client = str(cast(Any, mandt_field).text or "")
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # Fill login fields on the existing session (no new connection)
        cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-MANDT")).text = default_client
        cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-BNAME")).text = user
        cast(Any, session.find_by_id("wnd[0]/usr/pwdRSYST-BCODE")).text = password
        cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-LANGU")).text = language
        cast(Any, session.find_by_id("wnd[0]")).send_v_key(0)  # Enter
        time.sleep(1)

        _login_mod._handle_multiple_logon_popup(session)

        # Verify login succeeded
        if session.info.program == "SAPMSYST":
            sbar = cast(Any, session.find_by_id("wnd[0]/sbar"))
            raise SapConnectionError(f"Login failed: {sbar.text}")
    else:
        # SSO — already logged in
        default_client = str(session.info.client or "")

    # Query T000 for all clients
    clients = _query_t000_clients(session)

    return session, default_client, clients


def _query_t000_clients(session: GuiSession) -> list[dict[str, str]]:
    """Query T000 via SE16N and return all clients in the system.

    Returns a list of ``{"id": "NNN", "description": "..."}`` dicts.
    Navigates back to the starting screen when done.
    """
    com = cast(Any, session.com)
    try:
        # Navigate to SE16N
        okcd = com.findById("wnd[0]/tbar[0]/okcd")
        okcd.text = "/nSE16N"
        com.findById("wnd[0]").sendVKey(0)
        time.sleep(1)

        # Fill table name T000
        filled = False
        for field_id in [
            "wnd[0]/usr/ctxtGD-TAB",
            "wnd[0]/usr/ctxtGD-SESSION_TAB",
        ]:
            try:
                fld = com.findById(field_id)
                fld.text = "T000"
                filled = True
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        if not filled:
            logger.debug("T000 query: could not fill table name field")
            return []

        # Execute (F8)
        com.findById("wnd[0]").sendVKey(8)
        time.sleep(2)

        # Find ALV grid
        from sapwebguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel
        from sapsucker.components.grid import GuiGridView  # pylint: disable=import-outside-toplevel

        wnd = session.find_by_id("wnd[0]")
        tree = cast(Any, wnd).dump_tree()

        grid_id = None
        for elem in _flatten(tree):
            if elem.type_as_number in (122, 80):
                grid_id = elem.id
                break

        if grid_id is None:
            logger.debug("T000 query: no ALV grid found")
            return []

        grid = session.find_by_id(grid_id)
        if not isinstance(grid, GuiGridView):
            logger.debug("T000 query: found element is not a GuiGridView")
            return []

        grid_com = cast(Any, grid)
        row_count = grid_com.row_count
        col_order = grid_com.column_order
        columns = [str(col_order(i)) for i in range(col_order.Count)]

        mandt_col = next((c for c in columns if c.upper() == "MANDT"), None)
        mtext_col = next((c for c in columns if c.upper() == "MTEXT"), None)

        clients: list[dict[str, str]] = []
        for ri in range(row_count):
            mandt = str(grid_com.get_cell_value(ri, mandt_col)).strip() if mandt_col else ""
            mtext = str(grid_com.get_cell_value(ri, mtext_col)).strip() if mtext_col else ""
            if mandt:
                clients.append({"id": mandt, "description": mtext})

        return clients
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("T000 query failed", exc_info=True)
        return []
    finally:
        # Navigate back
        try:
            okcd = com.findById("wnd[0]/tbar[0]/okcd")
            okcd.text = "/n"
            com.findById("wnd[0]").sendVKey(0)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
