"""
SE24 (Class Builder) lookup tool.

This module provides a tool to look up class/interface metadata from SE24,
returning strongly-typed Pydantic models with method and attribute details.
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
    SE24Entry,
    SE24Error,
    SE24FileSummary,
    SE24Result,
)
from sapwebguimcp.parsers.se24_parser import SE24TabSnapshots, parse_se24_snapshot

logger = logging.getLogger(__name__)

__all__ = ["register_se24_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 5


# =============================================================================
# SE24 Navigation Helpers
# =============================================================================


async def _fill_class_field(backend: SapUiBackend, class_name: str) -> SE24Error | None:
    """Fill the class/interface name field in SE24. Returns error or None."""
    now = datetime.now(UTC)

    # Try multiple label variants (DE and EN)
    labels = [
        "Objekttyp",
        "Object type",
        "Object Type",
        "Klasse/Interface",
        "Class/Interface",
    ]

    for label in labels:
        try:
            await backend.fill_field(label, class_name.upper())
            return None
        except ValueError:  # pylint: disable=broad-exception-caught
            continue

    # Fallback: find the first visible input field by CSS selector.
    # SE24 initial screen typically has a single input field whose label
    # may not match standard text due to SAP's non-standard HTML.
    try:
        fields = await backend.discover_fields()
        if fields:
            selector = fields[0].selector
            if selector:
                await backend.fill_field(selector, class_name.upper())
                return None
    except (ValueError, Exception):  # pylint: disable=broad-exception-caught
        pass

    return SE24Error(
        class_name=class_name,
        error="Could not find class/interface field in SE24",
        retrieved_at=now,
    )


async def _check_class_not_found(backend: SapUiBackend, class_name: str) -> SE24Error | None:
    """Check if class was not found by examining the status bar. Returns error or None."""
    now = datetime.now(UTC)

    # Check status bar for specific error messages (narrow, avoids false positives)
    status = await backend.get_status_bar()
    status_text = (status.message or "").lower()

    not_found_msgs = {"existiert nicht", "does not exist", "nicht gefunden", "not found", "nicht vorhanden"}
    if status_text and any(msg in status_text for msg in not_found_msgs):
        return SE24Error(class_name=class_name, error=f"Class/interface '{class_name}' not found", retrieved_at=now)

    # Secondary check: verify we left the initial screen
    snapshot = await backend.get_snapshot()
    snapshot_lower = str(snapshot).lower()
    is_initial_screen = "einstieg" in snapshot_lower or "initial screen" in snapshot_lower
    if is_initial_screen:
        return SE24Error(
            class_name=class_name,
            error=f"Class/interface '{class_name}' not found (still on initial screen)",
            retrieved_at=now,
        )

    return None


async def _capture_tab_snapshot(backend: SapUiBackend, tab_name: str) -> str | None:
    """Click a tab and capture its snapshot. Returns snapshot or None."""
    # Try German and English tab names
    tab_names = {
        "methods": ["Methoden", "Methods"],
        "attributes": ["Attribute", "Attributes"],
        "interfaces": ["Interfaces", "Schnittstellen"],
    }

    names_to_try = tab_names.get(tab_name, [tab_name])
    for name in names_to_try:
        try:
            await backend.click_tab(name)
            snapshot = await backend.get_snapshot()
            return str(snapshot)
        except ValueError:
            continue

    return None


async def _lookup_single_class(backend: SapUiBackend, class_name: str) -> SE24Entry | SE24Error:
    """Look up a single class/interface in SE24."""
    now = datetime.now(UTC)

    # Navigate to SE24
    tx_result = await backend.enter_transaction("SE24")
    if not tx_result.success:
        return SE24Error(
            class_name=class_name,
            error=f"Failed to navigate to SE24: {tx_result.error}",
            retrieved_at=now,
        )

    # Wait for SE24 screen to be ready
    await backend.wait_for_ready()

    # Fill class name
    error = await _fill_class_field(backend, class_name)
    if error:
        return error

    # Click display (F7)
    await backend.press_key("F7")
    await backend.wait_for_ready()

    # Check for not found error
    error = await _check_class_not_found(backend, class_name)
    if error:
        return error

    # Get main snapshot first
    main_snapshot = await backend.get_snapshot()
    logger.debug("Got main snapshot", extra={"object": class_name, "length": len(str(main_snapshot))})

    # Capture each tab
    methods_raw = await _capture_tab_snapshot(backend, "methods")
    attributes_raw = await _capture_tab_snapshot(backend, "attributes")
    interfaces_raw = await _capture_tab_snapshot(backend, "interfaces")
    tab_snapshots = SE24TabSnapshots(
        methods_tab=AriaSnapshot(methods_raw) if methods_raw is not None else None,
        attributes_tab=AriaSnapshot(attributes_raw) if attributes_raw is not None else None,
        interfaces_tab=AriaSnapshot(interfaces_raw) if interfaces_raw is not None else None,
    )

    # Parse all snapshots
    return parse_se24_snapshot(
        snapshot=main_snapshot,
        class_name=class_name,
        tab_snapshots=tab_snapshots,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se24_tools(mcp: FastMCP) -> None:
    """Register SE24 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up class/interface metadata from SE24 (Class Builder). "
            "USE THIS instead of sap_transaction('SE24') - faster and returns structured data. "
            "Returns class structure including methods with parameters, "
            "attributes, and implemented interfaces. Supports single class or list of classes. "
            "Each method includes: name, visibility, parameters, exceptions, and description."
        ),
    )
    async def sap_se24_lookup(
        classes: str | list[str],
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE24Result | SE24FileSummary:
        """
        Look up class/interface metadata from SE24.

        Args:
            classes: Single class/interface name or list of names
                (e.g., 'CL_SALV_TABLE' or ['CL_SALV_TABLE', 'CL_ABAP_CHAR_UTILITIES'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >5 classes to avoid context overflow.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE24Result with entries and errors (inline), or
            SE24FileSummary with file path and statistics (when output_file provided)
        """
        class_list = [classes] if isinstance(classes, str) else list(classes)

        if not class_list:
            return SE24Result.failure("No classes provided")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se24_lookup")
        except ValueError as e:
            return SE24Result.failure(f"Session error: {e}")

        entries: list[SE24Entry] = []
        errors: list[SE24Error] = []

        for class_name in class_list:
            try:
                result = await _lookup_single_class(backend, class_name)
                if isinstance(result, SE24Entry):
                    entries.append(result)
                else:
                    errors.append(result)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Looking up in SE24", extra={"object": class_name})
                errors.append(
                    SE24Error(
                        class_name=class_name,
                        error=f"Error looking up '{class_name}': {e}",
                        retrieved_at=datetime.now(UTC),
                    )
                )

        # Build final result
        if entries:
            final_result = SE24Result(entries=entries, errors=errors)
        else:
            final_result = SE24Result.failure(
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

            return SE24FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(class_list),
                successful=len(entries),
                failed=len(errors),
                sample_entries=[e.class_name for e in entries[:5]],
                sample_errors=[e.class_name for e in errors[:5]],
            )

        if len(class_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning classes inline - consider using output_file parameter",
                extra={"count": len(class_list)},
            )

        return final_result
