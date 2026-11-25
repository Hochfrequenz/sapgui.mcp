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
from mcp.types import ToolAnnotations

from sapguimcp import lang
from sapguimcp.backend.manager import get_backend
from sapguimcp.models.se24_edit_models import SE24EditResult
from sapguimcp.tools.desktop_wait_predicates import (
    editor_loaded,
    editor_loaded_after,
    screen_changed,
    tab_table_control_loaded,
)
from sapguimcp.tools.edit_helpers import confirm_language_dialog, describe_failed_replace, switch_to_change_mode
from sapguimcp.tools.field_helpers import fill_field_with_keyboard

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.lang.schema import LanguagePack


logger = logging.getLogger(__name__)

# Upper bound for waiting on a state change on the desktop (#928): the former fixed waits took 1-2 s, so a step whose
# state does not change as expected (e.g. a toggle that was a no-op) must not cost more than they did.
_SE24_DISPLAY_WAIT_MS = 3000
_SE24_TOGGLE_WAIT_MS = 1000
_SE24_SOURCE_WAIT_MS = 10000


async def _open_class_in_change_mode_desktop(backend: DesktopBackend, class_name: str, t: LanguagePack) -> str | None:
    """Desktop-specific: navigate to SE24, display class, toggle to change mode."""
    await backend.enter_transaction("SE24")
    await backend.wait_for_ready()

    filled = await backend.focus_and_type("SEOCLASS-CLSNAME", class_name.upper())
    if not filled:
        filled = await fill_field_with_keyboard(backend, list(t.se24.object_type), class_name.upper())
    if not filled:
        return "Could not fill class name field on desktop"

    await asyncio.sleep(0.3)
    before_title = (await backend.get_screen_info()).title or ""
    before_status = (await backend.get_status_bar()).message.strip()
    await backend.press_key("F7")  # Display
    await backend.wait_for_ready()
    await backend.wait_for_condition(screen_changed(before_title, before_status), timeout_ms=_SE24_DISPLAY_WAIT_MS)

    popup_error = await confirm_language_dialog(backend, before_title, before_status, timeout_ms=_SE24_DISPLAY_WAIT_MS)
    if popup_error is not None:
        return f"Unexpected popup while displaying class '{class_name}': {popup_error}"  # lang-ok: our own message

    # Verify we left the initial screen
    screen = await backend.get_screen_info()
    if t.se24.initial_screen.contains(screen.title or ""):
        sbar = await backend.get_status_bar()
        return sbar.message or f"Could not display class '{class_name}'"  # lang-ok: our own message

    popup_error = await switch_to_change_mode(
        backend, toggle_wait_ms=_SE24_TOGGLE_WAIT_MS, dialog_wait_ms=_SE24_DISPLAY_WAIT_MS
    )
    if popup_error is not None:
        return f"Unexpected popup while switching class '{class_name}' to change mode: {popup_error}"  # lang-ok: our own message  # noqa: E501
    return None


async def _select_method_and_open_source_desktop(  # pylint: disable=too-many-return-statements
    backend: DesktopBackend, class_name: str, method_name: str, t: LanguagePack
) -> str | None:
    """Desktop-specific: find method in table control and open its source editor."""
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    # Ensure we're on the Methods tab. SAP instantiates a tab page lazily, so wait until the tab's own table
    # control is in the tree (it is already there when the tab was the active one).
    for tab_label in t.se24.methods_tab:
        try:
            await backend.click_tab(tab_label)
            await backend.wait_for_ready()
            await backend.wait_for_condition(tab_table_control_loaded(tab_label), timeout_ms=_SE24_TOGGLE_WAIT_MS)
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
                if t.se24.method_column.equals(title):
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
            return f"Method '{method_name}' not found in class '{class_name}' methods table"  # lang-ok: our own message
        return "No table control found on SE24 screen"

    select_error = await com.run(_select_method_row)
    if select_error:
        return select_error

    # Selecting the row only moves the focus on the client: no round trip to wait for.
    await backend.wait_for_ready()

    # An editor that is already open (e.g. the class itself is shown in the source-based view) does not tell that
    # the method's source has loaded: then the window title has to change as well.
    def _read_title_if_editor_is_open() -> str | None:
        if not editor_loaded(session):
            return None
        return str(cast(Any, session.find_by_id("wnd[0]")).text).strip()

    title_with_editor = await com.run(_read_title_if_editor_is_open)

    # Click the source code button to open the method source editor
    for btn_name in t.se24.source_button:
        try:
            await backend.click_button(btn_name)
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        await backend.wait_for_ready()
        if not await backend.wait_for_condition(
            editor_loaded_after(title_with_editor), timeout_ms=_SE24_SOURCE_WAIT_MS
        ):
            # Going on would read (and replace) a missing editor, or the one that predates the click.
            logger.warning("SE24 edit: no editor appeared within %d ms after '%s'", _SE24_SOURCE_WAIT_MS, btn_name)
            seconds = _SE24_SOURCE_WAIT_MS // 1000
            return f"The source editor of method '{method_name}' did not open within {seconds} s"  # lang-ok: ours
        return None

    return "Could not find the source code button"  # lang-ok: our own message


async def _navigate_to_method_editor_desktop(
    backend: DesktopBackend, class_name: str, method_name: str, t: LanguagePack
) -> str | None:
    """Desktop: navigate to SE24, open class in change mode, select method, open source."""
    error = await _open_class_in_change_mode_desktop(backend, class_name, t)
    if error:
        return error
    return await _select_method_and_open_source_desktop(backend, class_name, method_name, t)


async def _edit_check_activate_method(
    backend: DesktopBackend, class_name: str, method_name: str, new_source: str, t: LanguagePack
) -> SE24EditResult:
    """Core edit logic: navigate, read backup, replace, check, activate, revert on failure."""
    nav_error = await _navigate_to_method_editor_desktop(backend, class_name, method_name, t)
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
            error=await describe_failed_replace(backend, backup_source),
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
        annotations=ToolAnnotations(
            destructive_hint=True,
            read_only_hint=False,
            idempotent_hint=False,
        ),
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

        # Resolved outside the broad except below: an unsupported language must reach the caller as such
        t = lang.current("sap_se24_edit")

        try:
            return await _edit_check_activate_method(backend, class_name, method_name, new_source, t)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("SE24 edit failed for %s->%s", class_name, method_name)
            return SE24EditResult.failure(
                error=f"Unexpected error: {exc}",
                class_name=class_name,
                method_name=method_name,
                backup_source="",
                activated=False,
            )
