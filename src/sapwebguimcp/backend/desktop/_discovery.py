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


# -- grid helpers (keep _query_t000_clients small) ---------------------------


def _find_alv_grid_id(session: GuiSession) -> str | None:
    """Find the first ALV grid (type 122) or table control (type 80) in the window."""
    from sapwebguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    wnd = session.find_by_id("wnd[0]")
    tree = cast(Any, wnd).dump_tree()
    for elem in _flatten(tree):
        if elem.type_as_number in (122, 80):
            return str(elem.id)
    return None


def _read_clients_from_grid(session: GuiSession, grid_id: str) -> list[dict[str, str]]:
    """Read MANDT + MTEXT columns from an ALV grid showing T000 results."""
    from sapsucker.components.grid import GuiGridView  # pylint: disable=import-outside-toplevel

    grid = session.find_by_id(grid_id)
    if not isinstance(grid, GuiGridView):
        logger.debug("T000 query: found element is not a GuiGridView")
        return []

    grid_com = cast(Any, grid)
    col_order = grid_com.column_order
    # sapsucker >=0.1.0 returns a Python list; older versions return a COM collection
    if isinstance(col_order, list):
        columns = [str(c) for c in col_order]
    else:
        columns = [str(col_order(i)) for i in range(col_order.Count)]

    mandt_col = next((c for c in columns if c.upper() == "MANDT"), None)
    mtext_col = next((c for c in columns if c.upper() == "MTEXT"), None)

    clients: list[dict[str, str]] = []
    for ri in range(grid_com.row_count):
        mandt = str(grid_com.get_cell_value(ri, mandt_col)).strip() if mandt_col else ""
        mtext = str(grid_com.get_cell_value(ri, mtext_col)).strip() if mtext_col else ""
        if mandt:
            clients.append({"id": mandt, "description": mtext})
    return clients


# -- SAP navigation helpers --------------------------------------------------


def _navigate_to_se16n_t000(com: Any) -> bool:
    """Navigate to SE16N and fill table name T000. Returns True on success."""
    okcd = com.findById("wnd[0]/tbar[0]/okcd")
    okcd.text = "/nSE16N"
    com.findById("wnd[0]").sendVKey(0)
    time.sleep(1)

    for field_id in [
        "wnd[0]/usr/ctxtGD-TAB",
        "wnd[0]/usr/ctxtGD-SESSION_TAB",
    ]:
        try:
            com.findById(field_id).text = "T000"
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return False


def _navigate_back(com: Any) -> None:
    """Navigate back to Easy Access (/n)."""
    try:
        com.findById("wnd[0]/tbar[0]/okcd").text = "/n"
        com.findById("wnd[0]").sendVKey(0)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


# -- public API --------------------------------------------------------------


def open_and_discover_clients(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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

    Args:
        connection_name: SAP Logon entry name.
        user: SAP username.
        password: SAP password.
        language: Login language (default "EN").
        saplogon_exe_path: Override path to saplogon.exe.
        timeout: Max seconds to wait for connection/session.

    Returns:
        session: logged-in GuiSession
        default_client: the client used for login
        clients: list of {"id": "NNN", "description": "..."} from T000
    """
    # sapsucker exposes login helpers as private — no public alternative yet
    # pylint: disable=protected-access
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
        default_client = _login_at_screen(session, user, password, language)
        _login_mod._handle_multiple_logon_popup(session)
        if session.info.program == "SAPMSYST":
            sbar = cast(Any, session.find_by_id("wnd[0]/sbar"))
            raise SapConnectionError(f"Login failed: {sbar.text}")
    else:
        # SSO — already logged in
        default_client = str(session.info.client or "")

    clients = _query_t000_clients(session)
    return session, default_client, clients


def _login_at_screen(session: GuiSession, user: str, password: str, language: str) -> str:
    """Fill the SAP login screen and press Enter. Returns the default client."""
    default_client = ""
    try:
        mandt_field = session.find_by_id("wnd[0]/usr/txtRSYST-MANDT", raise_error=False)
        if mandt_field is not None:
            default_client = str(cast(Any, mandt_field).text or "")
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-MANDT")).text = default_client
    cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-BNAME")).text = user
    cast(Any, session.find_by_id("wnd[0]/usr/pwdRSYST-BCODE")).text = password
    cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-LANGU")).text = language
    cast(Any, session.find_by_id("wnd[0]")).send_v_key(0)
    time.sleep(1)
    return default_client


def _query_t000_clients(session: GuiSession) -> list[dict[str, str]]:
    """Query T000 via SE16N and return all clients in the system.

    Returns a list of ``{"id": "NNN", "description": "..."}`` dicts.
    Navigates back to the starting screen when done.
    """
    com = cast(Any, session.com)
    try:
        if not _navigate_to_se16n_t000(com):
            logger.debug("T000 query: could not fill table name field")
            return []

        # Execute (F8)
        com.findById("wnd[0]").sendVKey(8)
        time.sleep(2)

        grid_id = _find_alv_grid_id(session)
        if grid_id is None:
            logger.debug("T000 query: no ALV grid found")
            return []

        return _read_clients_from_grid(session, grid_id)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("T000 query failed", exc_info=True)
        return []
    finally:
        _navigate_back(com)
