"""
SE38 (ABAP Report Editor) edit tool.

Provides sap_se38_edit for modifying existing ABAP reports with
syntax check, activation, and auto-revert on failure.
"""

import logging

from fastmcp import FastMCP

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.protocol import SapUiBackend
from sapwebguimcp.models.se38_edit_models import SE38EditResult

logger = logging.getLogger(__name__)


async def _navigate_and_open_editor(backend: SapUiBackend, program_name: str) -> str | None:
    """Navigate to SE38 on the given page, fill program name, enter change mode, return error or None."""
    await backend.enter_transaction("SE38")

    try:
        await backend.fill_field("Programm", program_name)
    except ValueError:
        try:
            await backend.fill_field("Program", program_name)
        except ValueError:
            # Fallback: fill main form input, skipping toolbar/combobox inputs.
            if not await backend.fill_main_input(program_name, ["Programm", "Program"]):
                return "Could not find program name field"

    await backend.press_key("F6")
    await backend.wait_for_ready()
    return None


async def _edit_check_activate(backend: SapUiBackend, program_name: str, new_source: str) -> SE38EditResult:
    """Core edit logic: read backup, replace, check, activate, revert on failure."""
    # Navigate and open editor
    nav_error = await _navigate_and_open_editor(backend, program_name)
    if nav_error:
        return SE38EditResult.failure(error=nav_error, program_name=program_name, backup_source="", activated=False)

    # Read current source (backup)
    backup_source = await backend.read_editor_source() or ""
    if not backup_source:
        return SE38EditResult.failure(
            error="Could not read current source code from editor. Is the report accessible?",
            program_name=program_name,
            backup_source="",
            activated=False,
        )

    logger.info("SE38 edit: backup saved for %s (%d chars)", program_name, len(backup_source))

    # Replace editor content
    replaced = await backend.replace_editor_source(new_source)
    if not replaced:
        return SE38EditResult.failure(
            error="Failed to replace editor content",
            program_name=program_name,
            backup_source=backup_source,
            activated=False,
        )

    # Check and activate
    result = await backend.check_and_activate()

    if not result.success:
        logger.warning("SE38 edit: check/activate failed for %s, reverting", program_name)
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

        return SE38EditResult.failure(
            error=f"Check/activate failed: {'; '.join(result.messages)}",
            program_name=program_name,
            backup_source=backup_source,
            check_messages=result.messages,
            activated=False,
        )

    return SE38EditResult(
        success=True,
        program_name=program_name,
        backup_source=backup_source,
        check_messages=result.messages,
        activated=result.activated,
    )


def register_se38_edit_tools(mcp: FastMCP) -> None:
    """Register SE38 edit tools with the MCP server."""

    @mcp.tool(
        description=(
            "Edit an existing ABAP report in SE38.\n\n"
            "Replaces the entire source code, runs syntax check (Ctrl+F2), "
            "and activates (Ctrl+F3). Auto-reverts if check or activation fails.\n\n"
            "**Important:** Only for EXISTING reports. To create new reports, use abapGit.\n\n"
            "**Workflow:** Read current source with sap_read_se38_source first, "
            "modify it, then call this tool with the full new source."
        ),
        annotations={
            "destructiveHint": True,
            "readOnlyHint": False,
            "idempotentHint": False,
        },
    )
    async def sap_se38_edit(
        program_name: str,
        new_source: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE38EditResult:
        """Edit an existing ABAP report, check syntax, and activate.

        Args:
            program_name: Name of the ABAP report (e.g., 'ZTEST_MCP_EDIT').
            new_source: Complete new ABAP source code to replace the current code.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE38EditResult with success status, backup source, and check messages.
        """
        program_name = program_name.strip().upper()

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se38_edit")
        except ValueError as exc:
            return SE38EditResult.failure(
                error=f"Session error: {exc}",
                program_name=program_name,
                backup_source="",
                activated=False,
            )

        try:
            return await _edit_check_activate(backend, program_name, new_source)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("SE38 edit failed for %s", program_name)
            return SE38EditResult.failure(
                error=f"Unexpected error: {exc}",
                program_name=program_name,
                backup_source="",
                activated=False,
            )
