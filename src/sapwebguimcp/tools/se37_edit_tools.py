"""
SE37 (Function Module) edit tool.

Provides sap_se37_edit for modifying existing function modules with
syntax check, activation, and auto-revert on failure.
"""

import logging

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from sapwebguimcp.models.browser import get_browser_manager
from sapwebguimcp.models.se37_edit_models import SE37EditResult
from sapwebguimcp.tools.edit_helpers import check_and_activate, read_editor_source, replace_editor_source
from sapwebguimcp.tools.sap_tool_impl import _find_okcode_field, _load_js

logger = logging.getLogger(__name__)


async def _navigate_to_fm_editor(page: Page, function_module: str) -> str | None:
    """Navigate to SE37, display FM, open source tab in change mode. Returns error or None."""
    # Navigate via OK-code field directly on the provided page
    okcode_field = await _find_okcode_field(page)
    if not okcode_field:
        return "Could not find OK-Code field on page"

    await okcode_field.click()
    await page.wait_for_timeout(200)
    await page.evaluate(_load_js("set_okcode_field.js"), {"transactionInput": "/nSE37"})
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("networkidle", timeout=15000)

    await page.wait_for_timeout(1000)

    # Fill FM name field (DE: "Funktionsbaustein", EN: "Function Module")
    field = page.get_by_role("textbox", name="Funktionsbaustein")
    if not await field.is_visible(timeout=2000):
        field = page.get_by_role("textbox", name="Function Module")
    if not await field.is_visible(timeout=2000):
        # Fallback: try Function module (different casing)
        field = page.get_by_role("textbox", name="Function module")
    await field.click(click_count=3)
    await page.keyboard.press("Delete")
    await page.keyboard.type(function_module)

    # F6 to enter change mode directly (same as SE38)
    await page.keyboard.press("F6")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    # Click "Quelltext" / "Source Code" / "Source code" tab to show source editor
    source_tab = page.get_by_role("tab", name="Quelltext")
    if not await source_tab.is_visible(timeout=2000):
        source_tab = page.get_by_role("tab", name="Source Code")
    if not await source_tab.is_visible(timeout=2000):
        source_tab = page.get_by_role("tab", name="Source code")
    await source_tab.click()
    await page.wait_for_timeout(1000)
    await page.wait_for_load_state("networkidle")

    return None


async def _edit_check_activate_fm(page: Page, function_module: str, new_source: str) -> SE37EditResult:
    """Core edit logic: navigate, read backup, replace, check, activate, revert on failure."""
    nav_error = await _navigate_to_fm_editor(page, function_module)
    if nav_error:
        return SE37EditResult.failure(
            error=nav_error, function_module=function_module, backup_source="", activated=False
        )

    # Read current source (backup)
    backup_source = await read_editor_source(page) or ""
    if not backup_source:
        return SE37EditResult.failure(
            error="Could not read current source code from editor. Is the function module accessible?",
            function_module=function_module,
            backup_source="",
            activated=False,
        )

    logger.info("SE37 edit: backup saved for %s (%d chars)", function_module, len(backup_source))

    # Replace editor content
    replaced = await replace_editor_source(page, new_source)
    if not replaced:
        return SE37EditResult.failure(
            error="Failed to replace editor content",
            function_module=function_module,
            backup_source=backup_source,
            activated=False,
        )

    # Check and activate
    success, messages, activated = await check_and_activate(page)

    if not success:
        logger.warning("SE37 edit: check/activate failed for %s, reverting", function_module)
        reverted = await replace_editor_source(page, backup_source)
        if reverted:
            revert_ok, revert_msgs, _ = await check_and_activate(page)
            if revert_ok:
                messages.append("Auto-reverted to original source and re-activated successfully")
            else:
                messages.append(f"Auto-reverted source but re-activation failed: {'; '.join(revert_msgs)}")
        else:
            messages.append("WARNING: Auto-revert failed! Manual intervention needed.")

        return SE37EditResult.failure(
            error=f"Check/activate failed: {'; '.join(messages)}",
            function_module=function_module,
            backup_source=backup_source,
            check_messages=messages,
            activated=False,
        )

    return SE37EditResult(
        success=True,
        function_module=function_module,
        backup_source=backup_source,
        check_messages=messages,
        activated=activated,
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
            browser_manager = await get_browser_manager()
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_se37_edit")
        except ValueError as exc:
            return SE37EditResult.failure(
                error=f"Session error: {exc}",
                function_module=function_module,
                backup_source="",
                activated=False,
            )

        try:
            return await _edit_check_activate_fm(page, function_module, new_source)
        except (PlaywrightError, OSError) as exc:
            logger.exception("SE37 edit failed for %s", function_module)
            return SE37EditResult.failure(
                error=f"Unexpected error: {exc}",
                function_module=function_module,
                backup_source="",
                activated=False,
            )
