"""
SE37 (Function Module) edit tool.

Provides sap_se37_edit for modifying existing function modules with
syntax check, activation, and auto-revert on failure.
"""

import logging

from fastmcp import FastMCP

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.protocol import SapUiBackend
from sapwebguimcp.models.se37_edit_models import SE37EditResult

logger = logging.getLogger(__name__)


async def _open_fm_in_change_mode(backend: SapUiBackend, function_module: str) -> str | None:
    """Navigate to SE37, display FM via F7, and toggle to change mode.

    Returns error message or None on success.
    """
    await backend.enter_transaction("SE37")

    # Fill FM name field (DE: "Funktionsbaustein", EN: "Function Module")
    for label in ("Funktionsbaustein", "Function Module", "Function module"):
        try:
            await backend.fill_field(label, function_module)
            break
        except ValueError:
            continue
    else:
        # Fallback: fill main form input, skipping toolbar/combobox inputs.
        if not await backend.fill_main_input(
            function_module, ["Funktionsbaustein", "Function Module", "Function module"]
        ):
            return "Could not find function module name field"

    # F7 to display first (reliable in both DE/EN), then toggle to change mode
    await backend.press_key("F7")
    await backend.wait_for_ready()

    snapshot = str(await backend.get_snapshot())
    if "Function Builder" not in snapshot and "Funktionsbaustein" not in snapshot:
        return f"F7 failed to display function module. Page: {snapshot[:400]}"

    await backend.dismiss_language_dialog()

    # Switch from display to change mode via toggle button
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


async def _click_source_tab(backend: SapUiBackend) -> str | None:
    """Click the source code tab in SE37. Returns error or None on success."""
    for tab_name in ("Quelltext", "Source Code", "Source code", "Source text"):
        try:
            await backend.click_tab(tab_name)
            await backend.wait_for_ready()
            return None
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    snapshot = await backend.get_snapshot()
    return f"Could not find source code tab. Page: {str(snapshot)[:500]}"


async def _navigate_to_fm_editor(backend: SapUiBackend, function_module: str) -> str | None:
    """Navigate to SE37, open FM in change mode, click source tab.

    Returns error message or None on success.
    """
    error = await _open_fm_in_change_mode(backend, function_module)
    if error:
        return error
    return await _click_source_tab(backend)


async def _edit_check_activate_fm(backend: SapUiBackend, function_module: str, new_source: str) -> SE37EditResult:
    """Core edit logic: navigate, read backup, replace, check, activate, revert on failure."""
    nav_error = await _navigate_to_fm_editor(backend, function_module)
    if nav_error:
        return SE37EditResult.failure(
            error=nav_error, function_module=function_module, backup_source="", activated=False
        )

    # Read current source (backup)
    backup_source = await backend.read_editor_source() or ""
    if not backup_source:
        return SE37EditResult.failure(
            error="Could not read current source code from editor. Is the function module accessible?",
            function_module=function_module,
            backup_source="",
            activated=False,
        )

    logger.info("SE37 edit: backup saved for %s (%d chars)", function_module, len(backup_source))

    # Replace editor content
    replaced = await backend.replace_editor_source(new_source)
    if not replaced:
        return SE37EditResult.failure(
            error="Failed to replace editor content",
            function_module=function_module,
            backup_source=backup_source,
            activated=False,
        )

    # Check and activate
    result = await backend.check_and_activate()

    if not result.success:
        logger.warning("SE37 edit: check/activate failed for %s, reverting", function_module)
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

        return SE37EditResult.failure(
            error=f"Check/activate failed: {'; '.join(result.messages)}",
            function_module=function_module,
            backup_source=backup_source,
            check_messages=result.messages,
            activated=False,
        )

    return SE37EditResult(
        success=True,
        function_module=function_module,
        backup_source=backup_source,
        check_messages=result.messages,
        activated=result.activated,
    )


def register_se37_edit_tools(mcp: FastMCP) -> None:
    """Register SE37 edit tools with the MCP server."""

    @mcp.tool(
        description=(
            "Edit an existing ABAP function module in SE37.\n\n"
            "Replaces the entire source code, runs syntax check (Ctrl+F2), "
            "and activates (Ctrl+F3). Auto-reverts if check or activation fails.\n\n"
            "**Important:** Only for EXISTING function modules. To create new ones, use abapGit.\n\n"
            "**Workflow:** Read current source with sap_se37_lookup first (check the Quelltext/Source Code tab), "
            "modify it, then call this tool with the full new source."
        ),
        annotations={
            "destructiveHint": True,
            "readOnlyHint": False,
            "idempotentHint": False,
        },
    )
    async def sap_se37_edit(
        function_module: str,
        new_source: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE37EditResult:
        """Edit an existing function module, check syntax, and activate.

        Args:
            function_module: Name of the function module (e.g., 'Z_TEST_MCP_EDIT').
            new_source: Complete new ABAP source code to replace the current code.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE37EditResult with success status, backup source, and check messages.
        """
        function_module = function_module.strip().upper()

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se37_edit")
        except ValueError as exc:
            return SE37EditResult.failure(
                error=f"Session error: {exc}",
                function_module=function_module,
                backup_source="",
                activated=False,
            )

        try:
            return await _edit_check_activate_fm(backend, function_module, new_source)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("SE37 edit failed for %s", function_module)
            return SE37EditResult.failure(
                error=f"Unexpected error: {exc}",
                function_module=function_module,
                backup_source="",
                activated=False,
            )
