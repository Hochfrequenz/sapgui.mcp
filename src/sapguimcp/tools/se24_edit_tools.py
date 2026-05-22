"""
SE24 (Class Builder) edit tool.

Provides sap_se24_edit for modifying existing class methods with
syntax check, activation, and auto-revert on failure.

Unlike SE38/SE37 which edit entire program/FM source, SE24 edits
individual method source code within a class.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

from fastmcp import FastMCP

from sapguimcp.backend.manager import get_backend
from sapguimcp.models.se24_edit_models import SE24EditResult
from sapguimcp.tools.field_helpers import fill_field_with_keyboard, toggle_to_change_mode

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

_SE24_LABELS = ("Objekttyp", "Object Type")


async def _fill_class_field(backend: WebGuiBackend | DesktopBackend, class_name: str, attempt: int) -> bool:
    """Fill the SE24 class name field. attempt==0 uses JS, retries use keyboard."""
    if attempt == 0:
        for label in _SE24_LABELS:
            try:
                await backend.fill_field(label, class_name)
                return True
            except ValueError:
                continue
        return await backend.fill_main_input(class_name, list(_SE24_LABELS))
    return await fill_field_with_keyboard(backend, _SE24_LABELS, class_name)


async def _open_class_in_change_mode(backend: WebGuiBackend | DesktopBackend, class_name: str) -> str | None:
    """Navigate to SE24, display class via F7, and toggle to change mode.

    Returns error message or None on success.
    """
    # bring_to_front is required for SE24: without it, F7/field interactions fail silently
    await backend.bring_to_front()

    await backend.enter_transaction("SE24")

    # Fill class name and press F7. First attempt uses JS fill (fast),
    # retries use real keyboard events (survives SAP state resets after /n).
    for attempt in range(3):
        if attempt > 0:
            logger.info("Retrying fill+F7 for %s (attempt %d)", class_name, attempt + 1)
            await asyncio.sleep(1.0)

        filled = await _fill_class_field(backend, class_name, attempt)
        if not filled:
            logger.warning("Class name field not found (attempt %d)", attempt + 1)
            continue

        # Brief wait for SAP to register the typed value before pressing F7.
        await asyncio.sleep(0.3)
        await backend.press_key("F7")
        await backend.wait_for_ready()

        # Check if we left the initial screen.
        snapshot = str(await backend.get_snapshot())
        if "Class Builder" in snapshot or "Klasse" in snapshot:
            break
    else:
        return "Could not find or fill class name field after retries"

    await backend.dismiss_language_dialog()

    return await toggle_to_change_mode(backend)


async def _select_method_and_open_source(
    backend: WebGuiBackend | DesktopBackend, class_name: str, method_name: str
) -> str | None:
    """Select method in methods grid and open its source editor.

    Returns error message or None on success.
    """
    # Ensure we're on the Methods tab (DE: "Methoden", EN: "Methods")
    for tab_label in ("Methoden", "Methods"):
        try:
            await backend.click_tab(tab_label)
            break
        except ValueError:
            continue
    else:
        return "Could not find 'Methoden'/'Methods' tab"
    await backend.wait_for_ready()

    # Select the method in the grid by finding it in the table
    table = await backend.read_table()
    row_index = None
    for i, row in enumerate(table.rows):
        if any(method_name.upper() in v.upper() for v in row.data.values() if v):
            row_index = i
            break
    if row_index is None:
        snapshot = await backend.get_snapshot()
        logger.warning(
            "SE24 edit: method %s not found for %s. Screen: %s",
            method_name,
            class_name,
            str(snapshot)[:200],
        )
        return f"Method '{method_name}' not found in class '{class_name}' methods grid"
    await backend.click_table_cell(row_index + 1, 0, "click")  # 1-based row index
    await backend.wait_for_ready()

    # Click "Quelltext" / "Sourcecode" / "Source Code" button to open method source
    for btn_name in ("Quelltext", "Sourcecode", "Source Code", "Source code"):
        try:
            await backend.click_button(btn_name)
            await backend.wait_for_ready()
            break
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    else:
        return "Could not find 'Quelltext'/'Sourcecode' button"

    return None


async def _open_class_in_change_mode_desktop(backend: WebGuiBackend | DesktopBackend, class_name: str) -> str | None:
    """Desktop-specific: navigate to SE24, display class, toggle to change mode."""
    await backend.enter_transaction("SE24")
    await backend.wait_for_ready()

    filled = await backend.focus_and_type("SEOCLASS-CLSNAME", class_name.upper())
    if not filled:
        filled = await fill_field_with_keyboard(backend, _SE24_LABELS, class_name.upper())
    if not filled:
        return "Could not fill class name field on desktop"

    await asyncio.sleep(0.3)
    await backend.press_key("F7")  # Display
    await backend.wait(2000)

    # Dismiss language dialog ("Different original and logon languages")
    try:
        await backend.press_key("Enter")
        await backend.wait(1000)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Verify we left the initial screen
    screen = await backend.get_screen_info()
    title = (screen.title or "").lower()
    if "einstieg" in title or "initial" in title:
        sbar = await backend.get_status_bar()
        return sbar.message or f"Could not display class '{class_name}'"

    # Toggle to change mode: Ctrl+F1 (the toolbar button has no text on desktop,
    # so toggle_to_change_mode's label-based click_button won't find it).
    await backend.press_key("Ctrl+F1")
    await backend.wait(1000)
    return None


async def _select_method_and_open_source_desktop(  # pylint: disable=too-many-return-statements
    backend: WebGuiBackend | DesktopBackend, class_name: str, method_name: str
) -> str | None:
    """Desktop-specific: find method in table control and open its source editor."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return "Requires DesktopBackend"

    # Ensure we're on the Methods tab
    for tab_label in ("Methoden", "Methods"):
        try:
            await backend.click_tab(tab_label)
            await backend.wait(500)
            break
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    session = backend.require_session()
    com = backend.com

    def _select_method_row() -> str | None:
        """Find the method row in the table control and select it."""
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

            # Find the method name column
            method_col = -1
            for c in range(col_count):
                title = raw.Columns(c).Title or raw.Columns(c).Name
                if title in ("Methode", "Method"):
                    method_col = c
                    break
            if method_col < 0:
                continue

            # Find and select the method row
            for r in range(visible):
                try:
                    cell_text = raw.GetCell(r, method_col).Text
                    if cell_text.upper().strip() == method_name.upper():
                        raw.GetCell(r, method_col).SetFocus()
                        return None
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            return f"Method '{method_name}' not found in class '{class_name}' methods table"
        return "No table control found on SE24 screen"

    select_error = await com.run(_select_method_row)
    if select_error:
        return select_error

    await backend.wait(500)

    # Click "Quelltext" / "Sourcecode" button to open method source editor
    for btn_name in ("Quelltext", "Sourcecode", "Source Code", "Source code", "Weiter zu Quelltext"):
        try:
            await backend.click_button(btn_name)
            await backend.wait(2000)
            return None
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return "Could not find 'Quelltext'/'Sourcecode' button"


async def _navigate_to_method_editor_desktop(
    backend: WebGuiBackend | DesktopBackend, class_name: str, method_name: str
) -> str | None:
    """Desktop: navigate to SE24, open class in change mode, select method, open source."""
    error = await _open_class_in_change_mode_desktop(backend, class_name)
    if error:
        return error
    return await _select_method_and_open_source_desktop(backend, class_name, method_name)


async def _navigate_to_method_editor(
    backend: WebGuiBackend | DesktopBackend, class_name: str, method_name: str
) -> str | None:
    """Navigate to SE24, open class in change mode, select method, open source editor.

    Returns error message or None on success.
    """
    error = await _open_class_in_change_mode(backend, class_name)
    if error:
        return error
    return await _select_method_and_open_source(backend, class_name, method_name)


async def _edit_check_activate_method(
    backend: WebGuiBackend | DesktopBackend, class_name: str, method_name: str, new_source: str
) -> SE24EditResult:
    """Core edit logic: navigate, read backup, replace, check, activate, revert on failure."""
    if backend.backend_type == "desktop":
        nav_error = await _navigate_to_method_editor_desktop(backend, class_name, method_name)
    else:
        nav_error = await _navigate_to_method_editor(backend, class_name, method_name)
    if nav_error:
        return SE24EditResult.failure(
            error=nav_error, class_name=class_name, method_name=method_name, backup_source="", activated=False
        )

    # Read current source (backup)
    backup_source = await backend.read_editor_source() or ""
    if not backup_source:
        return SE24EditResult.failure(
            error="Could not read current method source code from editor. Is the class/method accessible?",
            class_name=class_name,
            method_name=method_name,
            backup_source="",
            activated=False,
        )

    logger.info("SE24 edit: backup saved for %s->%s (%d chars)", class_name, method_name, len(backup_source))

    # Replace editor content
    replaced = await backend.replace_editor_source(new_source)
    if not replaced:
        return SE24EditResult.failure(
            error="Failed to replace editor content",
            class_name=class_name,
            method_name=method_name,
            backup_source=backup_source,
            activated=False,
        )

    # Check and activate
    result = await backend.check_and_activate()

    if not result.success:
        logger.warning("SE24 edit: check/activate failed for %s->%s, reverting", class_name, method_name)
        reverted = await backend.replace_editor_source(backup_source)
        if reverted:
            revert_result = await backend.check_and_activate()
            if revert_result.success:
                result.messages.append("Auto-reverted to original source and re-activated successfully")
            else:
                result.messages.append(
                    f"Auto-reverted source but re-activation failed: {'; '.join(revert_result.messages)}"
                )
        else:
            result.messages.append("WARNING: Auto-revert failed! Manual intervention needed.")

        return SE24EditResult.failure(
            error=f"Check/activate failed: {'; '.join(result.messages)}",
            class_name=class_name,
            method_name=method_name,
            backup_source=backup_source,
            check_messages=result.messages,
            activated=False,
        )

    return SE24EditResult(
        success=True,
        class_name=class_name,
        method_name=method_name,
        backup_source=backup_source,
        check_messages=result.messages,
        activated=result.activated,
    )


def register_se24_edit_tools(mcp: FastMCP) -> None:
    """Register SE24 edit tools with the MCP server."""

    @mcp.tool(
        description=(
            "Edit an existing class method in SE24 (Class Builder). "
            "If sap-adt is available, prefer its patch_source or "
            "set_source_from_file tools — faster, no GUI needed.\n\n"
            "Replaces the method's source code, runs syntax check (Ctrl+F2), "
            "and activates (Ctrl+F3). Auto-reverts if check or activation fails.\n\n"
            "**Important:** Only for EXISTING classes and methods. To create new ones, use abapGit.\n\n"
            "**Workflow:** Read current class with sap_se24_lookup first to see methods, "
            "then call this tool with the full new method source."
        ),
        annotations={
            "destructiveHint": True,
            "readOnlyHint": False,
            "idempotentHint": False,
        },
    )
    async def sap_se24_edit(
        class_name: str,
        method_name: str,
        new_source: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE24EditResult:
        """Edit an existing class method, check syntax, and activate.

        Args:
            class_name: Name of the class (e.g., 'ZCL_TEST_MCP_EDIT').
            method_name: Name of the method to edit (e.g., 'DO_SOMETHING').
            new_source: Complete new ABAP method source code to replace the current code.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE24EditResult with success status, backup source, and check messages.
        """
        class_name = class_name.strip().upper()
        method_name = method_name.strip().upper()

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se24_edit")
        except ValueError as exc:
            return SE24EditResult.failure(
                error=f"Session error: {exc}",
                class_name=class_name,
                method_name=method_name,
                backup_source="",
                activated=False,
            )

        try:
            return await _edit_check_activate_method(backend, class_name, method_name, new_source)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("SE24 edit failed for %s->%s", class_name, method_name)
            return SE24EditResult.failure(
                error=f"Unexpected error: {exc}",
                class_name=class_name,
                method_name=method_name,
                backup_source="",
                activated=False,
            )
