"""
SE24 (Class Builder) lookup tool.

This module provides a tool to look up class/interface metadata from SE24,
returning strongly-typed Pydantic models with method and attribute details.
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
from sapguimcp.backend.webgui.parsers.se24_parser import SE24TabSnapshots, parse_se24_snapshot
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.models import (
    SE24Entry,
    SE24Error,
    SE24FileSummary,
    SE24Result,
)
from sapguimcp.models.se24_models import SE24Attribute, SE24Method, SE24ObjectType, SE24Visibility
from sapguimcp.tools.field_helpers import fill_and_display
from sapguimcp.tools.table_helpers import read_table_control_all_rows

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_se24_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 5


# =============================================================================
# SE24 Navigation Helpers
# =============================================================================


# DE/EN label variants for the class/interface input field.
_CLASS_FIELD_LABELS = [
    "Objekttyp",
    "Object type",
    "Object Type",
    "Klasse/Interface",
    "Class/Interface",
]


def _parse_visibility(raw: str) -> SE24Visibility:
    """Parse visibility string to typed literal."""
    lower = raw.lower()
    if "protected" in lower:
        return "protected"
    if "private" in lower:
        return "private"
    return "public"


def _parse_methods(rows: list[dict[str, str]]) -> list[SE24Method]:
    """Parse methods table rows into SE24Method models."""
    methods: list[SE24Method] = []
    for row in rows:
        name = row.get("Methode", row.get("Method", ""))
        if not name:
            continue
        kind = row.get("Art", row.get("Level", "")).lower()
        methods.append(
            SE24Method(
                name=name,
                visibility=_parse_visibility(row.get("Sichtbarkeit", row.get("Visibility", ""))),
                is_static="static" in kind,
                description=row.get("Beschreibung", row.get("Description", "")),
            )
        )
    return methods


def _parse_attributes(rows: list[dict[str, str]]) -> list[SE24Attribute]:
    """Parse attributes table rows into SE24Attribute models."""
    attributes: list[SE24Attribute] = []
    for row in rows:
        name = row.get("Attribut", row.get("Attribute", ""))
        if not name:
            continue
        kind = row.get("Art", row.get("Level", "")).lower()
        attributes.append(
            SE24Attribute(
                name=name,
                visibility=_parse_visibility(row.get("Sichtbarkeit", row.get("Visibility", ""))),
                is_static="static" in kind,
                is_constant="constant" in kind or "konstante" in kind,
                type_ref=row.get("Bezugstyp", row.get("Assoc.Type", "")),
                default_value=row.get("Initialer Wert", row.get("Initial Value", None)) or None,
                description=row.get("Beschreibung", row.get("Description", "")),
            )
        )
    return attributes


async def _click_tab_bilingual(backend: WebGuiBackend | DesktopBackend, de_label: str, en_label: str) -> None:
    """Click a tab trying DE then EN label."""
    for label in [de_label, en_label]:
        try:
            await backend.click_tab(label)
            await backend.wait(500)
            return
        except Exception:  # pylint: disable=broad-exception-caught
            continue


async def _lookup_class_desktop(  # pylint: disable=too-many-locals,too-many-statements
    backend: WebGuiBackend | DesktopBackend, class_name: str
) -> SE24Entry | SE24Error:
    """Desktop-specific SE24 lookup using tab navigation and table control reading."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)
    await backend.wait_for_ready()

    # Fill class name field
    filled = False
    for label in _CLASS_FIELD_LABELS:
        try:
            await backend.fill_field(label, class_name.upper())
            filled = True
            break
        except ValueError:
            continue
    if not filled:
        filled = await backend.focus_and_type("SEOCLASS-CLSNAME", class_name.upper())
    if not filled:
        return SE24Error(class_name=class_name, error="Could not fill class name field", retrieved_at=now)

    # Press F7 (Display), then Enter to dismiss any language popup
    await backend.press_key("F7")
    await backend.wait(2000)
    try:
        await backend.press_key("Enter")
        await backend.wait(1000)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Check status bar for errors
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return SE24Error(class_name=class_name, error=sbar.message or "Class not found", retrieved_at=now)

    # Verify we left the initial screen (title should contain the class name)
    screen = await backend.get_screen_info()
    if class_name.upper() not in (screen.title or "").upper():
        error_msg = sbar.message or f"Class/interface '{class_name}' not found"
        return SE24Error(class_name=class_name, error=error_msg, retrieved_at=now)

    if not isinstance(backend, DesktopBackend):
        return SE24Error(class_name=class_name, error="Requires DesktopBackend", retrieved_at=now)

    session = backend.require_session()
    com = backend.com

    def _read_tc() -> list[dict[str, str]]:
        return read_table_control_all_rows(session, _flatten)

    # Read methods tab: try reading first (default tab), click only if table is empty.
    # SAP lazily instantiates tab subscreen controls — the table control may not
    # exist in the widget tree until the tab is explicitly activated by a click.
    methods_raw = await com.run(_read_tc)
    if not methods_raw:
        await _click_tab_bilingual(backend, "Methoden", "Methods")
        methods_raw = await com.run(_read_tc)
    await _click_tab_bilingual(backend, "Attribute", "Attributes")
    attrs_raw = await com.run(_read_tc)
    await _click_tab_bilingual(backend, "Schnittstellen", "Interfaces")
    intfs_raw = await com.run(_read_tc)

    # Read description from screen fields and detect object type from title
    fields = await backend.discover_fields()
    description = ""
    for f in fields:
        if f.name and "DESCRIPT" in f.name.upper():
            description = f.value or ""
            break

    # Detect interface vs class from screen title
    # DE: "Class Builder: Interface IF_XXX anzeigen" / "Klasse CL_XXX anzeigen"
    # EN: "Class Builder: Display Interface IF_XXX" / "Display Class CL_XXX"
    title_lower = (screen.title or "").lower()
    object_type: SE24ObjectType = "interface" if "interface" in title_lower else "class"

    return SE24Entry(
        class_name=class_name.upper(),
        object_type=object_type,
        description=description,
        methods=_parse_methods(methods_raw),
        attributes=_parse_attributes(attrs_raw),
        interfaces=[row.get("Interface", "") for row in intfs_raw if row.get("Interface")],
        retrieved_at=now,
    )


async def _capture_tab_snapshot(backend: WebGuiBackend | DesktopBackend, tab_name: str) -> str | None:
    """Click a tab and capture its snapshot. Returns snapshot or None.

    After clicking, verifies the tab is actually ``[selected]`` in the ARIA
    snapshot.  SAP WebGUI sometimes needs an extra ``wait_for_ready`` before
    the tab content is rendered.
    """
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
            await backend.wait_for_ready()
            snapshot = str(await backend.get_snapshot())
            # Verify the tab actually switched by checking [selected] marker
            if f'tab "{name}" [selected]' in snapshot:
                return snapshot
            logger.warning("Tab '%s' clicked but not selected in snapshot, retrying", name)
            # Retry once — SAP may need a moment
            await backend.click_tab(name)
            await backend.wait_for_ready()
            snapshot = str(await backend.get_snapshot())
            if f'tab "{name}" [selected]' in snapshot:
                return snapshot
            logger.warning("Tab '%s' still not selected after retry", name)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Tab '%s' click failed, trying next variant", name, exc_info=True)
            continue

    logger.warning("Could not activate tab '%s' with any label variant", tab_name)
    return None


async def _fill_and_display(backend: WebGuiBackend | DesktopBackend, class_name: str) -> SE24Error | None:
    """Fill the class field and press F7 (Display). Returns error or None.

    Delegates to the shared ``fill_and_display`` helper which uses real
    keyboard events and polls for page navigation.
    """
    error_msg = await fill_and_display(backend, _CLASS_FIELD_LABELS, class_name, tcode_label="class/interface")
    if error_msg:
        return SE24Error(
            class_name=class_name,
            error=error_msg,
            retrieved_at=datetime.now(UTC),
        )
    return None


async def _lookup_class_on_initial_screen(
    backend: WebGuiBackend | DesktopBackend, class_name: str
) -> SE24Entry | SE24Error:
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
    main_snapshot = AriaSnapshot(await backend.get_snapshot())
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


async def _lookup_batch_se24_webgui(backend: WebGuiBackend | DesktopBackend, class_list: list[str]) -> SE24Result:
    """Run SE24 lookups for a batch of classes on the WebGUI backend."""
    entries: list[SE24Entry] = []
    errors: list[SE24Error] = []

    for class_name in class_list:
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
                    class_name=class_name, error=f"Error looking up '{class_name}': {e}", retrieved_at=datetime.now(UTC)
                )
            )

    if entries:
        return SE24Result(entries=entries, errors=errors)
    return SE24Result.failure(error=f"All {len(errors)} lookups failed", entries=[], errors=errors)


async def _lookup_batch_se24_desktop(backend: WebGuiBackend | DesktopBackend, class_list: list[str]) -> SE24Result:
    """Run SE24 lookups for a batch of classes on the desktop backend."""
    entries: list[SE24Entry] = []
    errors: list[SE24Error] = []

    for class_name in class_list:
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
            result = await _lookup_class_desktop(backend, class_name)
            if isinstance(result, SE24Entry):
                entries.append(result)
            else:
                errors.append(result)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("SE24 desktop lookup failed", extra={"class_name": class_name})
            errors.append(SE24Error(class_name=class_name, error=f"Error: {e}", retrieved_at=datetime.now(UTC)))

    if entries:
        return SE24Result(entries=entries, errors=errors)
    return SE24Result.failure(error=f"All {len(errors)} lookups failed", entries=[], errors=errors)


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
            "If sap-adt is available, prefer its get_source/get_class_definition tools. "
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

        # Route to desktop or WebGUI batch lookup
        if backend.backend_type == "desktop":
            final_result = await _lookup_batch_se24_desktop(backend, class_list)
        else:
            final_result = await _lookup_batch_se24_webgui(backend, class_list)

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
                successful=len(final_result.entries),
                failed=len(final_result.errors),
                sample_entries=[e.class_name for e in final_result.entries[:5]],
                sample_errors=[e.class_name for e in final_result.errors[:5]],
            )

        if len(class_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning classes inline - consider using output_file parameter",
                extra={"count": len(class_list)},
            )

        return final_result
