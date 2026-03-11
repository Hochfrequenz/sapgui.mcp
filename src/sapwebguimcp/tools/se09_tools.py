"""
SE09 (Transport Organizer) lookup tool.

This module provides a read-only tool to list transport requests from SE09.
The tool navigates to SE09, applies filters, clicks Anzeigen (Display),
and parses the flat text list from the ARIA snapshot.
"""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.lang import (
    SE09_DISPLAY_BUTTON_DE,
    SE09_DISPLAY_BUTTON_EN,
    SE09_MODIFIABLE_DE,
    SE09_MODIFIABLE_EN,
    SE09_RELEASED_DE,
    SE09_RELEASED_EN,
    SE09_USER_FIELD_DE,
    SE09_USER_FIELD_EN,
)
from sapwebguimcp.models.se09_models import TransportListResult, TransportRequest, TransportTask
from sapwebguimcp.parsers.se09_parser import parse_se09_transport_list

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

__all__ = ["register_se09_tools"]


# =============================================================================
# SE09 Navigation Helpers
# =============================================================================


async def _fill_user_field(backend: "SapUiBackend", username: str) -> None:
    """Fill the username filter field in SE09."""
    result = await backend.fill_form({SE09_USER_FIELD_DE: username.upper(), SE09_USER_FIELD_EN: username.upper()})
    if not result.filled:
        logger.warning("User field not found in SE09 for any label")


async def _set_checkbox_state(backend: "SapUiBackend", label: str, should_be_checked: bool) -> None:
    """Safely set a checkbox to checked or unchecked state."""
    try:
        await backend.set_checkbox(label, should_be_checked)
        # SAP WebGUI checkboxes may trigger partial page reloads
        await backend.wait_for_ready()
    except ValueError:
        logger.warning("Failed to set checkbox '%s', skipping", label)


async def _set_request_type_filter(backend: "SapUiBackend", request_type: str) -> None:
    """Set request type checkboxes on SE09 selection screen.

    Always explicitly set both checkboxes because SE09 is stateful —
    it remembers checkbox state from the previous lookup in the session.
    """
    if request_type == "all":
        await _set_checkbox_state(backend, "Workbench", True)
        await _set_checkbox_state(backend, "Customizing", True)
    elif request_type == "workbench":
        await _set_checkbox_state(backend, "Workbench", True)
        await _set_checkbox_state(backend, "Customizing", False)
    elif request_type == "customizing":
        await _set_checkbox_state(backend, "Workbench", False)
        await _set_checkbox_state(backend, "Customizing", True)


async def _try_set_checkbox(backend: "SapUiBackend", labels: list[str], checked: bool) -> None:
    """Try setting a checkbox using multiple label variants (DE/EN). First match wins."""
    for label in labels:
        try:
            await backend.set_checkbox(label, checked)
            await backend.wait_for_ready()
            return
        except ValueError:
            continue
    logger.warning("Checkbox not found for any label: %s", labels)


async def _set_status_filter(backend: "SapUiBackend", status: str) -> None:
    """Set status filter checkboxes on SE09 selection screen.

    Always explicitly set both checkboxes because SE09 is stateful —
    it remembers checkbox state from the previous lookup in the session.
    """
    mod_labels = [SE09_MODIFIABLE_DE, SE09_MODIFIABLE_EN]
    rel_labels = [SE09_RELEASED_DE, SE09_RELEASED_EN]

    if status == "all":
        await _try_set_checkbox(backend, mod_labels, True)
        await _try_set_checkbox(backend, rel_labels, True)
    elif status == "modifiable":
        await _try_set_checkbox(backend, mod_labels, True)
        await _try_set_checkbox(backend, rel_labels, False)
    elif status == "released":
        await _try_set_checkbox(backend, mod_labels, False)
        await _try_set_checkbox(backend, rel_labels, True)


async def _click_display_button(backend: "SapUiBackend") -> None:
    """Click the Anzeigen/Display button to execute the search.

    Uses JS to click the button by its element ID, which is more reliable
    than Playwright's click() for SAP WebGUI custom button controls.
    """
    # Find the Anzeigen/Display button by text and click it via JS,
    # dispatching a proper mousedown+mouseup+click sequence
    js_click_display = """() => {
        const buttons = document.querySelectorAll('[role="button"]');
        for (const btn of buttons) {
            const text = btn.textContent?.trim() || '';
            if (text === 'Anzeigen' || text === 'Display') {
                // SAP WebGUI needs mousedown+mouseup for proper event handling
                btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
                btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                return {clicked: text, id: btn.id};
            }
        }
        return {clicked: null};
    }"""
    result = await backend.evaluate_javascript(js_click_display)
    if isinstance(result, str):
        result = json.loads(result)
    if result and result.get("clicked"):
        logger.info("Clicked display button '%s' (id=%s)", result["clicked"], result.get("id"))
        await backend.wait_for_ready()
        return

    # Fallback: try Playwright click
    for label in [SE09_DISPLAY_BUTTON_DE, SE09_DISPLAY_BUTTON_EN]:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            return
        except ValueError:
            continue

    logger.warning("Anzeigen/Display button not found")


_JS_CLICK_NEXT_EXPAND = """(skip) => {
    const region = document.querySelector('[role="region"]');
    if (!region) return {clicked: null, remaining: false};
    const children = [...region.children];
    const transportPattern = /^[A-Z0-9]{3}K\\d{6}(\\s+\\d{3})?$/;
    const skipSet = new Set(skip);
    for (let i = 0; i < children.length; i++) {
        const el = children[i];
        if (el.getAttribute('role') !== 'button') continue;
        for (let j = 1; j <= 3 && i + j < children.length; j++) {
            const sibText = children[i + j].textContent?.trim() || '';
            if (transportPattern.test(sibText) && !skipSet.has(sibText)) {
                el.click();
                return {clicked: sibText, remaining: true};
            }
        }
    }
    return {clicked: null, remaining: false};
}"""


async def _expand_transport_nodes(backend: "SapUiBackend") -> int:
    """Expand all transport request/task nodes in the SE09 tree.

    Clicks the expand button next to each transport number, one at a time,
    re-querying the DOM after each click since SAP re-renders the list.
    Returns the number of nodes expanded.
    """
    expanded: set[str] = set()
    for _ in range(30):  # safety limit
        result = await backend.evaluate_javascript(f"({_JS_CLICK_NEXT_EXPAND})({json.dumps(list(expanded))})")
        if isinstance(result, str):
            result = json.loads(result)
        if not result or not result.get("remaining"):
            break
        expanded.add(result["clicked"])
        await backend.wait_for_ready()
    return len(expanded)


async def _extract_tree_text_lines(backend: "SapUiBackend") -> list[str]:
    """Extract all text content from the SE09 tree region via JS.

    Reads text from all children of the region element. Because the ABAP LIST
    control only renders visible rows, this scrolls through the list to capture
    everything.
    """
    js_extract = """() => {
        const region = document.querySelector('[role="region"]');
        if (!region) return [];
        return [...region.children]
            .filter(el => {
                const role = el.getAttribute('role');
                const text = el.textContent?.trim();
                return text || role === 'button' || role === 'img';
            })
            .map(el => ({
                role: el.getAttribute('role') || 'div',
                text: el.textContent?.trim() || '',
                id: el.id
            }));
    }"""

    all_items: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    # Extract visible content, scroll down, repeat until no new content
    for _ in range(10):  # max 10 scroll pages
        items = await backend.evaluate_javascript(f"({js_extract})()")
        if isinstance(items, str):
            items = json.loads(items)

        new_count = 0
        for item in items:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_items.append(item)
                new_count += 1

        if new_count == 0:
            break  # no new content after scrolling

        # Scroll down in the list
        await backend.press_key("PageDown")
        await backend.wait_for_ready()

    # Convert to text lines, filtering out empty/button/img entries
    return [item["text"] for item in all_items if item["text"]]


async def _lookup_transports(
    backend: "SapUiBackend",
    username: str | None,
    request_type: str,
    status: str,
    include_objects: bool = False,
) -> TransportListResult:
    """Look up transports in SE09."""
    now = datetime.now(UTC)

    # Navigate to SE09 using session-aware helper
    tx_result = await backend.enter_transaction("SE09")
    if not tx_result.success:
        return TransportListResult.failure(
            error=f"Failed to navigate to SE09: {tx_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    await backend.wait_for_ready()

    # Verify SE09 selection screen loaded (not results screen).
    # The selection screen has the "Anzeigen"/"Display" button; the results
    # screen title contains a colon ("Transport Organizer: Aufträge").
    verify_snap: AriaSnapshot = await backend.get_snapshot()
    on_selection_screen = "Transport Organizer" in verify_snap and (
        "Anzeigen" in verify_snap or "Display" in verify_snap
    )
    if not on_selection_screen:
        logger.warning("SE09 selection screen not loaded, retrying")
        await backend.enter_transaction("SE09")
        await backend.wait_for_ready()
        await backend.wait_for_ready(timeout_ms=3000)

    # Apply filters on selection screen
    if username is not None:
        await _fill_user_field(backend, username)

    await _set_request_type_filter(backend, request_type)
    await _set_status_filter(backend, status)

    # Allow SAP to process checkbox changes before clicking display
    await backend.wait_for_ready()

    # Click Anzeigen/Display button
    await _click_display_button(backend)

    # SE09 results may take a moment to render, especially with wildcard user.
    # The results screen title is "Transport Organizer: Aufträge" (DE) or
    # "Transport Organizer: Requests" (EN), while the initial screen is just
    # "Transport Organizer".
    # Poll for up to 10 seconds for the results screen to appear.
    snapshot = AriaSnapshot("")
    for attempt in range(5):
        snapshot = await backend.get_snapshot()
        if "Transport Organizer:" in snapshot:
            break
        logger.info("SE09 results not yet loaded (attempt %d), waiting 2s", attempt + 1)
        await asyncio.sleep(2)

    result = parse_se09_transport_list(snapshot)

    if not include_objects or not result.requests:
        return result

    # Expand transport nodes to reveal tasks
    request_numbers = {r.request_number for r in result.requests}
    expanded_count = await _expand_transport_nodes(backend)
    logger.info("Expanded %d transport tree nodes", expanded_count)

    # Extract all text from the expanded tree
    text_lines = await _extract_tree_text_lines(backend)

    # Map tasks to their parent requests
    _assign_tasks_from_expanded_text(result.requests, request_numbers, text_lines)

    return result


def _assign_tasks_from_expanded_text(
    requests: list[TransportRequest],
    request_numbers: set[str],
    text_lines: list[str],
) -> None:
    """Assign tasks to their parent requests from the expanded tree text.

    After expanding transport nodes, the text lines contain both requests
    and tasks interleaved. Tasks appear between their parent request and
    the next request. Any transport number NOT in ``request_numbers`` is a task.
    """
    transport_re = re.compile(r"^([A-Z0-9]{3}K\d{6})(?:\s+\d{3})?$")
    request_map = {r.request_number: r for r in requests}

    current_request = None
    i = 0
    while i < len(text_lines):
        line = text_lines[i]

        m = transport_re.match(line)
        if m:
            transport_num = m.group(1)  # 10-char transport number without client suffix
            if transport_num in request_numbers:
                # This is a request — set as current parent
                current_request = request_map.get(transport_num)
            elif current_request is not None:
                # This is a task under the current request
                owner = ""
                description = ""
                if i + 1 < len(text_lines) and not transport_re.match(text_lines[i + 1]):
                    parts = text_lines[i + 1].split(None, 1)
                    if parts:
                        owner = parts[0]
                        description = parts[1] if len(parts) > 1 else ""
                    i += 1

                current_request.tasks.append(
                    TransportTask(
                        task_number=transport_num,
                        owner=owner,
                        description=description,
                    )
                )
        i += 1


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se09_tools(mcp: FastMCP) -> None:
    """Register SE09 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up transport requests from SE09 (Transport Organizer). "
            "USE THIS instead of sap_transaction('SE09') - faster and returns structured data. "
            "Returns transport requests with owner, description, status, type, and target system. "
            "By default shows only modifiable requests for the current user. "
            "Supports filtering by username, request type (workbench/customizing), and status "
            "(modifiable/released/all)."
        ),
    )
    async def sap_se09_lookup(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        username: str | None = None,
        request_type: Literal["workbench", "customizing", "all"] = "all",
        status: Literal["modifiable", "released", "all"] = "modifiable",
        include_objects: bool = False,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TransportListResult:
        """
        Look up transport requests from SE09.

        Args:
            username: Filter by owner (default: current SAP user)
            request_type: Filter by type - "workbench", "customizing", or "all"
            status: Filter by status - "modifiable", "released", or "all" (default: "modifiable")
            include_objects: If True, expand the tree to include tasks under each request.
                This is slower (~2s per transport) but provides task details.
            output_file: If provided, write results to this JSON file (on success only).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TransportListResult with requests (and tasks if include_objects=True)
        """
        now = datetime.now(UTC)

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se09_lookup")
        except ValueError as e:
            return TransportListResult.failure(
                error=f"Session error: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        try:
            result = await _lookup_transports(
                backend=backend,
                username=username,
                request_type=request_type,
                status=status,
                include_objects=include_objects,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error looking up transports in SE09")
            return TransportListResult.failure(
                error=f"Error looking up transports: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        # Write to file if requested
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        return result
