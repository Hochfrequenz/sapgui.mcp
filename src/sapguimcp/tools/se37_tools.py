"""
SE37 (Function Builder) lookup tool.

This module provides a tool to look up function module metadata from SE37,
returning strongly-typed Pydantic models with parameter and exception details.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.se37_parser import SE37TabSnapshots, parse_se37_snapshot
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.models import (
    SE37Entry,
    SE37Error,
    SE37FileSummary,
    SE37Result,
)
from sapguimcp.models.se37_models import SE37Exception, SE37Parameter, SE37ParameterCategory, SE37TypingMethod
from sapguimcp.tools.field_helpers import fill_and_display
from sapguimcp.tools.table_helpers import read_table_control

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_se37_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 5


# =============================================================================
# SE37 Navigation Helpers
# =============================================================================


# DE/EN label variants for the function module input field.
_FM_FIELD_LABELS = [
    "Funktionsbaustein",
    "Function module",
    "Function Module",
]


async def _click_tab_bilingual(backend: WebGuiBackend | DesktopBackend, de_label: str, en_label: str) -> None:
    """Click a tab trying DE then EN label."""
    for label in [de_label, en_label]:
        try:
            await backend.click_tab(label)
            await backend.wait(500)
            return
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    logger.warning("Tab not found: %s / %s", de_label, en_label)


def _read_se37_table_control(session: Any, _flatten_fn: Any) -> list[dict[str, str]]:
    """Find and read the first GuiTableControl (type 80) on screen.

    Scrolls through all rows with a settle delay after each scrollbar change
    to avoid COM ``RPC_E_SERVERCALL_RETRYLATER`` errors (#387).
    """
    return read_table_control(session, _flatten_fn)


def _parse_se37_params(rows: list[dict[str, str]], category: SE37ParameterCategory) -> list[SE37Parameter]:
    """Parse parameter rows from an SE37 tab into SE37Parameter models."""
    params: list[SE37Parameter] = []
    for row in rows:
        name = row.get("Parametername", row.get("Parameter Name", ""))
        if not name:
            continue
        typing_raw = row.get("Typisierung", row.get("Typing", "")).upper()
        typing: SE37TypingMethod = "TYPE" if "TYPE" in typing_raw else "LIKE"
        params.append(
            SE37Parameter(
                name=name,
                category=category,
                typing=typing,
                reference_type=row.get("Bezugstyp", row.get("Associated Type", "")),
                default_value=row.get("Standardwert", row.get("Default Value", None)) or None,
                optional="X" in row.get("Optional", "").upper(),
                pass_by_value="X" in row.get("Wertübergabe", row.get("Pass Value", "")).upper(),
                description=row.get("Kurztext", row.get("Short Text", "")),
            )
        )
    return params


async def _lookup_fm_desktop(  # pylint: disable=too-many-locals
    backend: WebGuiBackend | DesktopBackend, fm_name: str
) -> SE37Entry | SE37Error:
    """Desktop-specific SE37 lookup using tab navigation and table control reading."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)
    await backend.wait_for_ready()

    # Fill FM name field
    filled = False
    for label in _FM_FIELD_LABELS:
        try:
            await backend.fill_field(label, fm_name.upper())
            filled = True
            break
        except ValueError:
            continue
    if not filled:
        filled = await backend.focus_and_type("RS38L-NAME", fm_name.upper())
    if not filled:
        return SE37Error(function_module=fm_name, error="Could not fill function module field", retrieved_at=now)

    # Press F7 (Display)
    await backend.press_key("F7")
    await backend.wait(2000)

    # Check status bar for errors
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return SE37Error(function_module=fm_name, error=sbar.message or "Function module not found", retrieved_at=now)

    # Verify we navigated to the FM display screen
    screen = await backend.get_screen_info()
    if fm_name.upper() not in (screen.title or "").upper():
        return SE37Error(
            function_module=fm_name, error=sbar.message or f"Function module '{fm_name}' not found", retrieved_at=now
        )

    if not isinstance(backend, DesktopBackend):
        return SE37Error(function_module=fm_name, error="Requires DesktopBackend", retrieved_at=now)

    session = backend.require_session()
    com = backend.com

    # Read Import tab: try reading first (default tab), click only if table is empty.
    # SAP lazily instantiates tab subscreen controls — the table control may not
    # exist in the widget tree until the tab is explicitly activated by a click.
    import_rows = await com.run(lambda: _read_se37_table_control(session, _flatten))
    if not import_rows:
        await _click_tab_bilingual(backend, "Import", "Import")
        import_rows = await com.run(lambda: _read_se37_table_control(session, _flatten))

    # Read Export tab
    await _click_tab_bilingual(backend, "Export", "Export")
    export_rows = await com.run(lambda: _read_se37_table_control(session, _flatten))

    # Read Changing tab
    await _click_tab_bilingual(backend, "Changing", "Changing")
    changing_rows = await com.run(lambda: _read_se37_table_control(session, _flatten))

    # Read Tables tab
    await _click_tab_bilingual(backend, "Tabellen", "Tables")
    tables_rows = await com.run(lambda: _read_se37_table_control(session, _flatten))

    # Read Exceptions tab
    await _click_tab_bilingual(backend, "Ausnahmen", "Exceptions")
    exc_rows = await com.run(lambda: _read_se37_table_control(session, _flatten))

    # Parse exceptions
    exceptions: list[SE37Exception] = []
    for row in exc_rows:
        name = row.get("Ausnahme", row.get("Exception", ""))
        if name:
            exceptions.append(SE37Exception(name=name, description=row.get("Kurztext", row.get("Short Text", ""))))

    # Read description from fields
    fields = await backend.discover_fields()
    description = ""
    for f in fields:
        if f.name and "STEXT" in f.name.upper():
            description = f.value or ""
            break

    return SE37Entry(
        function_module=fm_name.upper(),
        description=description,
        import_parameters=_parse_se37_params(import_rows, "import"),
        export_parameters=_parse_se37_params(export_rows, "export"),
        changing_parameters=_parse_se37_params(changing_rows, "changing"),
        tables_parameters=_parse_se37_params(tables_rows, "tables"),
        exceptions=exceptions,
        retrieved_at=now,
    )


async def _capture_tab_snapshot(backend: WebGuiBackend | DesktopBackend, tab_name: str) -> str | None:
    """Click a tab and capture its snapshot. Returns snapshot or None."""
    # Try German and English tab names
    tab_names = {
        "import": ["Import"],
        "export": ["Export"],
        "changing": ["Changing"],
        "tables": ["Tabellen", "Tables"],
        "exceptions": ["Ausnahmen", "Exceptions"],
    }

    names_to_try = tab_names.get(tab_name, [tab_name])
    for name in names_to_try:
        try:
            await backend.click_tab(name)
            snapshot = await backend.get_snapshot()
            return str(snapshot)
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return None


async def _lookup_fm_on_initial_screen(backend: WebGuiBackend | DesktopBackend, fm_name: str) -> SE37Entry | SE37Error:
    """Look up a function module assuming we're already on the SE37 initial screen.

    The caller handles navigation (``enter_transaction``) and state reset
    (``/n`` between lookups) to prevent state bleeding in batch mode.
    """
    # Ensure the SE37 screen is fully loaded before interacting.
    await backend.wait_for_ready()

    # Fill field with real keyboard events, press F7, and verify navigation.
    error_msg = await fill_and_display(backend, _FM_FIELD_LABELS, fm_name, tcode_label="function module")
    if error_msg:
        return SE37Error(
            function_module=fm_name,
            error=error_msg,
            retrieved_at=datetime.now(UTC),
        )

    # Get main snapshot first
    main_snapshot = await backend.get_snapshot()
    logger.debug("Got main snapshot", extra={"object": fm_name, "length": len(str(main_snapshot))})

    # Capture each tab
    import_raw = await _capture_tab_snapshot(backend, "import")
    export_raw = await _capture_tab_snapshot(backend, "export")
    changing_raw = await _capture_tab_snapshot(backend, "changing")
    tables_raw = await _capture_tab_snapshot(backend, "tables")
    exceptions_raw = await _capture_tab_snapshot(backend, "exceptions")
    tab_snapshots = SE37TabSnapshots(
        import_tab=AriaSnapshot(import_raw) if import_raw is not None else None,
        export_tab=AriaSnapshot(export_raw) if export_raw is not None else None,
        changing_tab=AriaSnapshot(changing_raw) if changing_raw is not None else None,
        tables_tab=AriaSnapshot(tables_raw) if tables_raw is not None else None,
        exceptions_tab=AriaSnapshot(exceptions_raw) if exceptions_raw is not None else None,
    )

    # Parse all snapshots
    return parse_se37_snapshot(
        snapshot=AriaSnapshot(str(main_snapshot)),
        fm_name=fm_name,
        tab_snapshots=tab_snapshots,
    )


async def _lookup_batch_se37_webgui(backend: WebGuiBackend | DesktopBackend, fm_list: list[str]) -> SE37Result:
    """Run SE37 lookups for a batch of function modules on the WebGUI backend."""
    entries: list[SE37Entry] = []
    errors: list[SE37Error] = []
    for fm_name in fm_list:
        await backend.enter_transaction("/n")
        await backend.wait_for_ready()
        tx_result = await backend.enter_transaction("SE37")
        if not tx_result.success:
            errors.append(
                SE37Error(
                    function_module=fm_name,
                    error=f"Failed to navigate: {tx_result.error}",
                    retrieved_at=datetime.now(UTC),
                )
            )
            continue
        await backend.wait_for_ready()
        try:
            result = await _lookup_fm_on_initial_screen(backend, fm_name)
            if isinstance(result, SE37Entry):
                entries.append(result)
            else:
                errors.append(result)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Looking up in SE37", extra={"object": fm_name})
            errors.append(SE37Error(function_module=fm_name, error=f"Error: {e}", retrieved_at=datetime.now(UTC)))
    if entries:
        return SE37Result(entries=entries, errors=errors)
    return SE37Result.failure(error=f"All {len(errors)} lookups failed", entries=[], errors=errors)


async def _lookup_batch_se37_desktop(backend: WebGuiBackend | DesktopBackend, fm_list: list[str]) -> SE37Result:
    """Run SE37 lookups for a batch of function modules on the desktop backend."""
    entries: list[SE37Entry] = []
    errors: list[SE37Error] = []
    for fm_name in fm_list:
        await backend.enter_transaction("/n")
        await backend.wait_for_ready()
        tx_result = await backend.enter_transaction("SE37")
        if not tx_result.success:
            errors.append(
                SE37Error(
                    function_module=fm_name,
                    error=f"Failed to navigate: {tx_result.error}",
                    retrieved_at=datetime.now(UTC),
                )
            )
            continue
        await backend.wait_for_ready()
        try:
            result = await _lookup_fm_desktop(backend, fm_name)
            if isinstance(result, SE37Entry):
                entries.append(result)
            else:
                errors.append(result)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("SE37 desktop lookup failed", extra={"fm_name": fm_name})
            errors.append(SE37Error(function_module=fm_name, error=f"Error: {e}", retrieved_at=datetime.now(UTC)))
    if entries:
        return SE37Result(entries=entries, errors=errors)
    return SE37Result.failure(error=f"All {len(errors)} lookups failed", entries=[], errors=errors)


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se37_tools(mcp: FastMCP) -> None:
    """Register SE37 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up function module metadata from SE37 (Function Builder). "
            "If sap-adt is available, prefer its get_source tool for reading FM source code. "
            "USE THIS instead of sap_transaction('SE37') - faster and returns structured data. "
            "Returns function module signature including import/export/changing/tables parameters "
            "and exceptions. Supports single FM or list of FMs. "
            "Each parameter includes: name, typing (LIKE/TYPE), reference type, "
            "default value, optional flag, and description."
        ),
    )
    async def sap_se37_lookup(
        function_modules: str | list[str],
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE37Result | SE37FileSummary:
        """
        Look up function module metadata from SE37.

        Args:
            function_modules: Single FM name or list of names
                (e.g., 'RFC_READ_TABLE' or ['RFC_READ_TABLE', 'BAPI_USER_GET_DETAIL'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >5 function modules to avoid context overflow.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE37Result with entries and errors (inline), or
            SE37FileSummary with file path and statistics (when output_file provided)
        """
        fm_list = [function_modules] if isinstance(function_modules, str) else list(function_modules)

        if not fm_list:
            return SE37Result.failure("No function modules provided")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se37_lookup")
        except ValueError as e:
            return SE37Result.failure(f"Session error: {e}")

        # Route to desktop or WebGUI batch lookup
        if backend.backend_type == "desktop":
            final_result = await _lookup_batch_se37_desktop(backend, fm_list)
        else:
            final_result = await _lookup_batch_se37_webgui(backend, fm_list)

        # Write to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(final_result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SE37FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(fm_list),
                successful=len(final_result.entries),
                failed=len(final_result.errors),
                sample_entries=[e.function_module for e in final_result.entries[:5]],
                sample_errors=[e.function_module for e in final_result.errors[:5]],
            )

        if len(fm_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning function modules inline - consider using output_file parameter",
                extra={"count": len(fm_list)},
            )

        return final_result
