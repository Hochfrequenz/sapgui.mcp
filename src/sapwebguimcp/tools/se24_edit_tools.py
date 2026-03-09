"""
SE24 (Class Builder) edit tool.

Provides sap_se24_edit for modifying existing class methods with
syntax check, activation, and auto-revert on failure.

Unlike SE38/SE37 which edit entire program/FM source, SE24 edits
individual method source code within a class.
"""

import logging

from fastmcp import FastMCP

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.protocol import SapUiBackend
from sapwebguimcp.models.se24_edit_models import SE24EditResult

logger = logging.getLogger(__name__)


async def _open_class_in_change_mode(backend: SapUiBackend, class_name: str) -> str | None:
    """Navigate to SE24, display class via F7, and toggle to change mode.

    Returns error message or None on success.
    """
    # bring_to_front is required for SE24: without it, F7/field interactions fail silently
    await backend.bring_to_front()

    await backend.enter_transaction("SE24")

    # Fill class name field (DE: "Objekttyp", EN: "Object Type")
    for label in ("Objekttyp", "Object Type"):
        try:
            await backend.fill_field(label, class_name)
            break
        except ValueError:
            continue
    else:
        # Fallback: fill first visible input by CSS selector
        try:
            fields = await backend.discover_fields()
            if fields and fields[0].selector:
                await backend.fill_field(fields[0].selector, class_name)
            else:
                return "Could not find class name field"
        except (ValueError, Exception):  # pylint: disable=broad-exception-caught
            return "Could not find class name field"

    # F7 to display first (reliable in both DE/EN), then toggle to change mode
    await backend.press_key("F7")
    await backend.wait_for_ready()

    snapshot = str(await backend.get_snapshot())
    if "Class Builder" not in snapshot and "Klasse" not in snapshot:
        return f"F7 failed to display class. Page: {snapshot[:400]}"

    await backend.dismiss_language_dialog()

    # Switch from display to change mode via "Display <-> Change" / "Anzeigen <-> Ändern"
    for toggle_label in ("Anzeigen <-> Ändern", "Display <-> Change"):
        try:
            await backend.click_button(toggle_label)
            break
        except ValueError:
            continue
    else:
        return "Could not find 'Display <-> Change' toggle button"
    await backend.wait_for_ready()

    await backend.dismiss_language_dialog()
    return None


async def _select_method_and_open_source(backend: SapUiBackend, class_name: str, method_name: str) -> str | None:
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


async def _navigate_to_method_editor(backend: SapUiBackend, class_name: str, method_name: str) -> str | None:
    """Navigate to SE24, open class in change mode, select method, open source editor.

    Returns error message or None on success.
    """
    error = await _open_class_in_change_mode(backend, class_name)
    if error:
        return error
    return await _select_method_and_open_source(backend, class_name, method_name)


async def _edit_check_activate_method(
    backend: SapUiBackend, class_name: str, method_name: str, new_source: str
) -> SE24EditResult:
    """Core edit logic: navigate, read backup, replace, check, activate, revert on failure."""
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
            "Edit an existing class method in SE24 (Class Builder).\n\n"
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
