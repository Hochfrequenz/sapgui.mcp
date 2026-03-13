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
from sapwebguimcp.backend.webgui.parsers.se37_parser import SE37TabSnapshots, parse_se37_snapshot
from sapwebguimcp.models import (
    SE37Entry,
    SE37Error,
    SE37FileSummary,
    SE37Result,
)
from sapwebguimcp.tools.field_helpers import fill_and_display

logger = logging.getLogger(__name__)

__all__ = ["register_se37_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 5


# =============================================================================
# SE37 Navigation Helpers
# =============================================================================


# DE/EN label variants for the function module input field.
_FM_FIELD_LABELS = [
    "Funktionsbaustein",
    "Function module",
    "Function Module",
]


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


async def _lookup_fm_on_initial_screen(backend: SapUiBackend, fm_name: str) -> SE37Entry | SE37Error:
    """Look up a function module assuming we're already on the SE37 initial screen.

    The caller handles navigation (``enter_transaction``) and state reset
    (``/n`` between lookups) to prevent state bleeding in batch mode.
    """
    # Ensure the SE37 screen is fully loaded before interacting.
    await backend.wait_for_ready()

    # Fill field with real keyboard events, press F7, and verify navigation.
    error_msg = await fill_and_display(backend, _FM_FIELD_LABELS, fm_name, tcode_label="function module")
    if error_msg:
        return SE37Error(
            function_module=fm_name,
            error=error_msg,
            retrieved_at=datetime.now(UTC),
        )

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
            # Navigate to Easy Access first to ensure a clean starting state,
            # then open SE37.  This prevents state bleeding between lookups.
            await backend.enter_transaction("/n")
            await backend.wait_for_ready()

            tx_result = await backend.enter_transaction("SE37")
            if not tx_result.success:
                errors.append(
                    SE37Error(
                        function_module=fm_name,
                        error=f"Failed to navigate to SE37: {tx_result.error}",
                        retrieved_at=datetime.now(UTC),
                    )
                )
                continue
            await backend.wait_for_ready()

            try:
                result = await _lookup_fm_on_initial_screen(backend, fm_name)
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
