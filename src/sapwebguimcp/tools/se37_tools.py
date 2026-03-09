"""
SE37 (Function Builder) lookup tool.

This module provides a tool to look up function module metadata from SE37,
returning strongly-typed Pydantic models with parameter and exception details.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.protocol import SapUiBackend
from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.models import (
    SE37Entry,
    SE37Error,
    SE37FileSummary,
    SE37Result,
)
from sapwebguimcp.parsers.se37_parser import SE37TabSnapshots, parse_se37_snapshot

logger = logging.getLogger(__name__)

__all__ = ["register_se37_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 5


# =============================================================================
# SE37 Navigation Helpers
# =============================================================================


async def _fill_fm_field(backend: SapUiBackend, fm_name: str) -> SE37Error | None:
    """Fill the function module name field in SE37. Returns error or None."""
    now = datetime.now(UTC)

    # Try multiple label variants (DE and EN)
    labels = [
        "Funktionsbaustein",
        "Function module",
        "Function Module",
    ]

    for label in labels:
        try:
            await backend.fill_field(label, fm_name.upper())
            return None
        except ValueError:  # pylint: disable=broad-exception-caught
            continue

    # Fallback: find the first visible input field by CSS selector.
    # SE37 initial screen typically has a single input field whose label
    # may not match standard text due to SAP's non-standard HTML.
    try:
        fields = await backend.discover_fields()
        if fields:
            selector = fields[0].selector
            if selector:
                await backend.fill_field(selector, fm_name.upper())
                return None
    except (ValueError, Exception):  # pylint: disable=broad-exception-caught
        pass

    return SE37Error(
        function_module=fm_name,
        error="Could not find function module field in SE37",
        retrieved_at=now,
    )


async def _check_fm_not_found(backend: SapUiBackend, fm_name: str) -> SE37Error | None:
    """Check if function module was not found by examining the status bar. Returns error or None."""
    now = datetime.now(UTC)

    # Check status bar for specific error messages (narrow, avoids false positives)
    status = await backend.get_status_bar()
    status_text = (status.message or "").lower()

    not_found_msgs = {
        "ist noch nicht vorhanden",
        "does not exist",
        "nicht gefunden",
        "not found",
        "nicht vorhanden",
        "existiert nicht",
    }
    if status_text and any(msg in status_text for msg in not_found_msgs):
        return SE37Error(function_module=fm_name, error=f"Function module '{fm_name}' not found", retrieved_at=now)

    # Secondary check: verify we left the initial screen
    snapshot = await backend.get_snapshot()
    snapshot_lower = str(snapshot).lower()
    is_initial_screen = "einstieg" in snapshot_lower or "initial screen" in snapshot_lower
    if is_initial_screen:
        return SE37Error(
            function_module=fm_name,
            error=f"Function module '{fm_name}' not found (still on initial screen)",
            retrieved_at=now,
        )

    return None


async def _capture_tab_snapshot(backend: SapUiBackend, tab_name: str) -> str | None:
    """Click a tab and capture its snapshot. Returns snapshot or None."""
    # Try German and English tab names
    tab_names = {
        "import": ["Import"],
        "export": ["Export"],
        "changing": ["Changing"],
        "tables": ["Tabellen", "Tables"],
        "exceptions": ["Ausnahmen", "Exceptions"],
    }

    names_to_try = tab_names.get(tab_name, [tab_name])
    for name in names_to_try:
        try:
            await backend.click_tab(name)
            snapshot = await backend.get_snapshot()
            return str(snapshot)
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return None


async def _lookup_single_fm(backend: SapUiBackend, fm_name: str) -> SE37Entry | SE37Error:
    """Look up a single function module in SE37."""
    now = datetime.now(UTC)

    # Navigate to SE37
    tx_result = await backend.enter_transaction("SE37")
    if not tx_result.success:
        return SE37Error(
            function_module=fm_name,
            error=f"Failed to navigate to SE37: {tx_result.error}",
            retrieved_at=now,
        )

    # Wait for SE37 screen to be ready
    await backend.wait_for_ready()

    # Fill function module name
    error = await _fill_fm_field(backend, fm_name)
    if error:
        return error

    # Click display (F7)
    await backend.press_key("F7")
    await backend.wait_for_ready()

    # Check for not found error
    error = await _check_fm_not_found(backend, fm_name)
    if error:
        return error

    # Get main snapshot first
    main_snapshot = await backend.get_snapshot()
    logger.debug("Got main snapshot", extra={"object": fm_name, "length": len(str(main_snapshot))})

    # Capture each tab
    import_raw = await _capture_tab_snapshot(backend, "import")
    export_raw = await _capture_tab_snapshot(backend, "export")
    changing_raw = await _capture_tab_snapshot(backend, "changing")
    tables_raw = await _capture_tab_snapshot(backend, "tables")
    exceptions_raw = await _capture_tab_snapshot(backend, "exceptions")
    tab_snapshots = SE37TabSnapshots(
        import_tab=AriaSnapshot(import_raw) if import_raw is not None else None,
        export_tab=AriaSnapshot(export_raw) if export_raw is not None else None,
        changing_tab=AriaSnapshot(changing_raw) if changing_raw is not None else None,
        tables_tab=AriaSnapshot(tables_raw) if tables_raw is not None else None,
        exceptions_tab=AriaSnapshot(exceptions_raw) if exceptions_raw is not None else None,
    )

    # Parse all snapshots
    return parse_se37_snapshot(
        snapshot=AriaSnapshot(str(main_snapshot)),
        fm_name=fm_name,
        tab_snapshots=tab_snapshots,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se37_tools(mcp: FastMCP) -> None:
    """Register SE37 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up function module metadata from SE37 (Function Builder). "
            "USE THIS instead of sap_transaction('SE37') - faster and returns structured data. "
            "Returns function module signature including import/export/changing/tables parameters "
            "and exceptions. Supports single FM or list of FMs. "
            "Each parameter includes: name, typing (LIKE/TYPE), reference type, "
            "default value, optional flag, and description."
        ),
    )
    async def sap_se37_lookup(
        function_modules: str | list[str],
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE37Result | SE37FileSummary:
        """
        Look up function module metadata from SE37.

        Args:
            function_modules: Single FM name or list of names
                (e.g., 'RFC_READ_TABLE' or ['RFC_READ_TABLE', 'BAPI_USER_GET_DETAIL'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >5 function modules to avoid context overflow.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE37Result with entries and errors (inline), or
            SE37FileSummary with file path and statistics (when output_file provided)
        """
        fm_list = [function_modules] if isinstance(function_modules, str) else list(function_modules)

        if not fm_list:
            return SE37Result.failure("No function modules provided")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se37_lookup")
        except ValueError as e:
            return SE37Result.failure(f"Session error: {e}")

        entries: list[SE37Entry] = []
        errors: list[SE37Error] = []

        for fm_name in fm_list:
            try:
                result = await _lookup_single_fm(backend, fm_name)
                if isinstance(result, SE37Entry):
                    entries.append(result)
                else:
                    errors.append(result)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Looking up in SE37", extra={"object": fm_name})
                errors.append(
                    SE37Error(
                        function_module=fm_name,
                        error=f"Error looking up '{fm_name}': {e}",
                        retrieved_at=datetime.now(UTC),
                    )
                )

        # Build final result
        if entries:
            final_result = SE37Result(entries=entries, errors=errors)
        else:
            final_result = SE37Result.failure(
                error=f"All {len(errors)} lookups failed",
                entries=[],
                errors=errors,
            )

        # Write to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(final_result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SE37FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(fm_list),
                successful=len(entries),
                failed=len(errors),
                sample_entries=[e.function_module for e in entries[:5]],
                sample_errors=[e.function_module for e in errors[:5]],
            )

        if len(fm_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning function modules inline - consider using output_file parameter",
                extra={"count": len(fm_list)},
            )

        return final_result
