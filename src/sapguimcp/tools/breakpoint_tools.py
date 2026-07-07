"""ABAP external breakpoint management tools (desktop backend only)."""

# pylint: disable=too-many-lines

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

from fastmcp import Context, FastMCP
from pydantic import Field as PydanticField

from sapguimcp.backend.manager import get_backend
from sapguimcp.models.breakpoint_models import (
    BreakpointDeleteResult,
    BreakpointEntry,
    BreakpointListResult,
    BreakpointSetResult,
)
from sapguimcp.tools.confirmation_helpers import confirm_destructive_action
from sapguimcp.tools.field_helpers import fill_field_with_keyboard

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend

logger = logging.getLogger(__name__)

# COM shell paths per transaction. Screen numbers (8430, 8300) vary across SAP releases.
# Each entry lists candidates in preference order; the first one found at runtime is used.
_SHELL_PATH_CANDIDATES: dict[str, list[str]] = {
    "PROG": [
        "usr/cntlEDITOR/shellcont/shell",
    ],
    "CLAS": [
        "usr/subEDITORSUBSCREEN:SAPLEDITOR_START:8430/cntlEDITOR/shellcont/shell",
        "usr/subEDITORSUBSCREEN:SAPLEDITOR_START:8300/cntlEDITOR/shellcont/shell",
    ],
    "FUGR": [
        "usr/tabsFUNC_TAB_STRIP/tabpSOURCE/ssubSCREEN_HEADER:SAPLEDITOR_START:8430/cntlEDITOR/shellcont/shell",
        "usr/tabsFUNC_TAB_STRIP/tabpSOURCE/ssubSCREEN_HEADER:SAPLEDITOR_START:8300/cntlEDITOR/shellcont/shell",
    ],
}

_WEBGUI_ERROR = "External breakpoints are not supported on the WebGUI backend. Use BACKEND_TYPE=desktop."

_SE37_FM_LABELS = ("Funktionsbaustein", "Function Module", "Function module")


def _resolve_match_pattern(source: str, pattern: str) -> int | None:
    """Resolve a substring or regex pattern to a 1-indexed line number.

    Returns the 1-indexed line number of the first matching line, or None.
    """
    lines = source.split("\n")
    for idx, line in enumerate(lines):
        try:
            if re.search(pattern, line):
                return idx + 1
        except re.error:
            if pattern in line:
                return idx + 1
    return None


def _classify_toggle_status(status_message: str) -> Literal["set", "deleted"] | None:
    """Classify a SAP status bar message as 'set' or 'deleted', or None if unrecognized."""
    msg = status_message.lower()
    if "gesetzt" in msg:
        return "set"
    if "gelöscht" in msg or "geloescht" in msg:
        return "deleted"
    return None


def _resolve_shell_path_com(session: Any, object_type: str) -> str | None:
    """COM-thread callable: return the first shell path candidate that exists, or None."""
    raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
    for candidate in _SHELL_PATH_CANDIDATES.get(object_type, []):
        if raw_session.FindById(f"wnd[0]/{candidate}", False) is not None:
            return candidate
    return None


def _toggle_breakpoint_com(session: Any, shell_path: str, line_number: int) -> tuple[bool, str]:
    """COM-thread callable: position cursor at line and send VKey 45.

    Returns (shell_found, status_bar_message).
    Runs entirely synchronously — called via backend.com.run().
    """
    raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
    shell = raw_session.FindById(f"wnd[0]/{shell_path}", False)
    if shell is None:
        return False, f"Editor shell not found at wnd[0]/{shell_path}"
    shell.SelectRange(line_number, 0, line_number, 0)
    time.sleep(0.1)
    raw_session.FindById("wnd[0]", False).SendVKey(45)
    time.sleep(0.3)
    sbar = raw_session.FindById("wnd[0]/sbar", False)
    # raw COM object uses PascalCase property names — Text, not text
    msg = str(sbar.Text) if sbar is not None else ""
    return True, msg


def _has_popup_com(session: Any) -> bool:
    """COM-thread callable: return True if a modal popup (wnd[1]) is currently open."""
    raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
    return raw_session.FindById("wnd[1]", False) is not None


def _find_menu_item_idx_com(raw_session: Any, base_path: str, texts: tuple[str, ...]) -> int | None:
    """Scan up to 20 menu children at base_path and return the index of the first text match."""
    for i in range(20):
        item = raw_session.FindById(f"{base_path}/menu[{i}]", False)
        if item is None:
            break
        if item.Text in texts:
            return i
    return None


def _open_bp_list_dialog_com(session: Any) -> tuple[bool, str]:
    """COM-thread callable: open breakpoints list dialog via menu.

    Returns (success, error_message).
    Runs synchronously — called via backend.com.run().
    """
    raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
    try:
        # Locate Hilfsmittel in the menu bar — its position varies across transactions
        # and SAP releases, so scan by .Text instead of using a hardcoded index.
        hilfsmittel_idx = _find_menu_item_idx_com(raw_session, "wnd[0]/mbar", ("Hilfsmittel", "Utilities"))
        if hilfsmittel_idx is None:
            return False, "Hilfsmittel menu not found in menu bar"

        # Locate the breakpoints submenu within Hilfsmittel.
        # In SE37/SE38 on ECC both "Breakpoint" (internal) and "Externe Breakpoints" (external)
        # exist — prefer the external one; fall back to generic "Breakpoint"/"Breakpoints".
        hilfsmittel_path = f"wnd[0]/mbar/menu[{hilfsmittel_idx}]"
        bp_menu_idx = _find_menu_item_idx_com(
            raw_session, hilfsmittel_path, ("Externe Breakpoints", "External Breakpoints")
        )
        if bp_menu_idx is None:
            bp_menu_idx = _find_menu_item_idx_com(raw_session, hilfsmittel_path, ("Breakpoint", "Breakpoints"))

        if bp_menu_idx is None:
            return False, "Breakpoint menu not found in Hilfsmittel"

        # Locate "Anzeigen..." within the Breakpoints submenu — index varies per release.
        bp_sub_path = f"wnd[0]/mbar/menu[{hilfsmittel_idx}]/menu[{bp_menu_idx}]"
        anzeigen_idx = _find_menu_item_idx_com(
            raw_session, bp_sub_path, ("Anzeigen...", "Anzeigen", "Display...", "Display")
        )
        if anzeigen_idx is None:
            return False, "Anzeigen... item not found in Breakpoints submenu"

        menu_item = raw_session.FindById(f"{bp_sub_path}/menu[{anzeigen_idx}]", False)
        menu_item.Select()
        time.sleep(0.5)
        return True, ""
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return False, f"Could not open breakpoints dialog: {exc}"


def _read_bp_grid_and_close_com(
    session: Any,
) -> tuple[list[dict[str, str]], str]:
    """COM-thread callable: click Alle anzeigen, read grid rows, close dialog.

    Returns (rows, error_message). rows is a list of dicts with keys:
    MAINPROGRAM_DIS, INCLUDE_DIS, SOURCE_LINE, SOURCE.
    Column names verified live from FORM prepare_alv_bp in LBREAF10 (spec §Listing Breakpoints).
    Runs synchronously — called via backend.com.run().
    """
    raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
    try:
        # Click "Alle anzeigen" — scan toolbar by tooltip, index varies across releases.
        btn_all = None
        for i in range(20):
            btn = raw_session.FindById(f"wnd[1]/tbar[0]/btn[{i}]", False)
            if btn is None:
                break
            if btn.Tooltip in ("Alle anzeigen", "Display All"):
                btn_all = btn
                break
        if btn_all is None:
            # Fallback: try the hardcoded index that works on S4U
            btn_all = raw_session.FindById("wnd[1]/tbar[0]/btn[5]", False)
        if btn_all is not None:
            btn_all.Press()
            time.sleep(0.8)

        # Read grid
        grid = raw_session.FindById("wnd[1]/usr/cntlG_BP_CONTAINER/shellcont/shell", False)
        if grid is None:
            raw_session.FindById("wnd[1]", False).SendVKey(12)
            return [], "Grid not found at wnd[1]/usr/cntlG_BP_CONTAINER/shellcont/shell"

        row_count = grid.RowCount
        rows: list[dict[str, str]] = []
        for i in range(row_count):
            rows.append(
                {
                    "MAINPROGRAM_DIS": str(grid.GetCellValue(i, "MAINPROGRAM_DIS")),
                    "INCLUDE_DIS": str(grid.GetCellValue(i, "INCLUDE_DIS")),
                    "SOURCE_LINE": str(grid.GetCellValue(i, "SOURCE_LINE")),
                    "SOURCE": str(grid.GetCellValue(i, "SOURCE")),
                }
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        try:
            raw_session.FindById("wnd[1]", False).SendVKey(12)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return [], f"Error reading breakpoints grid: {exc}"

    # Close dialog with F12 (Abbrechen)
    raw_session.FindById("wnd[1]", False).SendVKey(12)
    time.sleep(0.2)
    return rows, ""


def _filter_bp_rows(
    rows: list[dict[str, str]],
    object_type: str,
    object_name: str,
    _method_name: str | None,
) -> list[BreakpointEntry]:
    """Filter grid rows to only those matching the requested object."""
    entries: list[BreakpointEntry] = []
    for row in rows:
        include_dis = row["INCLUDE_DIS"].strip().upper()
        main_prog = row["MAINPROGRAM_DIS"].strip().upper()
        source_line_str = row["SOURCE_LINE"].strip()

        if object_type == "PROG":
            if include_dis != object_name.upper():
                continue
        elif object_type == "CLAS":
            # SAP stores class method breakpoints in generated method includes
            # (e.g. ZCL_FOO==========CM_MY_METHOD_XX), not under the class name directly.
            # MAINPROGRAM_DIS is set to the class name for all class breakpoints.
            # We filter by MAINPROGRAM_DIS == class name, which returns all breakpoints
            # for the class. Filtering to a specific method is not possible here without
            # resolving the generated include name first — callers get all class breakpoints.
            if not (
                main_prog == object_name.upper() or (main_prog == "" and include_dis.startswith(object_name.upper()))
            ):
                continue
        elif object_type == "FUGR":
            # SAP FM breakpoints live in numbered function group includes (e.g. LBREAU01),
            # not in an include named after the FM. MAINPROGRAM_DIS is set to the function
            # group name for all FM breakpoints. We filter by MAINPROGRAM_DIS == object_name,
            # which returns all breakpoints in the function group. The method_name is used
            # only for navigation, not for filtering here.
            if main_prog != object_name.upper():
                continue

        try:
            line_num = int(source_line_str)
        except ValueError:
            continue
        entries.append(BreakpointEntry(line_number=line_num, source_line=row["SOURCE"]))

    return entries


async def _navigate_prog(backend: DesktopBackend, object_name: str) -> str | None:
    """Navigate to SE38 in display mode. Returns error message or None."""
    await backend.enter_transaction("SE38")
    await backend.wait_for_ready()

    filled = await backend.focus_and_type("RS38M-PROGRAMM", object_name.upper())
    if not filled:
        filled = await fill_field_with_keyboard(
            backend,
            ["ABAP-Programmname", "ABAP Program Name", "ABAP program name", "Programm", "Program"],
            object_name.upper(),
        )
    if not filled:
        return f"Could not fill program name field for '{object_name}'"

    await asyncio.sleep(0.3)
    # click_button("Anzeigen") verified to work; F7 fallback only if button not found
    clicked = False
    try:
        await backend.click_button("Anzeigen")
        clicked = True
    except ValueError:
        pass
    if not clicked:
        await backend.press_key("F7")
    await backend.wait_for_ready()

    screen = await backend.get_screen_info()
    title = (screen.title or "").lower()
    if "einstieg" in title or "initial" in title:
        sbar = await backend.get_status_bar()
        return sbar.message or f"Could not display program '{object_name}'"
    return None


async def _navigate_clas(  # pylint: disable=too-many-statements
    backend: DesktopBackend, class_name: str, method_name: str
) -> str | None:
    """Navigate to SE24 in display mode and open the method source editor.

    Returns error message or None.
    """
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    await backend.enter_transaction("SE24")
    await backend.wait_for_ready()

    filled = await backend.focus_and_type("SEOCLASS-CLSNAME", class_name.upper())
    if not filled:
        filled = await fill_field_with_keyboard(backend, ["Objekttyp", "Object Type"], class_name.upper())
    if not filled:
        return f"Could not fill class name field for '{class_name}'"

    await asyncio.sleep(0.3)
    await backend.press_key("F7")  # Display
    await backend.wait_for_ready()

    # Dismiss language dialog if present (only press Enter when a popup actually opened)
    session = backend.require_session()
    com = backend.com
    has_popup = await com.run(lambda: _has_popup_com(session))
    if has_popup:
        await backend.press_key("Enter")
        await backend.wait_for_ready()

    screen = await backend.get_screen_info()
    title = (screen.title or "").lower()
    if "einstieg" in title or "initial" in title:
        sbar = await backend.get_status_bar()
        return sbar.message or f"Could not display class '{class_name}'"

    # Navigate to Methods tab
    for tab_label in ("Methoden", "Methods"):
        try:
            await backend.click_tab(tab_label)
            await backend.wait(500)
            break
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    # Find method row in the table control via raw COM

    def _select_method_row() -> str | None:
        wnd = session.find_by_id("wnd[0]")
        tree = cast(Any, wnd).dump_tree()
        flat = _flatten(tree)
        for elem in flat:
            if elem.type_as_number != 80:  # GuiTableControl
                continue
            tc = session.find_by_id(elem.id)
            raw: Any = getattr(tc, "com", getattr(tc, "_com", tc))
            col_count = raw.Columns.Count
            visible = min(raw.RowCount, raw.VisibleRowCount)
            method_col = -1
            for c in range(col_count):
                title_text = raw.Columns(c).Title or raw.Columns(c).Name
                if title_text in ("Methode", "Method"):
                    method_col = c
                    break
            if method_col < 0:
                continue
            for r in range(visible):
                try:
                    cell_text = raw.GetCell(r, method_col).Text
                    if cell_text.upper().strip() == method_name.upper():
                        raw.GetCell(r, method_col).SetFocus()
                        return None
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            return f"Method '{method_name}' not found in class '{class_name}' methods table"
        return "No GuiTableControl found on SE24 Methods tab"

    select_error = await com.run(_select_method_row)
    if select_error:
        return select_error

    # Click "Quelltext" / "Sourcecode" button to open method source editor
    for btn_name in ("Quelltext", "Sourcecode", "Source Code", "Source code"):
        try:
            await backend.click_button(btn_name)
            await backend.wait_for_ready()
            return None
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return "Could not find 'Quelltext'/'Sourcecode' button"


async def _navigate_fugr(backend: DesktopBackend, function_module: str) -> str | None:
    """Navigate to SE37 in display mode and click source code tab.

    Returns error message or None.
    `function_module` is the FM name (method_name in the tool params for FUGR).
    """
    await backend.enter_transaction("SE37")
    await backend.wait_for_ready()

    # Try direct field fill first (RS37M-FUNCNAME), fall back to label-based keyboard fill
    filled = await backend.focus_and_type("RS37M-FUNCNAME", function_module.upper())
    if not filled:
        filled = await fill_field_with_keyboard(backend, list(_SE37_FM_LABELS), function_module.upper())
    if not filled:
        return f"Could not fill function module name field for '{function_module}'"

    await asyncio.sleep(0.3)
    await backend.press_key("F7")  # Display
    await backend.wait_for_ready()

    screen = await backend.get_screen_info()
    title = (screen.title or "").lower()
    if "einstieg" in title or "initial" in title:
        sbar = await backend.get_status_bar()
        return sbar.message or f"Could not display function module '{function_module}'"

    # Click source code tab to ensure the editor is active
    for tab_name in ("Quelltext", "Source Code", "Source code", "Source text"):
        try:
            await backend.click_tab(tab_name)
            await backend.wait_for_ready()
            return None
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return "Could not find source code tab in SE37"


async def _navigate_to_editor(
    backend: DesktopBackend,
    object_type: Literal["PROG", "CLAS", "FUGR"],
    object_name: str,
    method_name: str | None,
) -> str | None:
    """Navigate to the editor for the given object. Returns error or None."""
    if object_type == "PROG":
        return await _navigate_prog(backend, object_name)
    if object_type == "CLAS":
        if not method_name:
            return "method_name is required for object_type=CLAS"
        return await _navigate_clas(backend, object_name, method_name)
    if object_type == "FUGR":
        if not method_name:
            return "method_name is required for object_type=FUGR"
        return await _navigate_fugr(backend, method_name)
    raise ValueError(f"Unknown object_type '{object_type}'")


async def _resolve_line_number(
    backend: DesktopBackend,
    line_number: int | None,
    match_pattern: str | None,
) -> tuple[int | None, str | None]:
    """Resolve to a line number and validate against source length.

    Returns (resolved_line, error_message). Exactly one of the inputs must be set.
    Always reads source to validate line_number range (spec requirement).
    """
    source = await backend.read_editor_source()
    if not source:
        return None, "Could not read source from editor"
    line_count = len(source.split("\n"))

    if line_number is not None:
        if line_number < 1 or line_number > line_count:
            return None, f"Line {line_number} exceeds source length ({line_count} lines)"
        return line_number, None

    assert match_pattern is not None
    resolved = _resolve_match_pattern(source, match_pattern)
    if resolved is None:
        return None, f"Pattern '{match_pattern}' not found in source ({line_count} lines)"
    return resolved, None


def _build_breakpoint_confirm_message(
    object_type: Literal["PROG", "CLAS", "FUGR"],
    object_name: str,
    method_name: str | None,
    line_number: int,
) -> str:
    """Build the elicitation confirmation message for sap_breakpoint_set.

    Described as a toggle, not an unconditional "set" — _toggle_breakpoint_com
    deletes an existing breakpoint at the exact line instead of setting a new one,
    and this isn't known in advance without an extra COM round trip. However, when
    a deletion is detected, the tool re-applies the toggle to ensure the breakpoint
    ends up armed.
    """
    target = f"{object_type} {object_name}"
    if method_name:
        target += f" ({method_name})"
    return (
        f"About to toggle the external ABAP breakpoint on {target}, line {line_number}: "
        "if no breakpoint exists there yet, this SETS one; if one already exists at "
        "this exact line, SAP briefly clears it and this tool immediately re-arms it — "
        "either way the breakpoint ends up ARMED.\n\n"
        "Setting a breakpoint is dangerous: once it fires, SAP GUI opens a modal ABAP "
        "debugger that only a human can drive — there is no tool to step, continue, "
        "or read variables. While the debugger is open, COM calls may fail with a transient 'server busy' "
        "error until you dismiss it in SAP GUI.\n\n"
        "Proceed only if you intend to sit at the SAP GUI yourself and step through "
        "the debugger when it fires."
    )


def register_breakpoint_tools(mcp: FastMCP) -> None:  # pylint: disable=too-many-statements
    """Register breakpoint management tools with the MCP server."""

    @mcp.tool(
        description=(
            "HIGHLY DANGEROUS — DO NOT CALL unless a human user has explicitly asked for a breakpoint "
            "to be set. Live-verified (issue #791): once the breakpoint fires, SAP GUI opens a modal ABAP debugger "
            "that blocks the SAP GUI message loop. While it is open, COM calls may fail with a transient 'server busy' "
            "error and can affect multiple sessions in the same SAP GUI process. Dismiss the debugger in SAP "
            "GUI before retrying.\n\n"
            "Set an external ABAP breakpoint on a specific line of a program, class method, "
            "or function module. Desktop backend only — WebGUI does not support external breakpoints.\n\n"
            "Provide either line_number (1-indexed SAP display line) or match_pattern "
            "(substring or regex matched against source lines).\n\n"
            "SAP toggles breakpoints: if the line already has a breakpoint, VKey 45 deletes it. "
            "This tool only sets the breakpoint — it does not run anything.\n\n"
            "IMPORTANT — before calling this tool, ask the human operator for explicit permission "
            "and explain the consequences: there is NO tool to step, continue, or read variables in "
            "the resulting debugger. If the breakpoint later fires during a GUI run, SAP GUI opens a "
            "modal interactive ABAP debugger that only a human can drive — the agent cannot see or "
            "control it, and it may fire once per row/iteration if the code path repeats. Firing it "
            "can also destroy every other open session for this agent, as described above. Only "
            "proceed once the human has confirmed they intend to sit at the SAP GUI and step through "
            "the debugger themselves and accept the risk of losing all sessions; do not use this to "
            "silently 'verify a code path is reached' from an unattended flow."
        ),
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
    )
    async def sap_breakpoint_set(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements,too-many-branches
        object_type: Literal["PROG", "CLAS", "FUGR"],
        object_name: str,
        line_number: Annotated[int, PydanticField(gt=0)] | None = None,
        match_pattern: str | None = None,
        method_name: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
        ctx: Context | None = None,
    ) -> BreakpointSetResult:
        """Set an external ABAP breakpoint.

        Args:
            object_type: "PROG" for programs, "CLAS" for classes, "FUGR" for function groups.
            object_name: Program name, class name, or function group name.
            line_number: 1-indexed SAP display line. Mutually exclusive with match_pattern.
            match_pattern: Substring or regex matched against source. Mutually exclusive with line_number.
            method_name: Required for CLAS (method name) and FUGR (function module name).
            session: Session ID (e.g., "s1"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
            ctx: MCP request context, auto-injected by FastMCP. Used to ask the
                connected client for explicit confirmation before arming the
                breakpoint. Not part of the tool's client-visible parameters.
        """
        object_name = object_name.strip().upper()
        if method_name:
            method_name = method_name.strip().upper()

        if object_type in ("CLAS", "FUGR") and not method_name:
            return BreakpointSetResult.failure(
                error=f"method_name required for object_type={object_type}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        if (line_number is None) == (match_pattern is None):
            return BreakpointSetResult.failure(
                error="Provide exactly one of line_number or match_pattern",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        if match_pattern is not None:
            try:
                re.compile(match_pattern)
            except re.error as exc:
                return BreakpointSetResult.failure(
                    error=f"Invalid regex pattern '{match_pattern}': {exc}",
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_breakpoint_set")
        except ValueError as exc:
            return BreakpointSetResult.failure(
                error=f"Session error: {exc}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        if backend.backend_type != "desktop":
            return BreakpointSetResult.failure(
                error=_WEBGUI_ERROR,
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )
        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, DesktopBackend)  # noqa: S101

        try:
            nav_error = await _navigate_to_editor(backend, object_type, object_name, method_name)
            if nav_error:
                return BreakpointSetResult.failure(
                    error=nav_error,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            resolved_line, resolve_error = await _resolve_line_number(backend, line_number, match_pattern)
            if resolve_error:
                return BreakpointSetResult.failure(
                    error=resolve_error,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )
            assert resolved_line is not None

            confirm_message = _build_breakpoint_confirm_message(object_type, object_name, method_name, resolved_line)
            proceed, reason, confirmation_skipped = await confirm_destructive_action(ctx, confirm_message)
            if not proceed:
                return BreakpointSetResult.failure(
                    error=f"sap_breakpoint_set aborted: {reason}",
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                    line_number=resolved_line,
                )

            session_com = backend.require_session()
            shell_path = await backend.com.run(lambda: _resolve_shell_path_com(session_com, object_type))
            if shell_path is None:
                return BreakpointSetResult.failure(
                    error=f"Editor shell not found for {object_type} (tried all known paths)",
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            shell_found, status_msg = await backend.com.run(
                lambda: _toggle_breakpoint_com(session_com, shell_path, resolved_line)
            )
            if not shell_found:
                return BreakpointSetResult.failure(
                    error=status_msg,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            outcome = _classify_toggle_status(status_msg)
            if outcome == "deleted":
                # SAP deleted the breakpoint (was already set). Re-apply once.
                shell_found2, status_msg2 = await backend.com.run(
                    lambda: _toggle_breakpoint_com(session_com, shell_path, resolved_line)
                )
                if not shell_found2 or _classify_toggle_status(status_msg2) != "set":
                    return BreakpointSetResult.failure(
                        error=(
                            f"Toggle correction failed. "
                            f"First toggle: '{status_msg}', second toggle: '{status_msg2}'"
                        ),
                        object_type=object_type,
                        object_name=object_name,
                        method_name=method_name,
                        line_number=resolved_line,
                        status_message=status_msg2,
                    )
                return BreakpointSetResult(
                    success=True,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                    line_number=resolved_line,
                    action="set",
                    status_message=status_msg2,
                    confirmation_skipped=confirmation_skipped,
                )
            if outcome == "set":
                return BreakpointSetResult(
                    success=True,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                    line_number=resolved_line,
                    action="set",
                    status_message=status_msg,
                    confirmation_skipped=confirmation_skipped,
                )
            return BreakpointSetResult.failure(
                error=f"Unrecognized status bar message: '{status_msg}'",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
                line_number=resolved_line,
                status_message=status_msg,
            )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_breakpoint_set failed for %s/%s", object_type, object_name)
            return BreakpointSetResult.failure(
                error=f"Unexpected error: {exc}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

    @mcp.tool(
        description=(
            "Delete an external ABAP breakpoint on a specific line of a program, class method, "
            "or function module. Desktop backend only.\n\n"
            "Provide either line_number (1-indexed SAP display line) or match_pattern "
            "(substring or regex matched against source lines).\n\n"
            "If the line has no breakpoint, SAP sets one. This tool detects that and "
            "re-applies to undo it, then reports action='was_not_set'.\n\n"
            "Note: this only removes the breakpoint from the source editor. It does NOT step or "
            "continue a debugger that is currently stopped and showing a modal dialog — there is no "
            "tool for that; only a human at the SAP GUI can dismiss it."
        ),
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
    )
    async def sap_breakpoint_delete(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements,too-many-branches
        object_type: Literal["PROG", "CLAS", "FUGR"],
        object_name: str,
        line_number: Annotated[int, PydanticField(gt=0)] | None = None,
        match_pattern: str | None = None,
        method_name: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> BreakpointDeleteResult:
        """Delete an external ABAP breakpoint.

        Args:
            object_type: "PROG" for programs, "CLAS" for classes, "FUGR" for function groups.
            object_name: Program name, class name, or function group name.
            line_number: 1-indexed SAP display line. Mutually exclusive with match_pattern.
            match_pattern: Substring or regex matched against source. Mutually exclusive with line_number.
            method_name: Required for CLAS (method name) and FUGR (function module name).
            session: Session ID (e.g., "s1"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        object_name = object_name.strip().upper()
        if method_name:
            method_name = method_name.strip().upper()

        if object_type in ("CLAS", "FUGR") and not method_name:
            return BreakpointDeleteResult.failure(
                error=f"method_name required for object_type={object_type}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        if (line_number is None) == (match_pattern is None):
            return BreakpointDeleteResult.failure(
                error="Provide exactly one of line_number or match_pattern",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        if match_pattern is not None:
            try:
                re.compile(match_pattern)
            except re.error as exc:
                return BreakpointDeleteResult.failure(
                    error=f"Invalid regex pattern '{match_pattern}': {exc}",
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_breakpoint_delete")
        except ValueError as exc:
            return BreakpointDeleteResult.failure(
                error=f"Session error: {exc}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        if backend.backend_type != "desktop":
            return BreakpointDeleteResult.failure(
                error=_WEBGUI_ERROR,
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )
        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, DesktopBackend)  # noqa: S101

        try:
            nav_error = await _navigate_to_editor(backend, object_type, object_name, method_name)
            if nav_error:
                return BreakpointDeleteResult.failure(
                    error=nav_error,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            resolved_line, resolve_error = await _resolve_line_number(backend, line_number, match_pattern)
            if resolve_error:
                return BreakpointDeleteResult.failure(
                    error=resolve_error,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )
            assert resolved_line is not None

            session_com = backend.require_session()
            shell_path = await backend.com.run(lambda: _resolve_shell_path_com(session_com, object_type))
            if shell_path is None:
                return BreakpointDeleteResult.failure(
                    error=f"Editor shell not found for {object_type} (tried all known paths)",
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            shell_found, status_msg = await backend.com.run(
                lambda: _toggle_breakpoint_com(session_com, shell_path, resolved_line)
            )
            if not shell_found:
                return BreakpointDeleteResult.failure(
                    error=status_msg,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            outcome = _classify_toggle_status(status_msg)
            if outcome == "set":
                # SAP set a new breakpoint (line had no breakpoint). Re-apply to undo it.
                shell_found2, status_msg2 = await backend.com.run(
                    lambda: _toggle_breakpoint_com(session_com, shell_path, resolved_line)
                )
                if not shell_found2 or _classify_toggle_status(status_msg2) != "deleted":
                    return BreakpointDeleteResult.failure(
                        error=(
                            f"Toggle correction failed. "
                            f"First toggle: '{status_msg}', second toggle: '{status_msg2}'"
                        ),
                        object_type=object_type,
                        object_name=object_name,
                        method_name=method_name,
                        line_number=resolved_line,
                        status_message=status_msg2,
                    )
                return BreakpointDeleteResult(
                    success=True,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                    line_number=resolved_line,
                    action="was_not_set",
                    status_message=status_msg2,  # correction toggle's "gelöscht" message
                )
            if outcome == "deleted":
                return BreakpointDeleteResult(
                    success=True,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                    line_number=resolved_line,
                    action="deleted",
                    status_message=status_msg,
                )
            return BreakpointDeleteResult.failure(
                error=f"Unrecognized status bar message: '{status_msg}'",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
                line_number=resolved_line,
                status_message=status_msg,
            )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_breakpoint_delete failed for %s/%s", object_type, object_name)
            return BreakpointDeleteResult.failure(
                error=f"Unexpected error: {exc}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

    @mcp.tool(
        description=(
            "List all external ABAP breakpoints for the current user on a program, "
            "class method, or function module. Desktop backend only.\n\n"
            "Opens 'Hilfsmittel > Breakpoints > Anzeigen...' dialog in the source editor, "
            "reads the grid, and returns matching breakpoints.\n\n"
            "Note: if a breakpoint is currently stopped in a modal debugger on this session, this "
            "tool will report the session as busy rather than opening the dialog — dismiss the "
            "debugger in the SAP GUI first."
        ),
        annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    )
    async def sap_breakpoint_list(  # pylint: disable=too-many-return-statements,too-many-locals
        object_type: Literal["PROG", "CLAS", "FUGR"],
        object_name: str,
        method_name: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> BreakpointListResult:
        """List all external breakpoints on an ABAP object.

        Args:
            object_type: "PROG" for programs, "CLAS" for classes, "FUGR" for function groups.
            object_name: Program name, class name, or function group name.
            method_name: Required for CLAS (method name) and FUGR (function module name).
            session: Session ID (e.g., "s1"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        object_name = object_name.strip().upper()
        if method_name:
            method_name = method_name.strip().upper()

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_breakpoint_list")
        except ValueError as exc:
            return BreakpointListResult.failure(
                error=f"Session error: {exc}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        if backend.backend_type != "desktop":
            return BreakpointListResult.failure(
                error=_WEBGUI_ERROR,
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )
        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        # pylint: disable-next=import-outside-toplevel
        from sapguimcp.backend.desktop._com_thread import is_transient_busy_error

        assert isinstance(backend, DesktopBackend)  # noqa: S101

        if object_type in ("CLAS", "FUGR") and not method_name:
            return BreakpointListResult.failure(
                error=f"method_name required for object_type={object_type}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )

        try:
            nav_error = await _navigate_to_editor(backend, object_type, object_name, method_name)
            if nav_error:
                return BreakpointListResult.failure(
                    error=nav_error,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            session_com = backend.require_session()

            opened, open_error = await backend.com.run(lambda: _open_bp_list_dialog_com(session_com))
            if not opened:
                return BreakpointListResult.failure(
                    error=open_error,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            rows, read_error = await backend.com.run(lambda: _read_bp_grid_and_close_com(session_com))
            if read_error:
                return BreakpointListResult.failure(
                    error=read_error,
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )

            entries = _filter_bp_rows(rows, object_type, object_name, method_name)
            return BreakpointListResult(
                success=True,
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
                breakpoints=entries,
            )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            if is_transient_busy_error(exc):
                return BreakpointListResult.failure(
                    error=(
                        "Session busy: a modal dialog (e.g. an ABAP debugger stopped at a "
                        "breakpoint) is blocking the SAP GUI message loop. Dismiss it in the "
                        "SAP GUI, then retry."
                    ),
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                )
            logger.exception("sap_breakpoint_list failed for %s/%s", object_type, object_name)
            return BreakpointListResult.failure(
                error=f"Unexpected error: {exc}",
                object_type=object_type,
                object_name=object_name,
                method_name=method_name,
            )
