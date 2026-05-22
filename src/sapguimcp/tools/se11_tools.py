"""
SE11 (ABAP Dictionary) lookup tool for tables and structures.

This module provides a fast, single-call tool to retrieve table/structure
metadata from SE11, returning strongly-typed Pydantic models.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.lang import (
    SE11_DATA_TYPE_DE,
    SE11_DATA_TYPE_EN,
    SE11_DATABASE_TABLE_DE,
    SE11_DATABASE_TABLE_EN,
    SE11_DICTIONARY_TYPE_DE,
    SE11_DICTIONARY_TYPE_EN,
    SE11_DISPLAY_BUTTON_DE,
    SE11_DISPLAY_BUTTON_EN,
    SE11_NOT_EXIST_DE,
    SE11_NOT_EXIST_EN,
    SE11_NOT_FOUND_DE,
    SE11_NOT_FOUND_EN,
    SE11_ROW_SELECT_FULL_DE,
    SE11_ROW_SELECT_FULL_EN,
    SE11_ROW_SELECT_PREFIX_DE,
    SE11_ROW_SELECT_PREFIX_EN,
    SE11_SHORT_DESC_DE,
    SE11_SHORT_DESC_EN,
    SE11_STRUCTURE_DE,
    SE11_STRUCTURE_EN,
    SE11_TABLE_NAME_DE,
    SE11_TABLE_NAME_EN,
    SE11_TRANSPARENT_TABLE_DE,
    SE11_TRANSPARENT_TABLE_EN,
    bilingual_pattern,
)
from sapguimcp.models import (
    SE11Entry,
    SE11Error,
    SE11Field,
    SE11FileSummary,
    SE11ObjectType,
    SE11Result,
)
from sapguimcp.tools.field_helpers import fill_field_with_keyboard
from sapguimcp.tools.screen_state_helpers import bilingual_target, ensure_screen_state
from sapguimcp.tools.table_helpers import read_table_control_all_rows

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 10

# Regex patterns for parsing - compiled once for efficiency
# Uses explicit constants: SE11_ROW_SELECT_PREFIX_DE, SE11_ROW_SELECT_PREFIX_EN
_ROW_SPLIT_PATTERN = re.compile(
    rf'(?=- row "{bilingual_pattern(SE11_ROW_SELECT_PREFIX_DE, SE11_ROW_SELECT_PREFIX_EN)})'
)
# Uses explicit constants: SE11_ROW_SELECT_FULL_DE, SE11_ROW_SELECT_FULL_EN (regex patterns)
_ROW_SELECT_FULL = bilingual_pattern(SE11_ROW_SELECT_FULL_DE, SE11_ROW_SELECT_FULL_EN, escape=False)
_FIELD_NAME_PATTERN = re.compile(rf'row "{_ROW_SELECT_FULL}\s+(?P<field_name>[A-Z_0-9/]+)')
_ROW_DATA_PATTERN = re.compile(
    rf'row "{_ROW_SELECT_FULL}\s+(?P<row_data>[^"]+)"',
    re.MULTILINE,
)


# =============================================================================
# YAML Parsing Functions
# =============================================================================


def _parse_se11_yaml(yaml_content: str, object_type: SE11ObjectType) -> SE11Entry | SE11Error:
    """
    Parse SE11 display YAML snapshot into structured data.

    Args:
        yaml_content: The YAML accessibility snapshot from browser_snapshot
        object_type: Whether this is a 'table' or 'structure'

    Returns:
        SE11Entry on success, SE11Error on parse failure
    """
    now = datetime.now(UTC)

    # Extract table/structure name
    # Uses explicit constants: SE11_TRANSPARENT_TABLE_DE/EN, SE11_STRUCTURE_DE/EN
    de_pattern = bilingual_pattern(SE11_TRANSPARENT_TABLE_DE, SE11_STRUCTURE_DE)
    en_pattern = bilingual_pattern(SE11_TRANSPARENT_TABLE_EN, SE11_STRUCTURE_EN)
    name_match = re.search(rf'textbox "{de_pattern}":\s*(?P<name>\S+)', yaml_content)
    if not name_match:
        name_match = re.search(rf'textbox "{en_pattern}":\s*(?P<name>\S+)', yaml_content)

    if not name_match:
        return SE11Error(
            name="UNKNOWN",
            object_type=object_type,
            error="Object not found - SE11 did not display table/structure details",
            retrieved_at=now,
        )

    name = name_match.group("name").strip()

    # Extract description
    # Uses explicit constants: SE11_SHORT_DESC_DE, SE11_SHORT_DESC_EN
    desc_match = re.search(
        rf'textbox "{bilingual_pattern(SE11_SHORT_DESC_DE, SE11_SHORT_DESC_EN)}":\s*(?P<description>.+?)(?:\n|$)',
        yaml_content,
    )
    description = desc_match.group("description").strip() if desc_match else ""

    # Parse fields from the grid
    fields = _parse_se11_fields(yaml_content)

    if not fields:
        return SE11Error(
            name=name,
            object_type=object_type,
            error="Could not parse fields from SE11 screen - grid not found or empty",
            retrieved_at=now,
        )

    return SE11Entry(
        name=name,
        description=description,
        object_type=object_type,
        fields=fields,
        retrieved_at=now,
    )


def _find_key_fields(yaml_content: str) -> set[str]:
    """Find which fields are marked as key fields in the SE11 grid."""
    key_fields: set[str] = set()
    row_blocks = _ROW_SPLIT_PATTERN.split(yaml_content)

    for block in row_blocks:
        if not block.strip():
            continue

        row_match = _FIELD_NAME_PATTERN.search(block)
        if not row_match:
            continue

        field_name = row_match.group("field_name")

        # Key checkbox pattern: after field name gridcell, next gridcell has [checked] checkbox
        key_pattern = re.compile(
            r'gridcell "' + re.escape(field_name) + r'":\s*\n'
            r"\s*- textbox\s*\n"
            r"\s*- gridcell[^:]*:\s*\n"
            r"\s*- checkbox[^\n]*\[checked\]",
        )

        if key_pattern.search(block):
            key_fields.add(field_name)

    return key_fields


def _parse_field_row(parts: list[str], key_fields: set[str]) -> SE11Field | None:
    """Parse a single field row into an SE11Field, or None if parsing fails."""
    if len(parts) < 7:
        return None

    field_name = parts[0]

    # Find the data type by looking for a 2-10 char uppercase string
    datatype = None
    datatype_idx = -1
    for i, part in enumerate(parts[1:], 1):
        if re.match(r"^[A-Z][A-Z0-9]{1,9}$", part) and not part.isdigit():
            if datatype is None or len(part) < len(datatype):
                datatype = part
                datatype_idx = i

    if datatype is None or datatype_idx < 2:
        return None

    try:
        length = int(parts[datatype_idx + 1])
        decimals_raw = int(parts[datatype_idx + 2])
        decimals = decimals_raw if decimals_raw > 0 else None
        description = " ".join(parts[datatype_idx + 4 :]).strip()
    except (IndexError, ValueError):
        return None

    return SE11Field(
        name=field_name,
        datatype=datatype,
        length=length,
        decimals=decimals,
        description=description,
        is_key=field_name in key_fields,
    )


def _parse_se11_fields(yaml_content: str) -> list[SE11Field]:
    """Parse field rows from SE11 grid."""
    key_fields = _find_key_fields(yaml_content)
    fields: list[SE11Field] = []

    for match in _ROW_DATA_PATTERN.finditer(yaml_content):
        row_data = match.group("row_data")

        # Filter out checkbox Unicode chars (Private Use Area U+E000-U+F8FF)
        parts = [p for p in row_data.split() if p and not (len(p) == 1 and ord(p) >= 0xE000)]

        field = _parse_field_row(parts, key_fields)
        if field:
            fields.append(field)

    return fields


# =============================================================================
# SE11 Navigation Helpers
# =============================================================================


async def _wait_for_se11_table_screen(backend: WebGuiBackend | DesktopBackend, name: str) -> SE11Error | None:
    """Wait for SE11 table screen and select the table radio. Returns error or None."""
    now = datetime.now(UTC)

    # Wait for the screen to load by checking snapshot for radio presence
    for _ in range(20):  # 20 * 500ms = 10s max
        snapshot = await backend.get_snapshot()
        if "Datenbanktabelle" in snapshot or "Database table" in snapshot:
            break
        await asyncio.sleep(0.5)
    else:
        return SE11Error(
            name=name,
            object_type="table",
            error=(
                "SE11 screen did not load. "
                "Could not find 'Database table' / 'Datenbanktabelle' radio button. "
                "This tool currently supports German (DE) and English (EN) SAP languages."
            ),
            retrieved_at=now,
        )

    # Select the table radio via ensure_screen_state (with verification)
    target = bilingual_target(
        radios_de={SE11_DATABASE_TABLE_DE: True},
        radios_en={SE11_DATABASE_TABLE_EN: True},
    )
    result = await ensure_screen_state(backend, target)
    if not result.success:
        return SE11Error(
            name=name,
            object_type="table",
            error=f"Could not select 'Database table' / 'Datenbanktabelle' radio: {result.error}",
            retrieved_at=now,
        )
    return None


async def _wait_for_se11_structure_screen(backend: WebGuiBackend | DesktopBackend, name: str) -> SE11Error | None:
    """Wait for SE11 structure screen and select the data type radio. Returns error or None."""
    now = datetime.now(UTC)

    # Wait for the screen to load by checking snapshot for radio presence
    for _ in range(20):  # 20 * 500ms = 10s max
        snapshot = await backend.get_snapshot()
        if "Datentyp" in snapshot or "Data type" in snapshot:
            break
        await asyncio.sleep(0.5)
    else:
        return SE11Error(
            name=name,
            object_type="structure",
            error=(
                "SE11 screen did not load. "
                "Could not find 'Data type' / 'Datentyp' radio button. "
                "This tool currently supports German (DE) and English (EN) SAP languages."
            ),
            retrieved_at=now,
        )

    # Select the data type radio via ensure_screen_state (with verification)
    target = bilingual_target(
        radios_de={SE11_DATA_TYPE_DE: True},
        radios_en={SE11_DATA_TYPE_EN: True},
    )
    result = await ensure_screen_state(backend, target)
    if not result.success:
        return SE11Error(
            name=name,
            object_type="structure",
            error=f"Could not select 'Data type' / 'Datentyp' radio: {result.error}",
            retrieved_at=now,
        )
    return None


async def _fill_table_name_field(backend: WebGuiBackend | DesktopBackend, name: str) -> SE11Error | None:
    """Fill the table name field in SE11 using real keyboard events. Returns error or None."""
    now = datetime.now(UTC)
    labels = [SE11_TABLE_NAME_DE, SE11_TABLE_NAME_EN, "Table name"]

    if await fill_field_with_keyboard(backend, labels, name.upper()):
        return None

    return SE11Error(
        name=name,
        object_type="table",
        error="Could not find table name field in SE11",
        retrieved_at=now,
    )


async def _fill_structure_name_field(backend: WebGuiBackend | DesktopBackend, name: str) -> SE11Error | None:
    """Fill the structure/data type name field in SE11 using real keyboard events. Returns error or None."""
    now = datetime.now(UTC)
    labels = [SE11_DICTIONARY_TYPE_DE, SE11_DICTIONARY_TYPE_EN]

    if await fill_field_with_keyboard(backend, labels, name.upper()):
        return None

    return SE11Error(
        name=name,
        object_type="structure",
        error="Could not find data type name field in SE11",
        retrieved_at=now,
    )


async def _click_display_button(backend: WebGuiBackend | DesktopBackend, name: str) -> None:
    """Click the Display button or fall back to F7."""
    # Try DE and EN display button labels
    for label in [SE11_DISPLAY_BUTTON_DE, SE11_DISPLAY_BUTTON_EN]:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            return
        except ValueError:  # pylint: disable=broad-exception-caught
            continue

    # Fall back to F7
    logger.warning("Display button not found, falling back to F7", extra={"object": name})
    await backend.press_key("F7")
    await backend.wait_for_ready()


async def _check_object_not_found(
    backend: WebGuiBackend | DesktopBackend, name: str, object_type: SE11ObjectType
) -> SE11Error | None:
    """Check if the status bar shows 'object not found'. Returns error or None."""
    now = datetime.now(UTC)
    status = await backend.get_status_bar()
    status_text = status.message or ""

    # Uses explicit constants: SE11_NOT_EXIST_DE/EN, SE11_NOT_FOUND_DE/EN
    not_found_msgs = {SE11_NOT_EXIST_DE, SE11_NOT_EXIST_EN, SE11_NOT_FOUND_DE, SE11_NOT_FOUND_EN}
    if status_text and any(msg in status_text.lower() for msg in not_found_msgs):
        await backend.press_key("F3")
        await backend.wait_for_ready()
        return SE11Error(
            name=name,
            object_type=object_type,
            error=f"Object '{name}' not found in ABAP Dictionary",
            retrieved_at=now,
        )

    return None


async def _lookup_object_on_initial_screen(  # pylint: disable=too-many-return-statements
    backend: WebGuiBackend | DesktopBackend, name: str, object_type: SE11ObjectType
) -> SE11Entry | SE11Error:
    """Look up a table or structure assuming we're already on the SE11 initial screen.

    The caller handles navigation (``enter_transaction``) and state reset
    (``/n`` between lookups) to prevent state bleeding in batch mode.
    """
    now = datetime.now(UTC)

    # Wait for screen and select object type
    if object_type == "table":
        error = await _wait_for_se11_table_screen(backend, name)
        if error:
            return error
        error = await _fill_table_name_field(backend, name)
        if error:
            return error
    else:
        error = await _wait_for_se11_structure_screen(backend, name)
        if error:
            return error
        error = await _fill_structure_name_field(backend, name)
        if error:
            return error

    # Click display and check for errors
    await _click_display_button(backend, name)

    error = await _check_object_not_found(backend, name, object_type)
    if error:
        return error

    # Get and parse snapshot
    snapshot = await backend.get_snapshot()
    snapshot_str = str(snapshot)
    logger.debug("Got snapshot", extra={"object": name, "length": len(snapshot_str)})

    parse_result = _parse_se11_yaml(snapshot_str, object_type)

    # Handle parse failure - save debug snapshot
    if isinstance(parse_result, SE11Error):
        logger.warning("Parse failed", extra={"object": name, "error": parse_result.error})
        debug_path = Path(f"se11_debug_{name}.yaml")
        debug_path.write_text(snapshot_str, encoding="utf-8")
        logger.warning("Saved debug snapshot", extra={"path": str(debug_path)})
        return SE11Error(name=name, object_type=object_type, error=parse_result.error, retrieved_at=now)

    # Verify parsed name matches requested name
    if parse_result.name.upper() != name.upper():  # pylint: disable=no-member
        return SE11Error(
            name=name,
            object_type=object_type,
            error=f"Object '{name}' not found (screen showed '{parse_result.name}')",
            retrieved_at=now,
        )

    return parse_result


# =============================================================================
# Desktop Backend (COM) Path
# =============================================================================

# DE/EN label variants for the SE11 input fields.
_SE11_TABLE_FIELD_LABELS = [SE11_TABLE_NAME_DE, SE11_TABLE_NAME_EN, "Table name"]
_SE11_STRUCTURE_FIELD_LABELS = [SE11_DICTIONARY_TYPE_DE, SE11_DICTIONARY_TYPE_EN]

# DE/EN column headers in the SE11 fields table control.
_COL_FIELD_NAME = ("Feld", "Feldname", "Field", "Field Name", "Field name")
_COL_DATA_TYPE = ("Datentyp", "Data Type", "Data type")
_COL_LENGTH = ("Länge", "Length")
_COL_DECIMALS = ("DezStellen", "Dez.St.", "Decimal Places", "Decimals", "Dec.Pl.")
_COL_SHORT_DESC = ("Kurzbeschreibung", "Short Description", "Short text")
# Note: Key column uses checkboxes which GetCell().Text can't read on desktop.
# Key field detection is not supported via table control; use WebGUI for that.


def _get_col(row: dict[str, str], candidates: tuple[str, ...]) -> str:
    """Get a column value trying multiple DE/EN header names."""
    for c in candidates:
        if c in row:
            return row[c]
    return ""


def _parse_se11_table_rows(rows: list[dict[str, str]]) -> list[SE11Field]:
    """Parse table control rows into SE11Field models."""
    fields: list[SE11Field] = []
    for row in rows:
        name = _get_col(row, _COL_FIELD_NAME)
        if not name:
            continue
        datatype = _get_col(row, _COL_DATA_TYPE)
        if not datatype:
            continue
        try:
            length = int(_get_col(row, _COL_LENGTH) or "0")
        except ValueError:
            length = 0
        try:
            dec_raw = int(_get_col(row, _COL_DECIMALS) or "0")
            decimals = dec_raw if dec_raw > 0 else None
        except ValueError:
            decimals = None
        # Key column uses checkboxes — GetCell().Text returns empty.
        # We cannot detect key fields via the desktop table control.
        is_key = False
        description = _get_col(row, _COL_SHORT_DESC)
        fields.append(
            SE11Field(
                name=name,
                datatype=datatype,
                length=length,
                decimals=decimals,
                description=description,
                is_key=is_key,
            )
        )
    return fields


async def _lookup_se11_desktop(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-statements
    backend: WebGuiBackend | DesktopBackend, name: str, object_type: SE11ObjectType
) -> SE11Entry | SE11Error:
    """Desktop-specific SE11 lookup using COM table control reading."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)
    await backend.wait_for_ready()

    # SE11 initial screen: select the radio button for the object type,
    # then fill the corresponding text field.
    # Radio buttons: RSRD1-TBMA (table), RSRD1-VIMA (view), RSRD1-DDTYPE (structure/type)
    # Text fields:   RSRD1-TBMA_VAL,     RSRD1-VIMA_VAL,  RSRD1-DDTYPE_VAL
    if object_type == "table":
        radio_id = "wnd[0]/usr/radRSRD1-TBMA"
        field_id = "wnd[0]/usr/ctxtRSRD1-TBMA_VAL"
    else:
        radio_id = "wnd[0]/usr/radRSRD1-DDTYPE"
        field_id = "wnd[0]/usr/ctxtRSRD1-DDTYPE_VAL"

    if not isinstance(backend, DesktopBackend):
        return SE11Error(name=name, object_type=object_type, error="Requires DesktopBackend", retrieved_at=now)

    session = backend.require_session()

    def _select_and_fill() -> str | None:
        """Select radio + fill field via raw COM.

        Polls for the radio button since SE11 may take a moment to render
        after transaction navigation.  Returns None on success, error on failure.
        """
        raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
        # Poll for the radio button (SE11 screen may not be rendered yet)
        radio = None
        for _attempt in range(20):
            radio = raw_session.FindById(radio_id, False)
            if radio is not None:
                break
            time.sleep(0.5)
        if radio is None:
            wnd = raw_session.FindById("wnd[0]", False)
            screen_title = wnd.Text if wnd else "unknown"
            return f"SE11 screen not ready after 10s (screen: {screen_title})"
        try:
            radio.Select()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return f"Could not select radio: {exc}"
        field = raw_session.FindById(field_id, False)
        if field is None:
            return f"Field not found: {field_id}"
        try:
            field.Text = name.upper()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return f"Could not fill field: {exc}"
        return None

    com = backend.com
    fill_error = await com.run(_select_and_fill)
    if fill_error:
        return SE11Error(name=name, object_type=object_type, error=fill_error, retrieved_at=now)

    # Press F7 (Display)
    await backend.press_key("F7")
    await backend.wait(2000)

    # Check status bar for errors
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return SE11Error(
            name=name, object_type=object_type, error=sbar.message or f"'{name}' not found", retrieved_at=now
        )

    # Verify we left the initial screen — SE11 display title is
    # "Dictionary: Tabelle anzeigen" (DE) / "Dictionary: Display Table" (EN),
    # NOT containing the object name. Check we're no longer on "Einstieg"/"Initial".
    screen = await backend.get_screen_info()
    title = (screen.title or "").lower()
    if "einstieg" in title or "initial" in title:
        return SE11Error(
            name=name,
            object_type=object_type,
            error=sbar.message or f"Object '{name}' not found in ABAP Dictionary",
            retrieved_at=now,
        )

    # Read the fields table control (SE11 shows fields on the main screen, no tabs)
    rows = await com.run(lambda: read_table_control_all_rows(session, _flatten))

    # Extract description from screen fields (DD02D-DDTEXT on the display screen)
    screen_fields = await backend.discover_fields()
    description = ""
    for f in screen_fields:
        if f.name and f.name.upper() == "DD02D-DDTEXT":
            description = f.value or ""
            break
    if not description:
        for f in screen_fields:
            if f.name and "DDTEXT" in f.name.upper():
                description = f.value or ""
                break

    fields = _parse_se11_table_rows(rows)
    if not fields:
        return SE11Error(
            name=name, object_type=object_type, error="Could not read fields from SE11 table control", retrieved_at=now
        )

    return SE11Entry(
        name=name.upper(),
        description=description,
        object_type=object_type,
        fields=fields,
        retrieved_at=now,
    )


async def _lookup_batch_se11_desktop(
    backend: WebGuiBackend | DesktopBackend, name_list: list[str], object_type: SE11ObjectType
) -> SE11Result:
    """Run SE11 lookups for a batch of names on the desktop backend."""
    entries: list[SE11Entry] = []
    errors: list[SE11Error] = []
    for name in name_list:
        await backend.enter_transaction("/n")
        await backend.wait_for_ready()
        tx_result = await backend.enter_transaction("SE11")
        if not tx_result.success:
            errors.append(
                SE11Error(
                    name=name,
                    object_type=object_type,
                    error=f"Failed to navigate to SE11: {tx_result.error}",
                    retrieved_at=datetime.now(UTC),
                )
            )
            continue
        await backend.wait_for_ready()
        try:
            result = await _lookup_se11_desktop(backend, name, object_type)
            if isinstance(result, SE11Entry):
                entries.append(result)
            else:
                errors.append(result)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("SE11 desktop lookup failed", extra={"name": name})
            errors.append(
                SE11Error(name=name, object_type=object_type, error=f"Error: {e}", retrieved_at=datetime.now(UTC))
            )
    if entries:
        return SE11Result(entries=entries, errors=errors)
    return SE11Result.failure(error=f"All {len(errors)} lookups failed", entries=[], errors=errors)


def _write_result_to_file(
    result: SE11Result,
    output_file: str,
    name_list: list[str],
) -> SE11FileSummary:
    """Write SE11 result to JSON file and return summary."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    return SE11FileSummary(
        success=result.success,
        error=result.error,
        output_file=str(output_path.absolute()),
        total_requested=len(name_list),
        successful=len(result.entries),
        failed=len(result.errors),
        sample_entries=[e.name for e in result.entries[:5]],
        sample_errors=[e.name for e in result.errors[:5]],
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se11_tools(mcp: FastMCP) -> None:
    """Register SE11 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up table or structure metadata from SE11 (ABAP Dictionary). "
            "If sap-adt is available, prefer its get_table_fields or get_object_info tools. "
            "USE THIS instead of sap_transaction('SE11') - faster and returns structured data. "
            "Returns field names, data types, lengths, and descriptions. "
            "Supports single name or list of names. Always queries live from SAP. "
            "Use object_type='table' for database tables, 'structure' for data structures. "
            "For large requests (>10 objects), provide output_file to write results to JSON file "
            "instead of returning inline (avoids context overflow)."
        ),
    )
    async def sap_se11_lookup(  # pylint: disable=too-many-branches
        names: str | list[str],
        object_type: SE11ObjectType,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE11Result | SE11FileSummary:
        """
        Look up table or structure metadata from SE11.

        Args:
            names: Single name or list of table/structure names
            object_type: 'table' for database tables, 'structure' for structures
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >10 objects to avoid context overflow.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE11Result with entries and errors (inline), or
            SE11FileSummary with file path and statistics (when output_file provided)
        """
        name_list = [names] if isinstance(names, str) else list(names)

        if not name_list:
            return SE11Result.failure("No names provided")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se11_lookup")
        except ValueError as e:
            return SE11Result.failure(f"Session error: {e}")

        # Route to desktop or WebGUI batch lookup
        if backend.backend_type == "desktop":
            final_result = await _lookup_batch_se11_desktop(backend, name_list, object_type)
        else:
            entries: list[SE11Entry] = []
            errors: list[SE11Error] = []

            for name in name_list:
                # Navigate to Easy Access first to ensure a clean starting state,
                # then open SE11.  This prevents state bleeding between lookups.
                await backend.enter_transaction("/n")
                await backend.wait_for_ready()

                tx_result = await backend.enter_transaction("SE11")
                if not tx_result.success:
                    errors.append(
                        SE11Error(
                            name=name,
                            object_type=object_type,
                            error=f"Failed to navigate to SE11: {tx_result.error}",
                            retrieved_at=datetime.now(UTC),
                        )
                    )
                    continue
                await backend.wait_for_ready()

                try:
                    result = await _lookup_object_on_initial_screen(backend, name, object_type)
                    if isinstance(result, SE11Entry):
                        entries.append(result)
                    else:
                        errors.append(result)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.exception("Looking up in SE11", extra={"object": name})
                    errors.append(
                        SE11Error(
                            name=name,
                            object_type=object_type,
                            error=f"Error looking up '{name}': {e}",
                            retrieved_at=datetime.now(UTC),
                        )
                    )

            # Build final result
            if entries:
                final_result = SE11Result(entries=entries, errors=errors)
            else:
                final_result = SE11Result.failure(
                    error=f"All {len(errors)} lookups failed",
                    entries=[],
                    errors=errors,
                )

        # Write to file if requested
        if output_file:
            return _write_result_to_file(final_result, output_file, name_list)

        if len(name_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning objects inline - consider using output_file parameter to avoid context overflow",
                extra={"count": len(name_list)},
            )

        return final_result
