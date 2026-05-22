"""
SE93 (Transaction Maintenance) lookup tool.

This module provides a tool to look up transaction metadata from SE93,
returning strongly-typed Pydantic models with transaction details.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.se93_parser import parse_se93_snapshot
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.models import (
    SE93Entry,
    SE93Error,
    SE93FileSummary,
    SE93Result,
)
from sapguimcp.models.se93_models import SE93TransactionType
from sapguimcp.tools.field_helpers import fill_and_display

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_se93_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 10


# =============================================================================
# SE93 Navigation Helpers
# =============================================================================


# DE/EN label variants for the transaction code input field.
_TCODE_FIELD_LABELS = [
    "Transaktionscode",
    "Transaction code",
    "Transaction Code",
]


async def _read_checkbox(backend: WebGuiBackend | DesktopBackend, sap_name: str) -> bool:
    """Read a checkbox's selected state by SAP element name. Returns False on error."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return False
    session = backend.require_session()
    com = backend.com

    def _read() -> bool:
        from sapsucker.components.base import GuiVContainer  # pylint: disable=import-outside-toplevel

        usr = session.find_by_id("wnd[0]/usr")
        if not isinstance(usr, GuiVContainer):
            return False
        try:
            chk = usr.find_by_name(sap_name, "GuiCheckBox")
            return bool(getattr(chk, "selected", False)) if chk is not None else False
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    return await com.run(_read)


async def _lookup_tcode_desktop(  # pylint: disable=too-many-locals
    backend: WebGuiBackend | DesktopBackend, tcode: str
) -> SE93Entry | SE93Error:
    """Desktop-specific SE93 lookup using field reading instead of ARIA parsing."""
    now = datetime.now(UTC)

    # Fill transaction code field
    filled = False
    for label in _TCODE_FIELD_LABELS:
        try:
            await backend.fill_field(label, tcode.upper())
            filled = True
            break
        except ValueError:
            continue
    if not filled:
        filled = await backend.focus_and_type("TSTC-TCODE", tcode.upper())
    if not filled:
        return SE93Error(tcode=tcode, error="Could not fill transaction code field", retrieved_at=now)

    # Press F7 (Display)
    await backend.press_key("F7")
    await backend.wait(1500)

    # Check status bar for errors (e.g., "Transaction code does not exist")
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return SE93Error(tcode=tcode, error=sbar.message or "Transaction not found", retrieved_at=now)

    # Read input fields (types 31-34: text, context, password, combo)
    field_list = await backend.discover_fields()
    field_map: dict[str, str] = {}
    for f in field_list:
        if f.name:
            field_map[f.name] = f.value or ""

    description = field_map.get("TSTCT-TTEXT", "")
    program = field_map.get("TSTC-PGMNA", "")
    package = field_map.get("RSSTCD-DEVCLASS", "")
    screen_number = field_map.get("TSTC-DYPNO", "")
    auth_object = field_map.get("TSTCA-OBJCT", "") or None

    # On R/3, nonexistent tcodes don't produce a status bar error — they show
    # an empty form instead. Detect this by checking if both program and
    # description are empty (a real tcode always has at least a program).
    if not program and not description:
        return SE93Error(tcode=tcode, error="Transaction code does not exist", retrieved_at=now)

    # Determine transaction type: dialog if screen number present, else report
    tx_type: SE93TransactionType = "dialog" if screen_number else "report"

    # Read GUI capability checkboxes (type 42, not returned by discover_fields)
    gui_html = await _read_checkbox(backend, "TSTCC-S_WEBGUI")
    gui_java = await _read_checkbox(backend, "TSTCC-S_PLATIN")
    gui_windows = await _read_checkbox(backend, "TSTCC-S_WIN32")

    return SE93Entry(
        tcode=tcode.upper(),
        description=description,
        transaction_type=tx_type,
        package=package,
        program=program,
        screen_number=screen_number or None,
        authorization_object=auth_object,
        gui_html=gui_html,
        gui_java=gui_java,
        gui_windows=gui_windows,
        retrieved_at=now,
    )


async def _lookup_tcode_on_initial_screen(backend: WebGuiBackend | DesktopBackend, tcode: str) -> SE93Entry | SE93Error:
    """Look up a transaction code assuming we're already on the SE93 initial screen.

    The caller handles navigation (``enter_transaction``) and state reset
    (``/n`` between lookups) to prevent state bleeding in batch mode.
    """
    # Ensure the SE93 screen is fully loaded before interacting.
    await backend.wait_for_ready()

    # Fill field with real keyboard events, press F7, and verify navigation.
    error_msg = await fill_and_display(backend, _TCODE_FIELD_LABELS, tcode, tcode_label="transaction")
    if error_msg:
        return SE93Error(
            tcode=tcode,
            error=error_msg,
            retrieved_at=datetime.now(UTC),
        )

    # Get and parse snapshot
    snapshot = AriaSnapshot(await backend.get_snapshot())
    logger.debug("Got snapshot", extra={"object": tcode, "length": len(snapshot)})

    return parse_se93_snapshot(snapshot, tcode)


async def _lookup_batch_webgui(backend: WebGuiBackend | DesktopBackend, tcode_list: list[str]) -> SE93Result:
    """Run SE93 lookups for a batch of tcodes on the WebGUI backend."""
    entries: list[SE93Entry] = []
    errors: list[SE93Error] = []

    for tcode in tcode_list:
        await backend.enter_transaction("/n")
        await backend.wait_for_ready()
        tx_result = await backend.enter_transaction("SE93")
        if not tx_result.success:
            errors.append(
                SE93Error(
                    tcode=tcode, error=f"Failed to navigate to SE93: {tx_result.error}", retrieved_at=datetime.now(UTC)
                )
            )
            continue
        await backend.wait_for_ready()
        try:
            result = await _lookup_tcode_on_initial_screen(backend, tcode)
            if isinstance(result, SE93Entry):
                entries.append(result)
            else:
                errors.append(result)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Looking up in SE93", extra={"object": tcode})
            errors.append(
                SE93Error(tcode=tcode, error=f"Error looking up '{tcode}': {e}", retrieved_at=datetime.now(UTC))
            )

    if entries:
        return SE93Result(entries=entries, errors=errors)
    return SE93Result.failure(error=f"All {len(errors)} lookups failed", entries=[], errors=errors)


async def _lookup_batch_desktop(backend: WebGuiBackend | DesktopBackend, tcode_list: list[str]) -> SE93Result:
    """Run SE93 lookups for a batch of tcodes on the desktop backend."""
    entries: list[SE93Entry] = []
    errors: list[SE93Error] = []

    for tcode in tcode_list:
        await backend.enter_transaction("/n")
        await backend.wait_for_ready()
        tx_result = await backend.enter_transaction("SE93")
        if not tx_result.success:
            errors.append(
                SE93Error(
                    tcode=tcode, error=f"Failed to navigate to SE93: {tx_result.error}", retrieved_at=datetime.now(UTC)
                )
            )
            continue
        await backend.wait_for_ready()
        try:
            result = await _lookup_tcode_desktop(backend, tcode)
            if isinstance(result, SE93Entry):
                entries.append(result)
            else:
                errors.append(result)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("SE93 desktop lookup failed", extra={"tcode": tcode})
            errors.append(SE93Error(tcode=tcode, error=f"Error: {e}", retrieved_at=datetime.now(UTC)))

    if entries:
        return SE93Result(entries=entries, errors=errors)
    return SE93Result.failure(error=f"All {len(errors)} lookups failed", entries=[], errors=errors)


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se93_tools(mcp: FastMCP) -> None:
    """Register SE93 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up transaction metadata from SE93 (Transaction Maintenance). "
            "USE THIS instead of sap_transaction('SE93') - faster and returns structured data. "
            "Returns transaction description, program, screen/selection info, and GUI capabilities. "
            "Supports single tcode or list of tcodes. "
            "Currently supports 'dialog' and 'report' transaction types."
        ),
    )
    async def sap_se93_lookup(
        tcodes: str | list[str],
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE93Result | SE93FileSummary:
        """
        Look up transaction metadata from SE93.

        Args:
            tcodes: Single transaction code or list of codes (e.g., 'VA01' or ['VA01', 'MM01'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >10 transactions to avoid context overflow.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE93Result with entries and errors (inline), or
            SE93FileSummary with file path and statistics (when output_file provided)
        """
        tcode_list = [tcodes] if isinstance(tcodes, str) else list(tcodes)

        if not tcode_list:
            return SE93Result.failure("No transaction codes provided")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se93_lookup")
        except ValueError as e:
            return SE93Result.failure(f"Session error: {e}")

        # Desktop backend: use field reading instead of ARIA parsing
        if backend.backend_type == "desktop":
            final_result = await _lookup_batch_desktop(backend, tcode_list)
        else:
            final_result = await _lookup_batch_webgui(backend, tcode_list)

        # Write to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(final_result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SE93FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(tcode_list),
                successful=len(final_result.entries),
                failed=len(final_result.errors),
                sample_entries=[e.tcode for e in final_result.entries[:5]],
                sample_errors=[e.tcode for e in final_result.errors[:5]],
            )

        if len(tcode_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning transactions inline - consider using output_file parameter",
                extra={"count": len(tcode_list)},
            )

        return final_result
