"""
SLG1 (Application Log) lookup tool.

This module provides a tool to search and read SAP application logs via SLG1,
returning strongly-typed Pydantic models with log entries.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.slg1_models import (
    SLG1FileSummary,
    SLG1LogListResult,
)
from sapwebguimcp.parsers.slg1_parser import (
    is_slg1_initial_screen,
    is_slg1_no_results,
    parse_slg1_log_list,
)
from sapwebguimcp.tools.sap_tool_impl import (
    sap_fill_form_impl,
    sap_transaction_impl,
)

logger = logging.getLogger(__name__)

__all__ = ["register_slg1_tools"]


def _format_sap_date(iso_date: str, language: str) -> str:
    """
    Convert ISO date (YYYY-MM-DD) to SAP format based on language.

    DE -> DD.MM.YYYY
    EN -> MM/DD/YYYY
    """
    parts = iso_date.split("-")
    if len(parts) != 3:
        return iso_date  # Return as-is if not valid ISO format
    year, month, day = parts
    if language.upper() == "DE":
        return f"{day}.{month}.{year}"
    return f"{month}/{day}/{year}"


async def _slg1_lookup(
    object_name: str,
    subobject: str | None = None,
    external_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> SLG1LogListResult:
    """Execute SLG1 lookup and return parsed results."""
    now = datetime.now(UTC)

    from sapwebguimcp.models.config import get_settings

    settings = get_settings()
    language = settings.sap_language

    # Navigate to SLG1
    tx_result = await sap_transaction_impl("SLG1")
    if not tx_result.success:
        return SLG1LogListResult.failure(
            f"Failed to navigate to SLG1: {tx_result.error}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    # Wait for SLG1 selection screen to fully load
    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

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
            fields["von (Datum/Uhrzeit)"] = _format_sap_date(from_date, language)
        if to_date:
            fields["bis (Datum/Uhrzeit)"] = _format_sap_date(to_date, language)
    else:
        fields["Object"] = object_name
        if subobject:
            fields["Subobject"] = subobject
        if external_id:
            fields["External ID"] = external_id
        if from_date:
            fields["From (Date/Time)"] = _format_sap_date(from_date, language)
        if to_date:
            fields["To (Date/Time)"] = _format_sap_date(to_date, language)

    # Fill selection screen
    fill_result = await sap_fill_form_impl(fields)
    if not fill_result.success:
        return SLG1LogListResult.failure(
            f"Failed to fill SLG1 selection screen: {fill_result.error}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    if fill_result.not_found:
        logger.warning("SLG1 fields not found: %r", fill_result.not_found)

    # Execute search (F8)
    from sapwebguimcp.tools.sap_tool_impl import sap_keyboard_impl

    kb_result = await sap_keyboard_impl("F8")
    if not kb_result.success:
        return SLG1LogListResult.failure(
            f"Failed to execute SLG1 search: {kb_result.error}",
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    # Wait for results to load
    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    # Capture result snapshot
    snapshot: str = await page.locator("body").aria_snapshot()

    # Check for no results
    if is_slg1_no_results(snapshot) or is_slg1_initial_screen(snapshot):
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
    async def sap_slg1_lookup(
        object: str,
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
        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_slg1_lookup")
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
                object,
                subobject,
                external_id,
                from_date,
                to_date,
            )
        except Exception as e:
            logger.exception("SLG1 lookup failed")
            result = SLG1LogListResult.failure(
                f"SLG1 lookup error: {e}",
                logs=[],
                log_count=0,
                logs_truncated=False,
                retrieved_at=datetime.now(UTC),
            )

        # Write to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            total_messages = sum(len(log.messages) for log in result.logs)
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
