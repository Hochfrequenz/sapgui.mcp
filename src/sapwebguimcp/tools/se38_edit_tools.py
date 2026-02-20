"""
SE38 (ABAP Report Editor) edit tool.

Provides sap_se38_edit for modifying existing ABAP reports with
syntax check, activation, and auto-revert on failure.
"""

import logging

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from sapwebguimcp.models.browser import get_browser_manager
from sapwebguimcp.models.se38_edit_models import SE38EditResult
from sapwebguimcp.tools.edit_helpers import check_and_activate, read_editor_source, replace_editor_source
from sapwebguimcp.tools.sap_tool_impl import _find_okcode_field, _load_js

logger = logging.getLogger(__name__)


async def _navigate_and_open_editor(page: Page, program_name: str) -> str | None:
    """Navigate to SE38 on the given page, fill program name, enter change mode, return error or None."""
    # Navigate via OK-code field directly on the provided page (not via sap_transaction_impl
    # which always uses the primary session page).
    okcode_field = await _find_okcode_field(page)
    if not okcode_field:
        return "Could not find OK-Code field on page"

    await okcode_field.click()
    await page.wait_for_timeout(200)
    await page.evaluate(_load_js("set_okcode_field.js"), {"transactionInput": "/nSE38"})
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("networkidle", timeout=15000)

    await page.wait_for_timeout(1000)

    field = page.get_by_role("textbox", name="Programm")
    if not await field.is_visible(timeout=2000):
        field = page.get_by_role("textbox", name="Program")
    await field.click(click_count=3)
    await page.keyboard.press("Delete")
    await page.keyboard.type(program_name)

    await page.keyboard.press("F6")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")
    return None


async def _edit_check_activate(page: Page, program_name: str, new_source: str) -> SE38EditResult:
    """Core edit logic: read backup, replace, check, activate, revert on failure."""
    # Navigate and open editor
    nav_error = await _navigate_and_open_editor(page, program_name)
    if nav_error:
        return SE38EditResult.failure(error=nav_error, program_name=program_name, backup_source="", activated=False)

    # Read current source (backup)
    backup_source = await read_editor_source(page) or ""
    if not backup_source:
        return SE38EditResult.failure(
            error="Could not read current source code from editor. Is the report accessible?",
            program_name=program_name,
            backup_source="",
            activated=False,
        )

    logger.info("SE38 edit: backup saved for %s (%d chars)", program_name, len(backup_source))

    # Replace editor content
    replaced = await replace_editor_source(page, new_source)
    if not replaced:
        return SE38EditResult.failure(
            error="Failed to replace editor content",
            program_name=program_name,
            backup_source=backup_source,
            activated=False,
        )

    # Check and activate
    success, messages, activated = await check_and_activate(page)

    if not success:
        logger.warning("SE38 edit: check/activate failed for %s, reverting", program_name)
        reverted = await replace_editor_source(page, backup_source)
        if reverted:
            revert_ok, revert_msgs, _ = await check_and_activate(page)
            if revert_ok:
                messages.append("Auto-reverted to original source and re-activated successfully")
            else:
                messages.append(f"Auto-reverted source but re-activation failed: {'; '.join(revert_msgs)}")
        else:
            messages.append("WARNING: Auto-revert failed! Manual intervention needed.")

        return SE38EditResult.failure(
            error=f"Check/activate failed: {'; '.join(messages)}",
            program_name=program_name,
            backup_source=backup_source,
            check_messages=messages,
            activated=False,
        )

    return SE38EditResult(
        success=True,
        program_name=program_name,
        backup_source=backup_source,
        check_messages=messages,
        activated=activated,
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
            browser_manager = await get_browser_manager()
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_se38_edit")
        except ValueError as exc:
            return SE38EditResult.failure(
                error=f"Session error: {exc}",
                program_name=program_name,
                backup_source="",
                activated=False,
            )

        try:
            return await _edit_check_activate(page, program_name, new_source)
        except (PlaywrightError, OSError) as exc:
            logger.exception("SE38 edit failed for %s", program_name)
            return SE38EditResult.failure(
                error=f"Unexpected error: {exc}",
                program_name=program_name,
                backup_source="",
                activated=False,
            )
