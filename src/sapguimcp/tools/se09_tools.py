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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp import lang
from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.js_helpers import script_arg
from sapguimcp.backend.webgui.parsers.se09_parser import parse_se09_transport_list
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang.schema import LanguagePack, TransportStatus
from sapguimcp.models.screen_state import SelectionScreenState
from sapguimcp.models.se09_models import TransportListResult, TransportObject, TransportRequest, TransportTask
from sapguimcp.tools.desktop_wait_predicates import screen_changed, usr_child_count_changed
from sapguimcp.tools.screen_state_helpers import ensure_screen_state
from sapguimcp.utils import resolve_output_file_path, write_json_output_file

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend
    from sapguimcp.lang.text import Text


logger = logging.getLogger(__name__)

__all__ = ["register_se09_tools"]


# =============================================================================
# SE09 Navigation Helpers
# =============================================================================


async def _click_display_button(backend: "WebGuiBackend", t: LanguagePack) -> None:
    """Click the Display button to execute the search.

    Uses JS to click the button by its element ID, which is more reliable
    than Playwright's click() for SAP WebGUI custom button controls.
    """
    # Find the Display button by text and click it via JS,
    # dispatching a proper mousedown+mouseup+click sequence
    js_click_display = """({texts}) => {
        const display = new RegExp('^(?:' + texts.display.source + ')$', texts.display.flags);
        const buttons = document.querySelectorAll('[role="button"]');
        for (const btn of buttons) {
            const text = btn.textContent?.trim() || '';
            if (display.test(text)) {
                // SAP WebGUI needs mousedown+mouseup for proper event handling
                btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
                btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                return {clicked: text, id: btn.id};
            }
        }
        return {clicked: null};
    }"""
    result = await backend.evaluate_javascript(js_click_display, script_arg({"display": t.se09.display_button}))
    if isinstance(result, str):
        result = json.loads(result)
    if result and result.get("clicked"):
        logger.info("Clicked display button '%s' (id=%s)", result["clicked"], result.get("id"))
        await backend.wait_for_ready()
        return

    # Fallback: try Playwright click
    for label in t.se09.display_button:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            return
        except ValueError:
            continue

    logger.warning("Display button not found")


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


async def _set_checkbox_by_labels(backend: "WebGuiBackend | DesktopBackend", labels: Text, checked: bool) -> None:
    """Set a checkbox trying each label variant in turn, warn if none is found."""
    for label in labels:
        try:
            await backend.set_checkbox(label, checked)
            return
        except ValueError:
            continue
    logger.warning("SE09 desktop: checkbox not found for %s", " / ".join(labels))


async def _set_se09_selection_screen(
    backend: "WebGuiBackend | DesktopBackend",
    t: LanguagePack,
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
        for label in t.common.user:
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
    wb_checked = request_type in ("all", "workbench")  # lang-ok: tool parameter values
    cust_checked = request_type in ("all", "customizing")  # lang-ok: tool parameter values
    await _set_checkbox_by_labels(backend, t.se09.workbench_requests, wb_checked)
    await _set_checkbox_by_labels(backend, t.se09.customizing_requests, cust_checked)

    # Status checkboxes
    mod_checked = status in ("all", "modifiable")  # lang-ok: tool parameter values
    rel_checked = status in ("all", "released")  # lang-ok: tool parameter values
    await _set_checkbox_by_labels(backend, t.se09.status[TransportStatus.MODIFIABLE], mod_checked)
    await _set_checkbox_by_labels(backend, t.se09.status[TransportStatus.RELEASED], rel_checked)


# A SAP user name: up to 12 upper-case letters, digits and a few symbols (the built-in user is SAP*), no blanks. A
# transport description that is a single such word cannot be told apart from an owner (the owner is only printed when
# it changes, see below).
_OWNER_LABEL = re.compile(r"^[A-Z0-9][A-Z0-9_$#.&*-]{0,11}$")


def _parse_labels_to_requests(labels: list[str], default_owner: str) -> list[TransportRequest]:
    """Parse SE09 screen labels into TransportRequest objects.

    Labels come in groups: ``[transport_number, owner?, description?]`` with optional header/target system entries
    interspersed. SE09 prints the owner only when it differs from the request before (the first request always shows
    it), so a label after the number is the owner only if it looks like a user name and a description follows it;
    otherwise the owner is the one of the previous request and the label is the description.
    """
    transport_re = re.compile(r"^[A-Z0-9]{3}K\d{6}$")
    requests: list[TransportRequest] = []
    seen: set[str] = set()
    current_owner = default_owner
    i = 0
    while i < len(labels):
        lbl = labels[i]
        if transport_re.match(lbl) and lbl not in seen:
            seen.add(lbl)
            after = [
                labels[j] if j < len(labels) and not transport_re.match(labels[j]) else None for j in (i + 1, i + 2)
            ]
            # An owner is followed by the description, so a user-like label that is the last one of the request is
            # a one-word description (except on the first request, which always prints its owner).
            if after[0] is not None and _OWNER_LABEL.match(after[0]) and (after[1] is not None or not requests):
                current_owner = after[0]
                desc = after[1] or ""
            else:
                desc = after[0] or ""
            requests.append(
                TransportRequest(
                    request_number=lbl,
                    description=desc,
                    owner=current_owner,
                    status="",
                    request_type="",
                    target_system="",
                )
            )
        i += 1
    return requests


_SE09_EDIT_MENU_INDEX = 1  # the Edit menu of the menu bar


def _select_edit_menu_item_for_label(
    session: Any, request_number: str, item_names: tuple[str, ...]
) -> tuple[bool, int]:
    """Focus the SE09 list label ``request_number`` and select an item of the Edit menu. Runs on the COM thread.

    Reads the ``usr`` and menu bar trees with one ``dump_tree()`` call each and then addresses the label and menu
    items by id: scanning the children one by one costs two COM calls per element, which made every request
    slower the further down the list it was (#928).

    Returns ``(performed, child_count_before)``; ``child_count_before`` is the number of direct ``usr`` children
    before the action, for the readiness predicate.
    """
    from sapguimcp.backend.desktop._element_finder import (  # pylint: disable=import-outside-toplevel
        _TYPE_LABEL,
        _flatten,
    )

    usr_tree = session.find_by_id("wnd[0]/usr").dump_tree()
    before_count = len(usr_tree)
    # Direct children of usr only, as the raw-COM scan did before.
    label = next((e for e in usr_tree if e.type_as_number == _TYPE_LABEL and e.text.strip() == request_number), None)
    if label is None:
        return False, before_count
    session.find_by_id(label.id).set_focus()
    # Find the Edit menu item by text (not by index): the item names differ per logon language.
    menus = session.find_by_id("wnd[0]/mbar").dump_tree()
    edit_menu = menus[_SE09_EDIT_MENU_INDEX]
    item = next((e for e in _flatten(edit_menu.children) if e.text in item_names), None)
    if item is None:
        logger.warning("SE09 menu item %s not found for %s", item_names, request_number)
        return False, before_count
    session.find_by_id(edit_menu.id).select()
    # COM calls are synchronous: no pauses needed between focus, menu and item.
    session.find_by_id(item.id).select()
    return True, before_count


_SE09_TREE_WAIT_MS = 2000


async def _wait_for_usr_tree_change(backend: "DesktopBackend", before_count: int, request_number: str) -> None:
    """Wait (bounded) until the number of usr children differs from ``before_count``; log if it never does."""
    changed = await backend.wait_for_condition(
        usr_child_count_changed(before_count), timeout_ms=_SE09_TREE_WAIT_MS, poll_ms=50
    )
    if not changed:
        logger.debug("SE09 list did not change within %d ms after the action on %s", _SE09_TREE_WAIT_MS, request_number)


async def _expand_request_node_desktop(
    backend: "WebGuiBackend | DesktopBackend", request_number: str, t: LanguagePack
) -> bool:
    """Focus on a transport request label and expand it via Edit > Expand.

    Returns True if the expand was performed, False if the label wasn't found.
    """
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return False

    session = backend.require_session()
    before_count = -1

    def _focus_expand() -> bool:
        nonlocal before_count
        try:
            performed, before_count = _select_edit_menu_item_for_label(session, request_number, tuple(t.se09.expand))
            return performed
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("SE09 expand failed for %s: %s", request_number, exc)
            return False

    result = await backend.com.run(_focus_expand)
    if result:
        await backend.wait_for_ready()
        # The caller reads the task labels next: wait until the expanded node's labels are in the tree.
        await _wait_for_usr_tree_change(backend, before_count, request_number)
    return result


async def _collapse_request_node_desktop(
    backend: "WebGuiBackend | DesktopBackend", request_number: str, t: LanguagePack
) -> None:
    """Focus on a transport request label and collapse it via Edit > Compress."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return

    session = backend.require_session()
    before_count = -1

    def _focus_collapse() -> bool:
        nonlocal before_count
        try:
            performed, before_count = _select_edit_menu_item_for_label(session, request_number, tuple(t.se09.compress))
            return performed
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("SE09 collapse failed for %s: %s", request_number, exc)
            return False

    collapsed = await backend.com.run(_focus_collapse)
    await backend.wait_for_ready()
    if collapsed:
        # The next request's label is looked up by text: wait until the collapsed node's labels are gone.
        await _wait_for_usr_tree_change(backend, before_count, request_number)


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
    t: LanguagePack,
    username: str | None,
    request_type: str,
    status: str,
    include_objects: bool = False,
) -> TransportListResult:
    """Desktop-specific SE09 lookup using get_screen_text / label parsing."""
    now = datetime.now(UTC)
    logger.info("SE09 desktop backend path")
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return TransportListResult.failure(
            error="Requires DesktopBackend", requests=[], request_count=0, retrieved_at=now
        )

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
    await _set_se09_selection_screen(backend, t, username, request_type, status)

    # Click Display button
    before_title = (await backend.get_screen_info()).title or ""
    before_status = (await backend.get_status_bar()).message.strip()
    for label in t.se09.display_button:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            break
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    # The next step reads the list's labels: wait for the list screen (or an error/empty-result status text).
    await backend.wait_for_condition(screen_changed(before_title, before_status), timeout_ms=5000)

    # Parse initial screen labels to get requests
    # Every label, in order: the owner is only printed when it changes, so a repeated owner or description must stay
    screen_text = await backend.get_screen_text(keep_duplicate_labels=True)
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
            expanded = await _expand_request_node_desktop(backend, req.request_number, t)
            if expanded:
                expanded_text = await backend.get_screen_text(keep_duplicate_labels=True)
                tasks = _parse_tasks_from_expanded_labels(expanded_text.labels, req.request_number, known_request_nums)
                req.tasks = tasks
                await _collapse_request_node_desktop(backend, req.request_number, t)

    return TransportListResult(
        requests=requests,
        request_count=len(requests),
        retrieved_at=now,
    )


async def _lookup_transports(  # pylint: disable=too-many-locals
    backend: "WebGuiBackend | DesktopBackend",
    t: LanguagePack,
    username: str | None,
    request_type: str,
    status: str,
    include_objects: bool = False,
) -> TransportListResult:
    """Look up transports in SE09."""
    now = datetime.now(UTC)

    # Desktop backend: use label parsing instead of ARIA snapshot parsing
    if backend.backend_type == "desktop":
        return await _lookup_transports_desktop(backend, t, username, request_type, status, include_objects)

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
    # The selection screen has the Display button; the results
    # screen title contains a colon ("Transport Organizer: ...").
    verify_snap = await backend.get_snapshot()
    on_selection_screen = t.se09.organizer_title.contains(verify_snap) and t.se09.display_button.contains(verify_snap)
    if not on_selection_screen:
        logger.warning("SE09 selection screen not loaded, retrying")
        await backend.enter_transaction("SE09")
        await backend.wait_for_ready()
        await backend.wait_for_ready(timeout_ms=3000)

    # Build target state for selection screen
    wb_checked = request_type in ("all", "workbench")  # lang-ok: tool parameter values
    cust_checked = request_type in ("all", "customizing")  # lang-ok: tool parameter values
    mod_checked = status in ("all", "modifiable")  # lang-ok: tool parameter values
    rel_checked = status in ("all", "released")  # lang-ok: tool parameter values
    target = SelectionScreenState(
        checkboxes={
            **dict.fromkeys(t.se09.workbench_requests, wb_checked),
            **dict.fromkeys(t.se09.customizing_requests, cust_checked),
            **dict.fromkeys(t.se09.status[TransportStatus.MODIFIABLE], mod_checked),
            **dict.fromkeys(t.se09.status[TransportStatus.RELEASED], rel_checked),
        },
        fields=dict.fromkeys(t.common.user, username.upper()) if username else {},
    )
    state_result = await ensure_screen_state(backend, target)
    if not state_result.success:
        return TransportListResult.failure(
            error=f"Failed to set SE09 selection screen: {state_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    # Click the Display button
    await _click_display_button(backend, t)

    # SE09 results may take a moment to render, especially with wildcard user.
    # The results screen title is "Transport Organizer: Aufträge" (DE) or
    # "Transport Organizer: Requests" (EN), while the initial screen is just
    # "Transport Organizer".
    # Poll for up to 10 seconds for the results screen to appear.
    snapshot = AriaSnapshot("")
    for attempt in range(5):
        snapshot = AriaSnapshot(await backend.get_snapshot())
        if any(f"{title}:" in str(snapshot) for title in t.se09.organizer_title):
            break
        logger.info("SE09 results not yet loaded (attempt %d), waiting 2s", attempt + 1)
        await asyncio.sleep(2)

    result = parse_se09_transport_list(snapshot, t)

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
            read_only_hint=True,
            open_world_hint=False,
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
        request_type: Literal["workbench", "customizing", "all"] = "all",  # lang-ok: tool parameter values
        status: Literal["modifiable", "released", "all"] = "modifiable",  # lang-ok: tool parameter values
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
            output_file: If provided, write results to this JSON file within the
                configured output directory (OUTPUT_DIR, default: current working
                directory) (on success only).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TransportListResult with requests (and tasks if include_objects=True)
        """
        now = datetime.now(UTC)

        if output_file:
            try:
                output_path = resolve_output_file_path(output_file)
            except ValueError as e:
                return TransportListResult.failure(
                    error=str(e),
                    requests=[],
                    request_count=0,
                    retrieved_at=now,
                )
        else:
            output_path = None

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se09_lookup")
        except ValueError as e:
            return TransportListResult.failure(
                error=f"Session error: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        # Resolved outside the try: an unsupported session language must reach the caller, not become a failure result.
        t = lang.current("sap_se09_lookup")

        try:
            result = await _lookup_transports(
                backend=backend,
                t=t,
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
        if output_file and output_path and result.success:
            try:
                write_json_output_file(output_file, result.model_dump(mode="json"))
            except (ValueError, OSError) as e:
                failure_payload = result.model_dump(mode="python")
                failure_payload["success"] = False
                failure_payload["error"] = str(e)
                return TransportListResult(**failure_payload)

        return result
