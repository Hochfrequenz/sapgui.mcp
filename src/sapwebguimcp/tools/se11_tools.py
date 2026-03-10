"""
SE11 (ABAP Dictionary) lookup tool for tables and structures.

This module provides a fast, single-call tool to retrieve table/structure
metadata from SE11, returning strongly-typed Pydantic models.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.protocol import SapUiBackend
from sapwebguimcp.lang import (
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
from sapwebguimcp.tools.field_helpers import fill_field_with_keyboard

from sapwebguimcp.models import (
    SE11Entry,
    SE11Error,
    SE11Field,
    SE11FileSummary,
    SE11ObjectType,
    SE11Result,
)

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


async def _wait_for_se11_table_screen(backend: SapUiBackend, name: str) -> SE11Error | None:
    """Wait for SE11 table screen and select the table radio. Returns error or None."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)
    # Uses explicit constants: SE11_DATABASE_TABLE_DE, SE11_DATABASE_TABLE_EN
    # Radio buttons don't have a backend protocol method, use _page directly
    page = backend._page  # type: ignore[attr-defined]  # pylint: disable=protected-access
    table_radio = page.get_by_role(
        "radio", name=re.compile(bilingual_pattern(SE11_DATABASE_TABLE_DE, SE11_DATABASE_TABLE_EN), re.I)
    )

    try:
        await table_radio.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snapshot = await backend.get_snapshot()
        logger.warning("Radio not found, snapshot preview", extra={"snapshot": str(snapshot)[:300]})
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

    await table_radio.click()
    return None


async def _wait_for_se11_structure_screen(backend: SapUiBackend, name: str) -> SE11Error | None:
    """Wait for SE11 structure screen and select the data type radio. Returns error or None."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)
    # Uses explicit constants: SE11_DATA_TYPE_DE, SE11_DATA_TYPE_EN
    # Radio buttons don't have a backend protocol method, use _page directly
    page = backend._page  # type: ignore[attr-defined]  # pylint: disable=protected-access
    type_radio = page.get_by_role(
        "radio", name=re.compile(bilingual_pattern(SE11_DATA_TYPE_DE, SE11_DATA_TYPE_EN), re.I)
    )

    try:
        await type_radio.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        snapshot = await backend.get_snapshot()
        logger.warning("Radio not found, snapshot preview", extra={"snapshot": str(snapshot)[:300]})
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

    await type_radio.click()
    return None


async def _fill_table_name_field(backend: SapUiBackend, name: str) -> SE11Error | None:
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


async def _fill_structure_name_field(backend: SapUiBackend, name: str) -> SE11Error | None:
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


async def _click_display_button(backend: SapUiBackend, name: str) -> None:
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


async def _check_object_not_found(backend: SapUiBackend, name: str, object_type: SE11ObjectType) -> SE11Error | None:
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
    backend: SapUiBackend, name: str, object_type: SE11ObjectType
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
            "USE THIS instead of sap_transaction('SE11') - faster and returns structured data. "
            "Returns field names, data types, lengths, and descriptions. "
            "Supports single name or list of names. Always queries live from SAP. "
            "Use object_type='table' for database tables, 'structure' for data structures. "
            "For large requests (>10 objects), provide output_file to write results to JSON file "
            "instead of returning inline (avoids context overflow)."
        ),
    )
    async def sap_se11_lookup(
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
