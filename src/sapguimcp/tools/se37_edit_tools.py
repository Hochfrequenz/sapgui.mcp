"""
SE37 (Function Builder) edit tool.

Provides sap_se37_edit for modifying existing function modules with
syntax check, activation, and auto-revert on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp import lang
from sapguimcp.backend.manager import get_backend
from sapguimcp.models.se37_edit_models import SE37EditResult
from sapguimcp.tools.desktop_wait_predicates import editor_loaded
from sapguimcp.tools.edit_helpers import (
    REVERT_FAILED,
    confirm_language_dialog,
    describe_failed_replace,
    leave_editor_after,
    switch_to_change_mode,
)
from sapguimcp.tools.se37_tools import _fill_fm_name_desktop, _se37_display_reached

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.lang.schema import LanguagePack


logger = logging.getLogger(__name__)

# Upper bound for waiting on a state change on the desktop (#928): a step whose state does not change as expected
# must not cost more than the former fixed waits did.
_SE37_DISPLAY_WAIT_MS = 3000
_SE37_TOGGLE_WAIT_MS = 1000
_SE37_SOURCE_WAIT_MS = 10000


async def _open_fm_in_change_mode_desktop(backend: DesktopBackend, function_module: str, t: LanguagePack) -> str | None:
    """Navigate to SE37, display the function module via F7 and switch to change mode.

    Returns an error message or None on success.
    """
    if not function_module:
        return "No function module name given"  # lang-ok: our own message
    await backend.enter_transaction("SE37")
    await backend.wait_for_ready()

    if not await _fill_fm_name_desktop(backend, function_module, t):
        return "Could not fill function module name field"  # lang-ok: our own message

    before_title = (await backend.get_screen_info()).title or ""
    before_status = (await backend.get_status_bar()).message.strip()
    await backend.press_key("F7")  # Display
    await backend.wait_for_ready()
    await backend.wait_for_condition(
        _se37_display_reached(function_module, before_title, before_status), timeout_ms=_SE37_DISPLAY_WAIT_MS
    )

    popup_error = await confirm_language_dialog(backend, before_title, before_status, timeout_ms=_SE37_DISPLAY_WAIT_MS)
    if popup_error is not None:
        return f"Unexpected popup while displaying function module '{function_module}': {popup_error}"  # lang-ok: ours

    # A missing function module keeps the initial screen and reports a status bar message
    if function_module.upper() not in ((await backend.get_screen_info()).title or "").upper():
        sbar = await backend.get_status_bar()
        return sbar.message or f"Function module '{function_module}' not found"  # lang-ok: our own message

    popup_error = await switch_to_change_mode(
        backend, toggle_wait_ms=_SE37_TOGGLE_WAIT_MS, dialog_wait_ms=_SE37_DISPLAY_WAIT_MS
    )
    if popup_error is not None:
        return f"Unexpected popup while switching function module '{function_module}' to change mode: {popup_error}"  # lang-ok: ours  # noqa: E501
    return None


async def _open_source_tab_desktop(backend: DesktopBackend, function_module: str, t: LanguagePack) -> str | None:
    """Click the source code tab and wait for the editor. Returns an error message or None on success."""
    for tab_name in t.se37.source_tab:
        try:
            await backend.click_tab(tab_name)
            await backend.wait_for_ready()
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        if not await backend.wait_for_condition(editor_loaded, timeout_ms=_SE37_SOURCE_WAIT_MS):
            # Going on would read (and replace) a missing editor.
            logger.warning("SE37 edit: no editor appeared within %d ms after '%s'", _SE37_SOURCE_WAIT_MS, tab_name)
            seconds = _SE37_SOURCE_WAIT_MS // 1000
            return f"The source editor of function module '{function_module}' did not open within {seconds} s"  # lang-ok: ours  # noqa: E501
        return None
    return "Could not find the source code tab"  # lang-ok: our own message


async def _edit_check_activate_fm(
    backend: DesktopBackend, function_module: str, new_source: str, t: LanguagePack
) -> SE37EditResult:
    """Edit the function module, then leave SE37 so its function group is no longer locked (#1166)."""
    return await leave_editor_after(backend, "SE37", _edit_fm_in_editor(backend, function_module, new_source, t))


async def _edit_fm_in_editor(
    backend: DesktopBackend, function_module: str, new_source: str, t: LanguagePack
) -> SE37EditResult:
    """Core edit logic: navigate, read backup, replace, check, activate, revert on failure."""
    nav_error = await _open_fm_in_change_mode_desktop(backend, function_module, t)
    if nav_error is None:
        nav_error = await _open_source_tab_desktop(backend, function_module, t)
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

    # Replace editor content. The backend verifies the buffer afterwards, so a
    # False here means the editor content does not match new_source (#859).
    replaced = await backend.replace_editor_source(new_source)
    if not replaced:
        return SE37EditResult.failure(
            error=await describe_failed_replace(backend, backup_source),
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
            if revert_result.success and revert_result.activated:
                result.messages.append("Auto-reverted to original source and re-activated successfully")
            elif revert_result.success:
                # No activation confirmation from the backend: do not claim the restore worked
                result.messages.append(
                    "Auto-reverted source but re-activation could not be confirmed: "
                    f"{'; '.join(revert_result.messages)}"
                )
            else:
                result.messages.append(
                    f"Auto-reverted source but re-activation failed: {'; '.join(revert_result.messages)}"
                )
        else:
            result.messages.append(REVERT_FAILED)

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
            "Edit an existing ABAP function module in SE37. "
            "If sap-adt is available, prefer its patch_source or "
            "set_source_from_file tools — faster, no GUI needed.\n\n"
            "Replaces the entire source code (including the FUNCTION and ENDFUNCTION lines), "
            "runs syntax check (Ctrl+F2), and activates (Ctrl+F3). "
            "Auto-reverts if check or activation fails. "
            "Afterwards, also after a failure, it leaves SE37 without saving, so the function group is not left "
            "locked.\n\n"
            "**Important:** Only for EXISTING function modules. To create new ones, use abapGit.\n\n"
            "**Workflow:** Read the current source first (sap-adt get_source, or the backup_source "
            "that this tool returns), modify it, then call this tool with the full new source."
        ),
        annotations=ToolAnnotations(
            destructive_hint=True,
            read_only_hint=False,
            idempotent_hint=False,
        ),
    )
    async def sap_se37_edit(
        function_module: str,
        new_source: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE37EditResult:
        """Edit an existing function module, check syntax, and activate.

        Args:
            function_module: Name of the function module (e.g., 'Z_MCP_TEST_FM').
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

        # Resolved outside the broad except below: an unsupported language must reach the caller as such
        t = lang.current("sap_se37_edit")

        try:
            return await _edit_check_activate_fm(backend, function_module, new_source, t)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("SE37 edit failed for %s", function_module)
            return SE37EditResult.failure(
                error=f"Unexpected error: {exc}",
                function_module=function_module,
                backup_source="",
                activated=False,
            )
