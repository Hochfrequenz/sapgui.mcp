"""
SE09 (Transport Organizer) lookup tool.

This module provides a read-only tool to list transport requests from SE09.
The tool navigates to SE09, applies filters, clicks Anzeigen (Display),
and parses the flat text list from the ARIA snapshot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.se09_parser import parse_se09_transport_list
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SE09_DISPLAY_BUTTON_DE,
    SE09_DISPLAY_BUTTON_EN,
)
from sapguimcp.models.se09_models import TransportListResult, TransportObject, TransportRequest, TransportTask
from sapguimcp.tools.screen_state_helpers import bilingual_target, ensure_screen_state

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_se09_tools"]


# =============================================================================
# SE09 Navigation Helpers
# =============================================================================


async def _click_display_button(backend: "WebGuiBackend") -> None:
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


async def _expand_transport_nodes(backend: "WebGuiBackend") -> int:
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


async def _extract_tree_text_lines(backend: "WebGuiBackend") -> list[str]:
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


async def _set_checkbox_bilingual(
    backend: "WebGuiBackend | DesktopBackend", de_label: str, en_label: str, checked: bool
) -> None:
    """Set a checkbox trying DE then EN label, warn if neither found."""
    for label in [de_label, en_label]:
        try:
            await backend.set_checkbox(label, checked)
            return
        except ValueError:
            continue
    logger.warning("SE09 desktop: checkbox not found for %s / %s", de_label, en_label)


async def _set_se09_selection_screen(
    backend: "WebGuiBackend | DesktopBackend",
    username: str | None,
    request_type: str,
    status: str,
) -> None:
    """Set SE09 selection screen fields: username, request type, and status.

    SE09 uses checkboxes (not radio buttons) for both request type and status.
    The username field is in a subscreen whose label/field names don't follow
    the standard convention, so we fill it by trying both label and technical name.
    """
    # Username field — SE09's user field is in a subscreen where label/field names
    # don't match (lblSEL_USER vs ctxtUSERNAME), so fill_field by label fails.
    # Fallback: focus_and_type with SAP technical name (uses FindByName strategy).
    if username:
        filled = False
        for label in ["Benutzer", "User"]:
            try:
                await backend.fill_field(label, username.upper())
                filled = True
                break
            except ValueError:
                continue
        if not filled:
            filled = await backend.focus_and_type("TRDYSE01CM-USERNAME", username.upper())
        if not filled:
            logger.warning("SE09 desktop: could not fill username field, results may be unfiltered")

    # Request type checkboxes
    wb_checked = request_type in ("all", "workbench")
    cust_checked = request_type in ("all", "customizing")
    await _set_checkbox_bilingual(backend, "Workbench-Auftr\u00e4ge", "Workbench Requests", wb_checked)
    await _set_checkbox_bilingual(backend, "Customizing-Auftr\u00e4ge", "Customizing Requests", cust_checked)

    # Status checkboxes
    mod_checked = status in ("all", "modifiable")
    rel_checked = status in ("all", "released")
    await _set_checkbox_bilingual(backend, "\u00c4nderbar", "Modifiable", mod_checked)
    await _set_checkbox_bilingual(backend, "Freigegeben", "Released", rel_checked)


def _parse_labels_to_requests(labels: list[str], default_owner: str) -> list[TransportRequest]:
    """Parse SE09 screen labels into TransportRequest objects.

    Labels come in groups: [transport_number, owner, description] with
    optional header/target system entries interspersed.
    """
    transport_re = re.compile(r"^[A-Z0-9]{3}K\d{6}$")
    requests: list[TransportRequest] = []
    seen: set[str] = set()
    i = 0
    while i < len(labels):
        lbl = labels[i]
        if transport_re.match(lbl) and lbl not in seen:
            seen.add(lbl)
            owner = labels[i + 1] if i + 1 < len(labels) and not transport_re.match(labels[i + 1]) else default_owner
            desc = labels[i + 2] if i + 2 < len(labels) and not transport_re.match(labels[i + 2]) else ""
            requests.append(
                TransportRequest(
                    request_number=lbl,
                    description=desc,
                    owner=owner,
                    status="",
                    request_type="",
                    target_system="",
                )
            )
        i += 1
    return requests


async def _expand_request_node_desktop(backend: "WebGuiBackend | DesktopBackend", request_number: str) -> bool:
    """Focus on a transport request label and expand it via Edit > Expand.

    Returns True if the expand was performed, False if the label wasn't found.
    """
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return False

    session = backend.require_session()
    com = backend.com

    def _focus_expand() -> bool:
        try:
            raw: Any = getattr(session, "com", getattr(session, "_com", session))
            usr = raw.FindById("wnd[0]/usr")
            for i in range(usr.Children.Count):
                child = usr.Children(i)
                if child.Type == "GuiLabel" and child.Text.strip() == request_number:
                    child.SetFocus()
                    time.sleep(0.3)
                    # Find Edit menu and Expand item by text (not hard-coded index)
                    mbar = raw.FindById("wnd[0]/mbar")
                    edit_menu = mbar.Children(1)
                    edit_menu.Select()
                    time.sleep(0.3)
                    for j in range(edit_menu.Children.Count):
                        item_text = edit_menu.Children(j).Text
                        if item_text in ("Expandieren", "Expand"):
                            edit_menu.Children(j).Select()
                            time.sleep(0.5)
                            return True
                    logger.warning("Expand menu item not found for %s", request_number)
                    return False
            return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("SE09 expand failed for %s: %s", request_number, exc)
            return False

    result = await com.run(_focus_expand)
    if result:
        await backend.wait(1000)
    return result


async def _collapse_request_node_desktop(backend: "WebGuiBackend | DesktopBackend", request_number: str) -> None:
    """Focus on a transport request label and collapse it via Edit > Compress."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return

    session = backend.require_session()
    com = backend.com

    def _focus_collapse() -> None:
        try:
            raw: Any = getattr(session, "com", getattr(session, "_com", session))
            usr = raw.FindById("wnd[0]/usr")
            for i in range(usr.Children.Count):
                child = usr.Children(i)
                if child.Type == "GuiLabel" and child.Text.strip() == request_number:
                    child.SetFocus()
                    time.sleep(0.3)
                    mbar = raw.FindById("wnd[0]/mbar")
                    edit_menu = mbar.Children(1)
                    edit_menu.Select()
                    time.sleep(0.3)
                    for j in range(edit_menu.Children.Count):
                        item_text = edit_menu.Children(j).Text
                        if item_text in ("Komprimieren", "Compress"):
                            edit_menu.Children(j).Select()
                            time.sleep(0.5)
                            return
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("SE09 collapse failed for %s: %s", request_number, exc)

    await com.run(_focus_collapse)
    await backend.wait(500)


def _parse_tasks_from_expanded_labels(
    labels: list[str], parent_request: str, known_requests: set[str]
) -> list[TransportTask]:
    """Parse tasks from labels after expanding a request node.

    After expansion, new transport numbers that are NOT in the known request
    set are tasks belonging to the parent request.
    """
    transport_re = re.compile(r"^[A-Z0-9]{3}K\d{6}$")
    tasks: list[TransportTask] = []
    i = 0
    while i < len(labels):
        lbl = labels[i]
        if transport_re.match(lbl) and lbl not in known_requests and lbl != parent_request:
            # This is a task
            task_type = ""
            if i + 1 < len(labels) and not transport_re.match(labels[i + 1]):
                task_type = labels[i + 1]
            # Collect objects from subsequent labels until next transport number
            objects: list[TransportObject] = []
            j = i + 2 if task_type else i + 1
            while j < len(labels) and not transport_re.match(labels[j]):
                obj_text = labels[j].strip()
                # Objects typically show as "PGMID OBJTYPE OBJNAME" or descriptions
                parts = obj_text.split()
                if len(parts) >= 2 and len(parts[0]) <= 4 and parts[0].isupper():
                    objects.append(
                        TransportObject(
                            pgmid=parts[0],
                            object_type=parts[1] if len(parts) > 1 else "",
                            object_name=" ".join(parts[2:]) if len(parts) > 2 else "",
                        )
                    )
                j += 1
            tasks.append(
                TransportTask(
                    task_number=lbl,
                    description="",
                    owner="",
                    status="",
                    task_type=task_type,
                    objects=objects,
                )
            )
        i += 1
    return tasks


async def _lookup_transports_desktop(  # pylint: disable=too-many-locals
    backend: "WebGuiBackend | DesktopBackend",
    username: str | None,
    request_type: str,
    status: str,
    include_objects: bool = False,
) -> TransportListResult:
    """Desktop-specific SE09 lookup using get_screen_text / label parsing."""
    now = datetime.now(UTC)
    logger.info("SE09 desktop backend path")

    tx_result = await backend.enter_transaction("SE09")
    if not tx_result.success:
        return TransportListResult.failure(
            error=f"Failed to navigate to SE09: {tx_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )
    await backend.wait_for_ready()

    # Set selection screen: username, request type, status checkboxes
    await _set_se09_selection_screen(backend, username, request_type, status)

    # Click Display button
    for label in [SE09_DISPLAY_BUTTON_DE, SE09_DISPLAY_BUTTON_EN]:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            break
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    await backend.wait(2000)

    # Parse initial screen labels to get requests
    screen_text = await backend.get_screen_text()
    requests = _parse_labels_to_requests(screen_text.labels, username or "")

    if not requests:
        return TransportListResult(
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    # If include_objects, expand each request node to find tasks
    if include_objects:
        known_request_nums = {r.request_number for r in requests}
        for req in requests:
            expanded = await _expand_request_node_desktop(backend, req.request_number)
            if expanded:
                expanded_text = await backend.get_screen_text()
                tasks = _parse_tasks_from_expanded_labels(expanded_text.labels, req.request_number, known_request_nums)
                req.tasks = tasks
                await _collapse_request_node_desktop(backend, req.request_number)

    return TransportListResult(
        requests=requests,
        request_count=len(requests),
        retrieved_at=now,
    )


async def _lookup_transports(  # pylint: disable=too-many-locals
    backend: "WebGuiBackend | DesktopBackend",
    username: str | None,
    request_type: str,
    status: str,
    include_objects: bool = False,
) -> TransportListResult:
    """Look up transports in SE09."""
    now = datetime.now(UTC)

    # Desktop backend: use label parsing instead of ARIA snapshot parsing
    if backend.backend_type == "desktop":
        return await _lookup_transports_desktop(backend, username, request_type, status, include_objects)

    from sapguimcp.backend.webgui.backend import WebGuiBackend as _WG  # pylint: disable=import-outside-toplevel

    assert isinstance(backend, _WG)

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
    verify_snap = await backend.get_snapshot()
    on_selection_screen = "Transport Organizer" in verify_snap and (
        "Anzeigen" in verify_snap or "Display" in verify_snap
    )
    if not on_selection_screen:
        logger.warning("SE09 selection screen not loaded, retrying")
        await backend.enter_transaction("SE09")
        await backend.wait_for_ready()
        await backend.wait_for_ready(timeout_ms=3000)

    # Build target state for selection screen
    target = bilingual_target(
        checkboxes_de={
            "Workbench-Aufträge": request_type in ("all", "workbench"),
            "Customizing-Aufträge": request_type in ("all", "customizing"),
            "Änderbar": status in ("all", "modifiable"),
            "Freigegeben": status in ("all", "released"),
        },
        checkboxes_en={
            "Workbench Requests": request_type in ("all", "workbench"),
            "Customizing Requests": request_type in ("all", "customizing"),
            "Modifiable": status in ("all", "modifiable"),
            "Released": status in ("all", "released"),
        },
        fields_de={"Benutzer": username.upper()} if username else {},
        fields_en={"User": username.upper()} if username else {},
    )
    state_result = await ensure_screen_state(backend, target)
    if not state_result.success:
        return TransportListResult.failure(
            error=f"Failed to set SE09 selection screen: {state_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    # Click Anzeigen/Display button
    await _click_display_button(backend)

    # SE09 results may take a moment to render, especially with wildcard user.
    # The results screen title is "Transport Organizer: Aufträge" (DE) or
    # "Transport Organizer: Requests" (EN), while the initial screen is just
    # "Transport Organizer".
    # Poll for up to 10 seconds for the results screen to appear.
    snapshot = AriaSnapshot("")
    for attempt in range(5):
        snapshot = AriaSnapshot(await backend.get_snapshot())
        if "Transport Organizer:" in str(snapshot):
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
            "If sap-adt is available, prefer its get_transport_requests for listing transports. "
            "USE THIS for transport release on ECC (ADT release silently fails on ECC) or when ADT is unavailable. "
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
