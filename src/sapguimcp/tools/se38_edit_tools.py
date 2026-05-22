"""
SE38 (ABAP Report Editor) edit tool.

Provides sap_se38_edit for modifying existing ABAP reports with
syntax check, activation, and auto-revert on failure.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastmcp import FastMCP

from sapguimcp.backend.manager import get_backend
from sapguimcp.models.se38_edit_models import SE38EditResult
from sapguimcp.tools.field_helpers import fill_field_with_keyboard

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

# DE/EN title attributes for the SE38 program name field.
# The field has title="ABAP-Programmname" (DE) / "ABAP Program Name" (EN),
# NOT the label text "Programm"/"Program" shown next to it.
_SE38_FIELD_TITLES = [
    "ABAP-Programmname",
    "ABAP Program Name",
    "ABAP program name",
    "Programm",
    "Program",
]


async def _fill_program_field_js(backend: WebGuiBackend | DesktopBackend, program_name: str) -> bool:
    """Fill the program name using the standard JS-based fill_field (works on fresh screens)."""
    for label in ("Programm", "Program"):
        try:
            await backend.fill_field(label, program_name)
            return True
        except ValueError:
            continue
    return await backend.fill_main_input(program_name, ["Programm", "Program"])


async def _fill_program_field_keyboard(backend: WebGuiBackend, program_name: str) -> bool:
    """Fill the program name using real keyboard events (works after state resets).

    Uses JavaScript to locate and focus the CBS field, then types with
    real keyboard events. This survives SAP's post-navigation state where
    Playwright locator clicks time out due to SAP's overlay mechanism.
    """
    # Try the shared helper first (matches by title attribute).
    if await fill_field_with_keyboard(backend, _SE38_FIELD_TITLES, program_name):
        return True

    # Direct JS: find the CBS program field by known attributes and focus it.
    focused = await backend.evaluate_javascript("""(() => {
        // Find CBS input with title containing 'rogramm' (works for DE/EN).
        const input = document.querySelector("input[title*='rogramm'][ct='CBS']")
            || document.querySelector("input[name='InputField'][ct='CBS']");
        if (!input || input.offsetParent === null) return false;
        input.focus();
        input.click();
        input.select();
        return true;
    })()""")
    if not focused:
        return False

    await backend.type_text(program_name)
    return True


async def _navigate_and_open_editor_desktop(backend: WebGuiBackend | DesktopBackend, program_name: str) -> str | None:
    """Desktop-specific: navigate to SE38, fill program name, enter change mode."""
    await backend.enter_transaction("SE38")
    await backend.wait_for_ready()

    filled = await backend.focus_and_type("RS38M-PROGRAMM", program_name.upper())
    if not filled:
        # Fallback: keyboard fill
        filled = await fill_field_with_keyboard(backend, _SE38_FIELD_TITLES, program_name.upper())
    if not filled:
        return "Could not fill program name field on desktop"

    await asyncio.sleep(0.3)
    # F6 (Change) works for SE38 on desktop in both DE and EN
    await backend.press_key("F6")
    await backend.wait(2000)

    # Verify we left the initial screen
    screen = await backend.get_screen_info()
    title = (screen.title or "").lower()
    if "einstieg" in title or "initial" in title:
        # Check status bar for error
        sbar = await backend.get_status_bar()
        return sbar.message or f"Could not open '{program_name}' in change mode"
    return None


async def _navigate_and_open_editor(backend: WebGuiBackend, program_name: str) -> str | None:
    """Navigate to SE38 on the given page, fill program name, enter change mode, return error or None."""
    await backend.enter_transaction("SE38")

    for attempt in range(3):
        if attempt > 0:
            logger.info("Retrying fill+F6 for %s (attempt %d)", program_name, attempt + 1)
            await asyncio.sleep(1.0)

        # First attempt: fast JS fill. Retries: keyboard fill (survives state resets).
        if attempt == 0:
            filled = await _fill_program_field_js(backend, program_name)
        else:
            filled = await _fill_program_field_keyboard(backend, program_name)

        if not filled:
            logger.warning("Program name field not found (attempt %d)", attempt + 1)
            continue

        # Brief wait for SAP to register the typed value before pressing F6.
        await asyncio.sleep(0.3)
        await backend.press_key("F6")
        await backend.wait_for_ready()

        # Verify we left the initial screen.
        snapshot = str(await backend.get_snapshot()).lower()
        if "einstieg" not in snapshot and "initial screen" not in snapshot:
            return None

    return "Could not find or fill program name field after retries"


async def _edit_check_activate(
    backend: WebGuiBackend | DesktopBackend, program_name: str, new_source: str
) -> SE38EditResult:
    """Core edit logic: read backup, replace, check, activate, revert on failure."""
    # Navigate and open editor — use desktop or WebGUI path
    if backend.backend_type == "desktop":
        nav_error = await _navigate_and_open_editor_desktop(backend, program_name)
    else:
        from sapguimcp.backend.webgui.backend import WebGuiBackend as _WG  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, _WG)
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
            "Edit an existing ABAP report in SE38. "
            "If sap-adt is available, prefer its patch_source or "
            "set_source_from_file tools — faster, no GUI needed.\n\n"
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
