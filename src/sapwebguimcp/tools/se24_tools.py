"""
SE24 (Class Builder) lookup tool.

This module provides a tool to look up class/interface metadata from SE24,
returning strongly-typed Pydantic models with method and attribute details.
"""

import asyncio
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
    """Fill the class/interface name field in SE24. Returns error or None.

    Uses JS to find the field element among multiple label variants, then
    focuses it and clicks it.  Follows with ``type_text`` (real Playwright
    keyboard events) to type the class name.  This ensures SAP WebGUI's
    framework registers the value via ``keydown``/``keyup`` events, which
    JS-only ``el.value = ...`` doesn't trigger reliably.
    """
    now = datetime.now(UTC)
    upper_name = class_name.upper()

    # Find the field element via JS and get its ID so we can click it.
    # This reuses the same label-matching logic as fill_field/fill_main_input.
    labels = [
        "Objekttyp",
        "Object type",
        "Object Type",
        "Klasse/Interface",
        "Class/Interface",
    ]

    # Find, focus, click, and select-all in a single JS roundtrip.
    # Returns true if a field was found, false otherwise.
    # The actual value will be typed via type_text (real keyboard events).
    labels_js = "[" + ",".join(f'"{lbl}"' for lbl in labels) + "]"
    found = await backend.evaluate_javascript(f"""(() => {{
            const labels = {labels_js};

            function isUsableInput(input) {{
                if (input.getAttribute('role') === 'combobox') return false;
                if (input.getAttribute('ct') === 'CB') return false;
                if (input.closest('[role="toolbar"]')) return false;
                if (input.closest('[role="banner"]')) return false;
                if (input.offsetParent === null) return false;
                if (input.disabled || input.readOnly) return false;
                return true;
            }}

            function activateInput(input) {{
                input.focus();
                input.click();
                input.select();
                return true;
            }}

            // 1. Match by title attribute (DE/EN label variants).
            const titledInputs = document.querySelectorAll('input[title]');
            for (const label of labels) {{
                for (const input of titledInputs) {{
                    if (input.getAttribute('title') !== label) continue;
                    if (!isUsableInput(input)) continue;
                    return activateInput(input);
                }}
            }}

            // 2. Fallback: first visible text input not in toolbar/banner.
            const allInputs = document.querySelectorAll(
                'input[type="text"], input:not([type])'
            );
            for (const input of allInputs) {{
                if (!isUsableInput(input)) continue;
                return activateInput(input);
            }}

            return false;
        }})()""")

    if not found:
        return SE24Error(
            class_name=class_name,
            error="Could not find class/interface field in SE24",
            retrieved_at=now,
        )

    # Type the class name with real keyboard events.
    # The field is already focused and text selected from the JS above.
    await backend.type_text(upper_name)

    return None


_NOT_FOUND_MSGS = frozenset({"existiert nicht", "does not exist", "nicht gefunden", "not found", "nicht vorhanden"})

# How long to wait for F7 navigation to complete before declaring failure.
_F7_POLL_INTERVAL_MS = 500
_F7_MAX_POLLS = 10  # 10 * 500ms = 5 seconds max wait


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
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    return None


async def _fill_and_display(backend: SapUiBackend, class_name: str) -> SE24Error | None:
    """Fill the class field and press F7 (Display). Returns error or None.

    Retries once if still on the initial screen after F7, because SAP's
    WebGUI sometimes doesn't register the JS-based field fill on the first
    attempt (especially after ``/nSE24`` navigation in batch mode).
    """
    for attempt in range(2):
        if attempt > 0:
            logger.info("Retrying fill+F7 for %s (attempt %d)", class_name, attempt + 1)

        error = await _fill_class_field(backend, class_name)
        if error:
            return error

        # Brief wait for SAP to register the typed value before pressing F7.
        await asyncio.sleep(0.3)

        # Click display (F7)
        await backend.press_key("F7")
        await backend.wait_for_ready()

        # Check for definitive "not found" error — no retry needed.
        status = await backend.get_status_bar()
        status_text = (status.message or "").lower()
        if status_text and any(msg in status_text for msg in _NOT_FOUND_MSGS):
            return SE24Error(
                class_name=class_name,
                error=f"Class/interface '{class_name}' not found",
                retrieved_at=datetime.now(UTC),
            )

        # Poll: wait for the page to leave the initial screen.
        navigated = False
        for poll in range(_F7_MAX_POLLS):
            snapshot = await backend.get_snapshot()
            snapshot_lower = str(snapshot).lower()
            if "einstieg" not in snapshot_lower and "initial screen" not in snapshot_lower:
                navigated = True
                break
            logger.debug("SE24 still on initial screen, poll %d/%d", poll + 1, _F7_MAX_POLLS)
            await asyncio.sleep(_F7_POLL_INTERVAL_MS / 1000)

        if navigated:
            return None

    # Include status bar text for debugging — might contain a SAP error
    # that isn't in _NOT_FOUND_MSGS.
    final_status = await backend.get_status_bar()
    status_hint = f" (status: {final_status.message})" if final_status.message else ""

    return SE24Error(
        class_name=class_name,
        error=f"Class/interface '{class_name}' not found (still on initial screen after retries){status_hint}",
        retrieved_at=datetime.now(UTC),
    )


async def _lookup_class_on_initial_screen(backend: SapUiBackend, class_name: str) -> SE24Entry | SE24Error:
    """Look up a class assuming we're already on the SE24 initial screen.

    After a successful lookup, the browser will be on the class detail screen.
    The caller handles navigation between lookups (via ``enter_transaction``).
    """
    # Ensure the SE24 screen is fully loaded before interacting.
    await backend.wait_for_ready()

    # Fill class name, press F7, and verify we left the initial screen.
    error = await _fill_and_display(backend, class_name)
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
            # Navigate to Easy Access first to ensure a clean starting state,
            # then open SE24.  This is simple and robust — no state from a
            # previous lookup can leak into the next one.
            await backend.enter_transaction("/n")
            await backend.wait_for_ready()

            tx_result = await backend.enter_transaction("SE24")
            if not tx_result.success:
                errors.append(
                    SE24Error(
                        class_name=class_name,
                        error=f"Failed to navigate to SE24: {tx_result.error}",
                        retrieved_at=datetime.now(UTC),
                    )
                )
                continue
            await backend.wait_for_ready()

            try:
                result = await _lookup_class_on_initial_screen(backend, class_name)
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
