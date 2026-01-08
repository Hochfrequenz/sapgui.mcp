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
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import TimeoutError as PlaywrightTimeout

from sapwebguimcp.models import (
    SE11Entry,
    SE11Error,
    SE11Field,
    SE11FileSummary,
    SE11ObjectType,
    SE11Result,
    get_browser_manager,
)
from sapwebguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 10

# Regex patterns for parsing - compiled once for efficiency
_ROW_SPLIT_PATTERN = re.compile(r'(?=- row "(?:Zum Auswählen|To select a row))')
_FIELD_NAME_PATTERN = re.compile(
    r'row "(?:Zum Auswählen[^"]*Leertaste\.|To select a row, press the space bar\.)\s+(?P<field_name>[A-Z_0-9/]+)'
)
_ROW_DATA_PATTERN = re.compile(
    r'row "(?:Zum Auswählen[^"]*Leertaste\.|To select a row, press the space bar\.)\s+(?P<row_data>[^"]+)"',
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

    # Extract table/structure name (German or English labels)
    name_match = re.search(r'textbox "(?:Transp\.Tabelle|Struktur)":\s*(?P<name>\S+)', yaml_content)
    if not name_match:
        name_match = re.search(r'textbox "(?:Transparent Table|Structure)":\s*(?P<name>\S+)', yaml_content)

    if not name_match:
        return SE11Error(
            name="UNKNOWN",
            object_type=object_type,
            error="Object not found - SE11 did not display table/structure details",
            retrieved_at=now,
        )

    name = name_match.group("name").strip()

    # Extract description (German or English)
    desc_match = re.search(
        r'textbox "(?:Kurzbeschreibung|Short Description)":\s*(?P<description>.+?)(?:\n|$)', yaml_content
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


async def _wait_for_se11_table_screen(page: Any, name: str) -> SE11Error | None:
    """Wait for SE11 table screen and select the table radio. Returns error or None."""
    now = datetime.now(UTC)
    table_radio = page.get_by_role("radio", name=re.compile(r"Datenbanktabelle|Database table", re.I))

    try:
        await table_radio.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        page_title = await page.title()
        logger.warning("SE11: Page title when radio not found: %s", page_title)
        return SE11Error(
            name=name,
            object_type="table",
            error=(
                f"SE11 screen did not load (page title: '{page_title}'). "
                "Could not find 'Database table' / 'Datenbanktabelle' radio button. "
                "This tool currently supports German (DE) and English (EN) SAP languages."
            ),
            retrieved_at=now,
        )

    await table_radio.click()
    await page.wait_for_timeout(100)
    return None


async def _wait_for_se11_structure_screen(page: Any, name: str) -> SE11Error | None:
    """Wait for SE11 structure screen and select the data type radio. Returns error or None."""
    now = datetime.now(UTC)
    type_radio = page.get_by_role("radio", name=re.compile(r"Datentyp|Data type", re.I))

    try:
        await type_radio.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        page_title = await page.title()
        logger.warning("SE11: Page title when radio not found: %s", page_title)
        return SE11Error(
            name=name,
            object_type="structure",
            error=(
                f"SE11 screen did not load (page title: '{page_title}'). "
                "Could not find 'Data type' / 'Datentyp' radio button. "
                "This tool currently supports German (DE) and English (EN) SAP languages."
            ),
            retrieved_at=now,
        )

    await type_radio.click()
    await page.wait_for_timeout(100)
    return None


async def _fill_table_name_field(page: Any, name: str) -> SE11Error | None:
    """Fill the table name field in SE11. Returns error or None."""
    now = datetime.now(UTC)

    # Try multiple selectors for the table name field
    table_field = page.locator('[id*="TBMA_VAL"], [id*="TBMA-VAL"]').first
    if await table_field.count() == 0:
        table_field = page.get_by_role("textbox", name=re.compile(r"Tabellenname|Table name", re.I))
    if await table_field.count() == 0:
        table_field = page.locator("input[title*='Tabellenname'], input[title*='Table name']").first

    if await table_field.count() == 0:
        return SE11Error(
            name=name,
            object_type="table",
            error="Could not find table name field in SE11",
            retrieved_at=now,
        )

    await table_field.click(click_count=3)
    await page.wait_for_timeout(50)
    await page.keyboard.type(name.upper())
    return None


async def _fill_structure_name_field(page: Any, name: str) -> SE11Error | None:
    """Fill the structure/data type name field in SE11. Returns error or None."""
    now = datetime.now(UTC)

    type_field = page.get_by_role("textbox", name=re.compile(r"Dictionary.*Typ|Dictionary.*type", re.I))
    if await type_field.count() == 0:
        return SE11Error(
            name=name,
            object_type="structure",
            error="Could not find data type name field in SE11",
            retrieved_at=now,
        )

    await type_field.click(click_count=3)
    await page.wait_for_timeout(50)
    await page.keyboard.type(name.upper())
    return None


async def _click_display_button(page: Any, name: str) -> None:
    """Click the Display button or fall back to F7."""
    await page.wait_for_timeout(500)
    display_button = page.get_by_role("button", name=re.compile(r"^Anzeigen$|^Display$", re.I))

    if await display_button.count() > 0:
        await display_button.first.click(force=True)
    else:
        logger.warning("SE11: Display button not found for %s, falling back to F7", name)
        await page.keyboard.press("F7")

    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")


async def _check_object_not_found(page: Any, name: str, object_type: SE11ObjectType) -> SE11Error | None:
    """Check if the status bar shows 'object not found'. Returns error or None."""
    now = datetime.now(UTC)
    status_bar = page.locator("#sapStatusBarAll, [id*='STATUSBAR']").first
    status_text = await status_bar.text_content() if await status_bar.count() > 0 else ""

    not_found_msgs = ["existiert nicht", "does not exist", "nicht gefunden", "not found"]
    if status_text and any(msg in status_text.lower() for msg in not_found_msgs):
        await page.keyboard.press("F3")
        await page.wait_for_load_state("networkidle")
        return SE11Error(
            name=name,
            object_type=object_type,
            error=f"Object '{name}' not found in ABAP Dictionary",
            retrieved_at=now,
        )

    return None


async def _lookup_single_object(  # pylint: disable=too-many-return-statements
    page: Any, name: str, object_type: SE11ObjectType
) -> SE11Entry | SE11Error:
    """Look up a single table or structure in SE11."""
    now = datetime.now(UTC)

    # Navigate to SE11
    await page.wait_for_timeout(300)
    tx_result = await sap_transaction_impl("SE11")
    if not tx_result.success:
        return SE11Error(
            name=name,
            object_type=object_type,
            error=f"Failed to navigate to SE11: {tx_result.error}",
            retrieved_at=now,
        )

    # Wait for screen and select object type
    if object_type == "table":
        error = await _wait_for_se11_table_screen(page, name)
        if error:
            return error
        error = await _fill_table_name_field(page, name)
        if error:
            return error
    else:
        error = await _wait_for_se11_structure_screen(page, name)
        if error:
            return error
        error = await _fill_structure_name_field(page, name)
        if error:
            return error

    # Click display and check for errors
    await _click_display_button(page, name)

    error = await _check_object_not_found(page, name, object_type)
    if error:
        return error

    # Get and parse snapshot
    snapshot = await page.locator("body").aria_snapshot()
    logger.debug("SE11: Got snapshot for %s, length: %d chars", name, len(snapshot))

    parse_result = _parse_se11_yaml(snapshot, object_type)

    # Handle parse failure - save debug snapshot
    if isinstance(parse_result, SE11Error):
        logger.warning("SE11: Parse failed for %s: %s", name, parse_result.error)
        debug_path = Path(f"se11_debug_{name}.yaml")
        debug_path.write_text(snapshot, encoding="utf-8")
        logger.warning("SE11: Saved debug snapshot to %s", debug_path)
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
    ) -> SE11Result | SE11FileSummary:
        """
        Look up table or structure metadata from SE11.

        Args:
            names: Single name or list of table/structure names
            object_type: 'table' for database tables, 'structure' for structures
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >10 objects to avoid context overflow.

        Returns:
            SE11Result with entries and errors (inline), or
            SE11FileSummary with file path and statistics (when output_file provided)
        """
        name_list = [names] if isinstance(names, str) else list(names)

        if not name_list:
            return SE11Result.failure("No names provided")

        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        entries: list[SE11Entry] = []
        errors: list[SE11Error] = []

        for name in name_list:
            try:
                result = await _lookup_single_object(page, name, object_type)
                if isinstance(result, SE11Entry):
                    entries.append(result)
                else:
                    errors.append(result)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error looking up %s in SE11", name)
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
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(final_result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SE11FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(name_list),
                successful=len(entries),
                failed=len(errors),
                sample_entries=[e.name for e in entries[:5]],
                sample_errors=[e.name for e in errors[:5]],
            )

        if len(name_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning %d objects inline - consider using output_file parameter to avoid context overflow",
                len(name_list),
            )

        return final_result
