"""
SLG1 (Application Log) lookup tool.

This module provides a tool to search and read SAP application logs via SLG1,
returning strongly-typed Pydantic models with log entries.
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
from sapguimcp.backend.webgui.parsers.slg1_parser import (
    is_slg1_initial_screen,
    is_slg1_no_results,
    parse_slg1_log_list,
)
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.models import TableData
from sapguimcp.models.config import get_sap_config
from sapguimcp.models.slg1_models import (
    SLG1FileSummary,
    SLG1LogEntry,
    SLG1LogListResult,
)
from sapguimcp.utils import SapLanguage, format_sap_date

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_slg1_tools"]


def _safe_int(value: str | None) -> int:
    """Convert a value to int, returning 0 on failure."""
    try:
        return int(value or "0")
    except (ValueError, TypeError):
        return 0


async def _slg1_lookup_desktop(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches,too-many-locals
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
    language: SapLanguage = sap_cfg.get_default().language
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

    fill_result = await backend.fill_form(fields)
    if fill_result.not_found:
        logger.warning("SLG1 desktop fields not found: %r", fill_result.not_found)

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
        msg in sbar.message.lower() for msg in ["keine protokolle", "no logs", "no application log"]
    ):
        return SLG1LogListResult(
            logs=[],
            log_count=0,
            logs_truncated=False,
            filters_applied=filters,
            retrieved_at=now,
        )

    # Read table data
    table_data: TableData = await backend.read_table(start_row=1, max_rows=50)

    if not table_data.headers:
        return SLG1LogListResult.failure(
            "Could not read SLG1 log list table",
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
    language: SapLanguage = sap_cfg.get_default().language

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
            readOnlyHint=True,
            openWorldHint=False,
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
