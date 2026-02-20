"""
SE24 (Class Builder) edit tool.

Provides sap_se24_edit for modifying existing class methods with
syntax check, activation, and auto-revert on failure.

Unlike SE38/SE37 which edit entire program/FM source, SE24 edits
individual method source code within a class.
"""

import logging

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from sapwebguimcp.models.browser import get_browser_manager
from sapwebguimcp.models.se24_edit_models import SE24EditResult
from sapwebguimcp.tools.edit_helpers import check_and_activate, read_editor_source, replace_editor_source
from sapwebguimcp.tools.sap_tool_impl import _find_okcode_field, _load_js

logger = logging.getLogger(__name__)


async def _dismiss_language_dialog(page: Page) -> None:
    """Handle SAP's 'Different original and logon languages' popup if present."""
    snap = await page.locator("body").aria_snapshot()
    if "Different original and logon languages" not in snap and "Originalsprache und Anmeldesprache" not in snap:
        return
    logger.info("SE24 edit: detected language mismatch dialog, confirming maintenance in original language")
    maint_btn = page.get_by_role("button", name="Maint. in orig. lang.")
    if not await maint_btn.is_visible(timeout=2000):
        maint_btn = page.get_by_role("button", name="Pflege in Originalsprache")
    if await maint_btn.is_visible(timeout=2000):
        await maint_btn.click()
        await page.wait_for_timeout(1000)
        await page.wait_for_load_state("networkidle")


async def _navigate_to_method_editor(page: Page, class_name: str, method_name: str) -> str | None:
    """Navigate to SE24, open class in change mode, select method, open source editor.

    Returns error message or None on success.
    """
    # Navigate via OK-code field directly on the provided page
    okcode_field = await _find_okcode_field(page)
    if not okcode_field:
        return "Could not find OK-Code field on page"

    await page.bring_to_front()
    await page.wait_for_timeout(500)
    await okcode_field.click()
    await page.wait_for_timeout(200)
    await page.evaluate(_load_js("set_okcode_field.js"), {"transactionInput": "/nSE24"})
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.wait_for_timeout(1000)

    # Fill class name field (DE: "Objekttyp", EN: "Object Type") using SE38-style approach
    field = page.get_by_role("textbox", name="Objekttyp")
    if not await field.is_visible(timeout=2000):
        field = page.get_by_role("textbox", name="Object Type")
    if not await field.is_visible(timeout=2000):
        heading_snap = (await page.locator("body").aria_snapshot())[:300]
        return f"Could not find class/interface field in SE24. Page state: {heading_snap}"
    await field.click(click_count=3)
    await page.keyboard.press("Delete")
    await page.keyboard.type(class_name)

    # F7 to display first (reliable in both DE/EN), then toggle to change mode
    await page.keyboard.press("F7")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    page_title_after_display = await page.title()
    if "Class Builder" not in page_title_after_display and "Klasse" not in page_title_after_display:
        snap = (await page.locator("body").aria_snapshot())[:400]
        return f"F7 failed to display class. Page: {snap}"

    await _dismiss_language_dialog(page)

    # Switch from display to change mode via "Display <-> Change" / "Anzeigen <-> Ändern"
    toggle_btn = page.get_by_role("button", name="Anzeigen <-> Ändern")
    if not await toggle_btn.is_visible(timeout=2000):
        toggle_btn = page.get_by_role("button", name="Display <-> Change")
    if not await toggle_btn.is_visible(timeout=2000):
        snap = (await page.locator("body").aria_snapshot())[:300]
        return f"Could not find 'Display <-> Change' toggle button. Page: {snap}"
    await toggle_btn.click()
    await page.wait_for_timeout(1000)
    await page.wait_for_load_state("networkidle")

    await _dismiss_language_dialog(page)

    # Ensure we're on the Methods tab (DE: "Methoden", EN: "Methods")
    methods_tab = page.get_by_role("tab", name="Methoden")
    if not await methods_tab.is_visible(timeout=2000):
        methods_tab = page.get_by_role("tab", name="Methods")
    if await methods_tab.is_visible(timeout=2000):
        await methods_tab.click()
        await page.wait_for_timeout(500)
        await page.wait_for_load_state("networkidle")

    # Select the method in the grid by clicking on its gridcell
    method_cell = page.get_by_role("gridcell", name=method_name).first
    if not await method_cell.is_visible(timeout=3000):
        # Try case-insensitive: SAP might show it differently
        method_cell = page.get_by_role("gridcell", name=method_name.upper()).first
    if not await method_cell.is_visible(timeout=2000):
        # Debug: capture snapshot to understand current screen state
        debug_snapshot = await page.locator("body").aria_snapshot()
        logger.warning(
            "SE24 edit: method %s not found in grid for %s. Screen heading: %s",
            method_name,
            class_name,
            debug_snapshot[:200],
        )
        return f"Method '{method_name}' not found in class '{class_name}' methods grid"
    await method_cell.click()
    await page.wait_for_timeout(300)

    # Click "Quelltext" / "Sourcecode" / "Source Code" button to open method source
    source_btn = page.get_by_role("button", name="Quelltext")
    if not await source_btn.is_visible(timeout=2000):
        source_btn = page.get_by_role("button", name="Sourcecode")
    if not await source_btn.is_visible(timeout=2000):
        source_btn = page.get_by_role("button", name="Source Code")
    if not await source_btn.is_visible(timeout=2000):
        source_btn = page.get_by_role("button", name="Source code")
    if not await source_btn.is_visible(timeout=2000):
        return "Could not find 'Quelltext'/'Sourcecode' button"
    await source_btn.click()
    await page.wait_for_timeout(1000)
    await page.wait_for_load_state("networkidle")

    return None


async def _edit_check_activate_method(page: Page, class_name: str, method_name: str, new_source: str) -> SE24EditResult:
    """Core edit logic: navigate, read backup, replace, check, activate, revert on failure."""
    nav_error = await _navigate_to_method_editor(page, class_name, method_name)
    if nav_error:
        return SE24EditResult.failure(
            error=nav_error, class_name=class_name, method_name=method_name, backup_source="", activated=False
        )

    # Read current source (backup)
    backup_source = await read_editor_source(page) or ""
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
    replaced = await replace_editor_source(page, new_source)
    if not replaced:
        return SE24EditResult.failure(
            error="Failed to replace editor content",
            class_name=class_name,
            method_name=method_name,
            backup_source=backup_source,
            activated=False,
        )

    # Check and activate
    success, messages, activated = await check_and_activate(page)

    if not success:
        logger.warning("SE24 edit: check/activate failed for %s->%s, reverting", class_name, method_name)
        reverted = await replace_editor_source(page, backup_source)
        if reverted:
            revert_ok, revert_msgs, _ = await check_and_activate(page)
            if revert_ok:
                messages.append("Auto-reverted to original source and re-activated successfully")
            else:
                messages.append(f"Auto-reverted source but re-activation failed: {'; '.join(revert_msgs)}")
        else:
            messages.append("WARNING: Auto-revert failed! Manual intervention needed.")

        return SE24EditResult.failure(
            error=f"Check/activate failed: {'; '.join(messages)}",
            class_name=class_name,
            method_name=method_name,
            backup_source=backup_source,
            check_messages=messages,
            activated=False,
        )

    return SE24EditResult(
        success=True,
        class_name=class_name,
        method_name=method_name,
        backup_source=backup_source,
        check_messages=messages,
        activated=activated,
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
            browser_manager = await get_browser_manager()
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_se24_edit")
        except ValueError as exc:
            return SE24EditResult.failure(
                error=f"Session error: {exc}",
                class_name=class_name,
                method_name=method_name,
                backup_source="",
                activated=False,
            )

        try:
            return await _edit_check_activate_method(page, class_name, method_name, new_source)
        except (PlaywrightError, OSError) as exc:
            logger.exception("SE24 edit failed for %s->%s", class_name, method_name)
            return SE24EditResult.failure(
                error=f"Unexpected error: {exc}",
                class_name=class_name,
                method_name=method_name,
                backup_source="",
                activated=False,
            )
