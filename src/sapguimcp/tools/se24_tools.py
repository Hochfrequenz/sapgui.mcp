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
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.desktop._com_thread import _RPC_E_DISCONNECTED, RETRYABLE_COM_ERRORS, _get_com_error_code
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
from sapguimcp.tools.desktop_wait_predicates import (
    named_text_field_present,
    popup_closed_and_screen_changed,
    screen_changed,
    tab_table_control_loaded,
)
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


# Upper bound for waiting on a state change after F7 / Enter. A lookup whose title and status text stay unchanged (e.g.
# the same 'does not exist' message as before) must not cost more than the 3 s the former fixed waits took.
_SE24_SCREEN_WAIT_MS = 3000


async def _click_tab_bilingual(backend: DesktopBackend, de_label: str, en_label: str) -> str | None:
    """Click a tab trying DE then EN label. Returns the label that matched, or None when neither did."""
    for label in [de_label, en_label]:
        try:
            await backend.click_tab(label)
            await backend.wait_for_ready()
            return label
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    logger.warning("Tab not found: %s / %s", de_label, en_label)
    return None


# The header data of a class or interface is on its properties tab ('Eigenschaften' / 'Properties'), read by field name:
# the description and package of a class and of an interface have different names
_HEADER_TEXT_FIELDS = {
    "VSEOCLASS-DESCRIPT": "description",
    "VSEOINTERF-DESCRIPT": "description",
    "DY_0152-DEVCLASS": "package",
    "DY_0153-DEVCLASS": "package",
    "DY_0152-SUPERCLASS": "superclass",
}
_HEADER_DESCRIPTION_FIELDS = ("VSEOCLASS-DESCRIPT", "VSEOINTERF-DESCRIPT")
_HEADER_FINAL = "VSEOCLASS-CLSFINAL"  # checkbox
_HEADER_INSTANTIATION = "SEOX-CREATABLE"  # combo box: public / protected / private / abstract
# The key of 'abstract' in the instantiation combo box (private is '0'): the same in every logon language
_ABSTRACT_INSTANTIATION_KEY = "3"
_ABSTRACT_INSTANTIATION_TEXTS = ("abstrakt", "abstract")  # the text, if the key cannot be read
_TYPE_TEXT_FIELDS = (31, 32)  # GuiTextField, GuiCTextField
_TYPE_COMBO_BOX = 34
_TYPE_CHECK_BOX = 42


def _reraise_if_transient(exc: Exception) -> None:
    """Re-raise a lost connection and the errors the COM thread retries: swallowing them would return partial header
    data instead of retrying."""
    if _get_com_error_code(exc) in (_RPC_E_DISCONNECTED, *RETRYABLE_COM_ERRORS):
        raise exc


def _is_abstract_instantiation(session: Any, elem: Any) -> bool:
    """Whether the instantiation combo box says abstract: by its key, by its text if the key cannot be read."""
    try:
        return str(session.find_by_id(elem.id).key).strip() == _ABSTRACT_INSTANTIATION_KEY
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _reraise_if_transient(exc)
        logger.debug("SE24 instantiation key not readable, using the text", exc_info=True)
        return str(elem.text).strip().lower() in _ABSTRACT_INSTANTIATION_TEXTS


def _read_se24_header(session: Any, flatten_fn: Any) -> dict[str, str | bool]:
    """The header data of the class or interface from the active properties tab (COM thread), by field name.

    Keys: ``description``, ``package``, ``superclass`` (only a subclass shows it), ``is_final`` and ``is_abstract``.
    A value that cannot be read is left out and logged; the others are still read.
    """
    values: dict[str, str | bool] = {}
    try:
        wnd = session.find_by_id("wnd[0]")
        elements = list(flatten_fn(wnd.dump_tree()))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _reraise_if_transient(exc)
        logger.warning("SE24 header data could not be read from the properties tab", exc_info=True)
        return values
    for elem in elements:
        name = getattr(elem, "name", "")
        kind = getattr(elem, "type_as_number", None)
        try:
            if name in _HEADER_TEXT_FIELDS and kind in _TYPE_TEXT_FIELDS:
                values[_HEADER_TEXT_FIELDS[name]] = str(elem.text).strip()
            elif name == _HEADER_FINAL and kind == _TYPE_CHECK_BOX:
                values["is_final"] = bool(session.find_by_id(elem.id).selected)
            elif name == _HEADER_INSTANTIATION and kind == _TYPE_COMBO_BOX:
                values["is_abstract"] = _is_abstract_instantiation(session, elem)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _reraise_if_transient(exc)
            logger.warning("SE24 header field %s could not be read", name, exc_info=True)
    return values


async def _read_tab_rows(
    backend: DesktopBackend, de_label: str, en_label: str, previous_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Select a tab and read its table control (#928).

    SAP instantiates a tab page's subscreen lazily, so right after the click the table control may not exist yet
    (reads as empty) or the previous tab's rows may still be returned. Only in those cases, i.e. empty rows or
    rows identical to ``previous_rows``, wait until the clicked tab's own table control is in the tree and read
    again. A populated tab therefore costs no extra wait.
    """
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    session = backend.require_session()
    com = backend.com

    def _read_tc() -> list[dict[str, str]]:
        return read_table_control_all_rows(session, _flatten)

    label = await _click_tab_bilingual(backend, de_label, en_label)
    rows = await com.run(_read_tc)
    if label is not None and (not rows or rows == previous_rows):
        if not await backend.wait_for_condition(tab_table_control_loaded(label), timeout_ms=3000, poll_ms=250):
            logger.debug("SE24 tab %s: table control did not appear within 3 s", label)
        rows = await com.run(_read_tc)
    return rows


async def _lookup_class_desktop(  # pylint: disable=too-many-locals,too-many-statements
    backend: WebGuiBackend | DesktopBackend, class_name: str
) -> SE24Entry | SE24Error:
    """Desktop-specific SE24 lookup using tab navigation and table control reading."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)
    if not isinstance(backend, DesktopBackend):
        return SE24Error(class_name=class_name, error="Requires DesktopBackend", retrieved_at=now)
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

    # Press F7 (Display) and wait for a state change (popup, new title or new status text) instead of a fixed
    # time (#928). Enter is only needed to dismiss a language popup, so it is pressed only if one is open: after
    # a failed lookup the message disappears on Enter and nothing else changes, which would wait for nothing.
    before_title = (await backend.get_screen_info()).title or ""
    before_f7 = (await backend.get_status_bar()).message.strip()
    await backend.press_key("F7")
    await backend.wait_for_ready()
    await backend.wait_for_condition(screen_changed(before_title, before_f7), timeout_ms=_SE24_SCREEN_WAIT_MS)
    if await backend.check_popup() is not None:
        try:
            await backend.press_key("Enter")
            await backend.wait_for_ready()
            # screen_changed would already be true because of the popup itself: wait until it is gone as well.
            await backend.wait_for_condition(
                popup_closed_and_screen_changed(before_title, before_f7), timeout_ms=_SE24_SCREEN_WAIT_MS
            )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    # Check status bar for errors
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return SE24Error(class_name=class_name, error=sbar.message or "Class not found", retrieved_at=now)

    # Verify we left the initial screen (title should contain the class name)
    screen = await backend.get_screen_info()
    if class_name.upper() not in (screen.title or "").upper():
        # Always the generic text: the former unconditional Enter cleared SAP's own message ("<type> <name> does
        # not exist", which also reads wrong in German) before it was read, so callers never saw it.
        error_msg = f"Class/interface '{class_name}' not found"
        return SE24Error(class_name=class_name, error=error_msg, retrieved_at=now)

    session = backend.require_session()
    com = backend.com

    def _read_tc() -> list[dict[str, str]]:
        return read_table_control_all_rows(session, _flatten)

    # Read methods tab: try reading first (default tab), click only if table is empty.
    # SAP lazily instantiates tab subscreen controls — the table control may not
    # exist in the widget tree until the tab is explicitly activated by a click.
    methods_raw = await com.run(_read_tc)
    if not methods_raw:
        methods_raw = await _read_tab_rows(backend, "Methoden", "Methods", previous_rows=[])
    attrs_raw = await _read_tab_rows(backend, "Attribute", "Attributes", previous_rows=methods_raw)
    intfs_raw = await _read_tab_rows(backend, "Schnittstellen", "Interfaces", previous_rows=attrs_raw)

    # The header data (description, package, superclass, final, abstract) is on the properties tab. It is read last:
    # that tab has a table control of its own (type groups) that must not be taken for the methods of the class.
    await _click_tab_bilingual(backend, "Eigenschaften", "Properties")
    # SAP instantiates the subscreen lazily and idle does not prove that it is there: wait for its description field
    if not await backend.wait_for_condition(
        named_text_field_present(_HEADER_DESCRIPTION_FIELDS), timeout_ms=3000, poll_ms=250
    ):
        logger.warning("SE24 properties tab: the description field did not appear within 3 s")
    header = await com.run(lambda: _read_se24_header(session, _flatten))

    # Detect interface vs class from screen title
    # DE: "Class Builder: Interface IF_XXX anzeigen" / "Klasse CL_XXX anzeigen"
    # EN: "Class Builder: Display Interface IF_XXX" / "Display Class CL_XXX"
    title_lower = (screen.title or "").lower()
    object_type: SE24ObjectType = "interface" if "interface" in title_lower else "class"

    return SE24Entry(
        class_name=class_name.upper(),
        object_type=object_type,
        description=str(header.get("description") or ""),
        package=str(header.get("package") or ""),
        superclass=str(header.get("superclass") or "") or None,
        is_abstract=bool(header.get("is_abstract")),
        is_final=bool(header.get("is_final")),
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
            read_only_hint=True,
            open_world_hint=False,
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
