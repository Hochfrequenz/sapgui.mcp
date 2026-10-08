"""
SLG1 (Application Log) lookup tool.

This module provides a tool to search and read SAP application logs via SLG1,
returning strongly-typed Pydantic models with log entries.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.slg1_parser import (
    is_slg1_initial_screen,
    is_slg1_no_results,
    parse_slg1_log_list,
)
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import SLG1_NO_LOGS_FOUND_DE, SLG1_NO_LOGS_FOUND_EN
from sapguimcp.models import TableData
from sapguimcp.models.config import get_sap_config
from sapguimcp.models.slg1_models import (
    SLG1FileSummary,
    SLG1LogEntry,
    SLG1LogListResult,
)
from sapguimcp.utils import SapLanguage, as_sap_language, format_sap_date

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_slg1_tools"]

# Column headers that identify a row of the SLG1 log list as a log (the grid of a selected log holds messages instead)
_SLG1_LOG_NUMBER_HEADERS = ("Protokollnr.", "Log Number", "Log number")

_MAX_LOGS = 50
# Item columns of the log tree in SAP's standard layout (the node text itself is date, time and user): the number of
# messages, the external ID, the texts of the object and the subobject, and (last) the log number.
_TREE_COLUMN_MESSAGES = "100"
_TREE_COLUMN_EXTERNAL_ID = "101"
_TREE_COLUMN_OBJECT = "102"
_TREE_COLUMN_SUBOBJECT = "103"
_TREE_COLUMN_LOG_NUMBER = "107"
# A log node's text: a date, a time (with AM/PM in some date formats) and the user, if there is one. The 'More ...' node
# the tree ends in when the selection holds more logs than it loaded does not look like this.
_TREE_NODE_TEXT = re.compile(
    r"^(?P<date>\S+)\s+(?P<time>\d{1,2}:\d{2}:\d{2}(?:\s*[AP]M)?)(?:\s+(?P<user>\S+))?$", re.IGNORECASE
)


def _safe_int(value: str | None) -> int:
    """Convert a value to int, returning 0 on failure."""
    try:
        return int(value or "0")
    except (ValueError, TypeError):
        return 0


def _tree_item(tree: Any, columns: set[str], key: str, column: str) -> str:
    """The text of one item of a log node, empty if the tree has no such column."""
    return str(tree.get_item_text(key, column)).strip() if column in columns else ""


def _read_log_tree(session: Any, max_logs: int) -> tuple[list[SLG1LogEntry], bool]:
    """Read the logs of the log tree on screen (COM thread): the newest ``max_logs``, newest first, and if more exist.

    The desktop lists the logs in a flat tree next to a grid that holds the messages of the selected log: one node per
    log whose text is ``<date> <time> <user>``, with the other columns as items. The tree shows the descriptions of
    the object and the subobject, not their technical names. If the tree ends in a
    'More ...' node, SAP loaded only the first logs of the selection: these are the newest of those, so the result is
    reported as truncated. ``([], False)`` if there is no tree.
    """
    from sapsucker.components.tree import GuiTree  # pylint: disable=import-outside-toplevel

    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    wnd: Any = session.find_by_id("wnd[0]")
    for elem in _flatten(wnd.dump_tree()):
        if elem.type_as_number != 122:
            continue
        tree: Any = session.find_by_id(elem.id)
        if not isinstance(tree, GuiTree):
            continue
        columns = set(tree.get_column_names())
        keys = tree.get_all_node_keys()
        # Only the end of the tree is looked at: reading the text of every node would cost a COM call per node.
        stamps: dict[str, re.Match[str]] = {}
        more_on_server = False
        for key in keys[-(max_logs + 1) :]:
            match = _TREE_NODE_TEXT.match(str(tree.get_node_text_by_key(key)).strip())
            if match:
                stamps[key] = match
            else:
                more_on_server = True  # the 'More ...' node
        logs: list[SLG1LogEntry] = []
        for key, match in list(stamps.items())[-max_logs:][::-1]:
            logs.append(
                SLG1LogEntry(
                    log_number=_tree_item(tree, columns, key, _TREE_COLUMN_LOG_NUMBER),
                    object=_tree_item(tree, columns, key, _TREE_COLUMN_OBJECT),
                    subobject=_tree_item(tree, columns, key, _TREE_COLUMN_SUBOBJECT),
                    external_id=_tree_item(tree, columns, key, _TREE_COLUMN_EXTERNAL_ID),
                    date=match.group("date"),
                    time=match.group("time"),
                    user=match.group("user") or "",
                    message_count=_safe_int(_tree_item(tree, columns, key, _TREE_COLUMN_MESSAGES)),
                )
            )
        return logs, more_on_server or len(keys) > max_logs
    return [], False


async def _slg1_lookup_desktop(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches,too-many-locals,too-many-return-statements
    backend: "WebGuiBackend | DesktopBackend",
    object_name: str,
    subobject: str | None = None,
    external_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> SLG1LogListResult:
    """Desktop-specific SLG1 lookup using read_table instead of ARIA parsing."""
    now = datetime.now(UTC)
    sap_cfg = get_sap_config()
    language: SapLanguage = as_sap_language(sap_cfg.get_default().language)
    logger.info("SLG1 desktop backend path", extra={"object": object_name})

    tx_result = await backend.enter_transaction("SLG1")
    if not tx_result.success:
        return SLG1LogListResult.failure(
            f"Failed to navigate to SLG1: {tx_result.error}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )
    await backend.wait_for_ready()

    # Fill selection screen
    fields: dict[str, str] = {}
    if language == "DE":
        fields["Objekt"] = object_name
        if subobject:
            fields["Unterobjekt"] = subobject
        if external_id:
            fields["Ext. Identif."] = external_id
    else:
        fields["Object"] = object_name
        if subobject:
            fields["Subobject"] = subobject
        if external_id:
            fields["External ID"] = external_id

    # A filter that cannot be applied fails the lookup: it would otherwise return the default selection (the logs of
    # today) as if it were the answer. The date fields are not found by their labels on the desktop, so they are filled
    # by their technical names (the 'to' field's name starts with a star).
    unapplied: list[str] = []
    fill_result = await backend.fill_form(fields)
    unapplied.extend(fill_result.not_found)
    unapplied.extend(error.field for error in fill_result.errors)  # found, but the value was not accepted
    for value, field_name, filter_name in (
        (from_date, "BALHDR-ALDATE", "from_date"),
        (to_date, "*BALHDR-ALDATE", "to_date"),
    ):
        if value and not await backend.focus_and_type(field_name, format_sap_date(value, language), delay_ms=50):
            unapplied.append(filter_name)
    if unapplied:
        return SLG1LogListResult.failure(
            f"Could not apply the filter(s) on the SLG1 selection screen: {', '.join(unapplied)}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    # Execute search (F8)
    await backend.press_key("F8")
    await backend.wait_for_ready()

    # Check status bar
    sbar = await backend.get_status_bar()
    filters = _build_filters(object_name, subobject, external_id, from_date, to_date)

    if sbar.type == "E":
        return SLG1LogListResult.failure(
            f"SLG1 error: {sbar.message}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    if sbar.message and any(
        msg.lower() in sbar.message.lower()
        for msg in [
            "keine protokolle",
            "no logs",
            "no application log",
            SLG1_NO_LOGS_FOUND_DE,
            SLG1_NO_LOGS_FOUND_EN,
        ]
    ):
        return SLG1LogListResult(
            logs=[],
            log_count=0,
            logs_truncated=False,
            filters_applied=filters,
            retrieved_at=now,
        )

    # The logs are listed in a tree (next to a grid that holds the messages of the selected log), so read that first
    desktop = cast("DesktopBackend", backend)
    session = desktop.require_session()
    tree_logs, tree_truncated = await desktop.com.run(lambda: _read_log_tree(session, _MAX_LOGS))
    if tree_logs:
        return SLG1LogListResult(
            logs=tree_logs,
            log_count=len(tree_logs),
            logs_truncated=tree_truncated,
            filters_applied=filters,
            retrieved_at=now,
        )

    # Read table data
    table_data: TableData = await backend.read_table(start_row=1, max_rows=_MAX_LOGS)

    # No rows without a "no logs" status message is not an empty result, and neither are rows that are no logs: the
    # logs are listed in a tree next to a grid that stays empty until a log is selected (and then holds its messages),
    # so there is no log list to read here.
    if not table_data.rows or not any(h in _SLG1_LOG_NUMBER_HEADERS for h in table_data.headers):
        return SLG1LogListResult.failure(
            "Could not read SLG1 log list: the desktop shows the logs in a tree, which cannot be read as a table",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    # Convert to SLG1LogEntry models
    logs: list[SLG1LogEntry] = []
    for tr in table_data.rows:
        d = tr.data
        logs.append(
            SLG1LogEntry(
                log_number=d.get("Protokollnr.", d.get("Log Number", d.get("Log number", ""))),
                object=d.get("Objekt", d.get("Object", "")),
                subobject=d.get("Unterobjekt", d.get("Subobject", "")),
                external_id=d.get("Ext. Identif.", d.get("External ID", "")),
                date=d.get("Datum", d.get("Date", "")),
                time=d.get("Uhrzeit", d.get("Time", "")),
                user=d.get("Benutzer", d.get("User", "")),
                message_count=_safe_int(d.get("Anzahl Nachr.", d.get("No. Messages", "0"))),
            )
        )

    return SLG1LogListResult(
        logs=logs,
        log_count=len(logs),
        logs_truncated=len(logs) >= 50,
        filters_applied=filters,
        retrieved_at=now,
    )


async def _slg1_lookup(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches,too-many-locals
    backend: "WebGuiBackend | DesktopBackend",
    object_name: str,
    subobject: str | None = None,
    external_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> SLG1LogListResult:
    """Execute SLG1 lookup and return parsed results."""
    now = datetime.now(UTC)

    # Desktop backend: use read_table instead of ARIA snapshot parsing
    if backend.backend_type == "desktop":
        return await _slg1_lookup_desktop(backend, object_name, subobject, external_id, from_date, to_date)

    sap_cfg = get_sap_config()
    language: SapLanguage = as_sap_language(sap_cfg.get_default().language)

    # Navigate to SLG1
    tx_result = await backend.enter_transaction("SLG1")
    if not tx_result.success:
        return SLG1LogListResult.failure(
            f"Failed to navigate to SLG1: {tx_result.error}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    # Wait for SLG1 selection screen to fully load
    await backend.wait_for_ready()

    # Build fields dict based on language
    # Field labels from real ARIA snapshot:
    # DE: "Objekt", "Unterobjekt", "Ext. Identif.", "von (Datum/Uhrzeit)", "bis (Datum/Uhrzeit)"
    # EN: will need exploration - using reasonable guesses
    fields: dict[str, str] = {}

    if language == "DE":
        fields["Objekt"] = object_name
        if subobject:
            fields["Unterobjekt"] = subobject
        if external_id:
            fields["Ext. Identif."] = external_id
        if from_date:
            fields["von (Datum/Uhrzeit)"] = format_sap_date(from_date, language)
        if to_date:
            fields["bis (Datum/Uhrzeit)"] = format_sap_date(to_date, language)
    else:
        fields["Object"] = object_name
        if subobject:
            fields["Subobject"] = subobject
        if external_id:
            fields["External ID"] = external_id
        if from_date:
            fields["From (Date/Time)"] = format_sap_date(from_date, language)
        if to_date:
            fields["To (Date/Time)"] = format_sap_date(to_date, language)

    # Fill selection screen
    fill_result = await backend.fill_form(fields)
    if fill_result.not_found:
        logger.warning("SLG1 fields not found: %r", fill_result.not_found)

    # Execute search (F8)
    await backend.press_key("F8")
    await backend.wait_for_ready()

    # Capture result snapshot
    snapshot = AriaSnapshot(await backend.get_snapshot())

    # Check for no results (explicit status bar message)
    if is_slg1_no_results(snapshot):
        return SLG1LogListResult(
            logs=[],
            log_count=0,
            logs_truncated=False,
            filters_applied=_build_filters(object_name, subobject, external_id, from_date, to_date),
            retrieved_at=now,
        )

    # If still on initial screen after F8, read status bar for error details
    if is_slg1_initial_screen(snapshot):
        sb_info = await backend.get_status_bar()
        if sb_info.type in ("error", "warning", "E", "W"):
            return SLG1LogListResult.failure(
                f"SLG1 error: {sb_info.message}",
                logs=[],
                log_count=0,
                logs_truncated=False,
                retrieved_at=now,
            )
        # No error in status bar — genuinely no results
        return SLG1LogListResult(
            logs=[],
            log_count=0,
            logs_truncated=False,
            filters_applied=_build_filters(object_name, subobject, external_id, from_date, to_date),
            retrieved_at=now,
        )

    # Parse the log list
    result = parse_slg1_log_list(snapshot)
    result.filters_applied = _build_filters(object_name, subobject, external_id, from_date, to_date)
    return result


def _build_filters(
    object_name: str,
    subobject: str | None,
    external_id: str | None,
    from_date: str | None,
    to_date: str | None,
) -> dict[str, str]:
    """Build filters_applied dict from parameters."""
    filters: dict[str, str] = {"object": object_name}
    if subobject:
        filters["subobject"] = subobject
    if external_id:
        filters["external_id"] = external_id
    if from_date:
        filters["from_date"] = from_date
    if to_date:
        filters["to_date"] = to_date
    return filters


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_slg1_tools(mcp: FastMCP) -> None:
    """Register SLG1 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
        description=(
            "Search and read SAP application logs from SLG1. "
            "USE THIS instead of sap_transaction('SLG1') - faster and returns structured data. "
            "Returns log entries with metadata (date, time, user, object, subobject, external ID, "
            "message count, log number). Best used when the log object is known "
            "(e.g., /SDF/CALM for Cloud ALM, /SDF/AIMAX for AI). "
            "Use '*' as object to search all logs. "
            "Requires at minimum the 'object' parameter. "
            "Returns up to 50 logs."
        ),
    )
    async def sap_slg1_lookup(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        object: str,  # noqa: A002  # pylint: disable=redefined-builtin
        subobject: str | None = None,
        external_id: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SLG1LogListResult | SLG1FileSummary:
        """
        Search and read SAP application logs from SLG1.

        Args:
            object: Log object (e.g., '/SDF/CALM', '/SDF/AIMAX', '*' for all)
            subobject: Log subobject (optional filter)
            external_id: External identifier (optional filter)
            from_date: Start date filter (YYYY-MM-DD format)
            to_date: End date filter (YYYY-MM-DD format)
            output_file: If provided, write results to this JSON file and return summary.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SLG1LogListResult with log entries, or
            SLG1FileSummary with file path when output_file is provided.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_slg1_lookup")
        except ValueError as e:
            return SLG1LogListResult.failure(
                f"Session error: {e}",
                logs=[],
                log_count=0,
                logs_truncated=False,
                retrieved_at=datetime.now(UTC),
            )

        try:
            result = await _slg1_lookup(
                backend,
                object,
                subobject,
                external_id,
                from_date,
                to_date,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("SLG1 lookup failed")
            result = SLG1LogListResult.failure(
                f"SLG1 lookup error: {e}",
                logs=[],
                log_count=0,
                logs_truncated=False,
                retrieved_at=datetime.now(UTC),
            )

        # Write to file if requested (only on success)
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            total_messages = sum(log.message_count for log in result.logs)
            return SLG1FileSummary(
                success=result.success,
                error=result.error,
                output_file=str(output_path.absolute()),
                log_count=result.log_count,
                total_messages=total_messages,
                logs_truncated=result.logs_truncated,
                retrieved_at=result.retrieved_at,
            )

        return result
