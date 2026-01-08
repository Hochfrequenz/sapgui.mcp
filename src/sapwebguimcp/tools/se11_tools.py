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
    # Format: textbox "Transp.Tabelle": T000
    # or: textbox "Struktur": BAPIRET2
    name_match = re.search(r'textbox "(?:Transp\.Tabelle|Struktur)":\s*(?P<name>\S+)', yaml_content)
    if not name_match:
        # Try English labels
        name_match = re.search(r'textbox "(?:Transparent Table|Structure)":\s*(?P<name>\S+)', yaml_content)

    if not name_match:
        return SE11Error(
            name="UNKNOWN",
            object_type=object_type,
            error="Object not found - SE11 did not display table/structure details",
            retrieved_at=now,
        )

    name = name_match.group("name").strip()

    # Extract description
    # Format: textbox "Kurzbeschreibung": Mandanten
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


def _parse_se11_fields(yaml_content: str) -> list[SE11Field]:
    """
    Parse field rows from SE11 grid.

    The grid format in YAML looks like (German):
    - row "Zum Auswählen... MANDT   MANDT CLNT 3 0 0 Mandant":
      - gridcell "Zum Auswählen..."
      - gridcell "MANDT":
        - textbox
      - gridcell "":           # Key checkbox
        - checkbox "" [checked] [disabled]
      ...

    Or in English:
    - row "To select a row, press the space bar. MANDT   MANDT CLNT 3 0 0 Client":
      ...

    The row text contains: FIELDNAME DATA_ELEMENT DATATYPE LENGTH DECIMALS COORD DESCRIPTION
    """
    fields = []
    key_fields = set()

    # First pass: find key fields by looking at the row structure
    # Key fields have [checked] on the first checkbox after the field name gridcell
    # Pattern: gridcell "FIELDNAME" -> gridcell "" with checkbox [checked]
    # We split by "- row" to get individual row blocks
    # Support both German ("Zum Auswählen") and English ("To select a row")
    row_blocks = re.split(r'(?=- row "(?:Zum Auswählen|To select a row))', yaml_content)

    for block in row_blocks:
        if not block.strip():
            continue

        # Extract field name from the row header (German or English)
        # German: "Zum Auswählen...Leertaste. FIELDNAME"
        # English: "To select a row, press the space bar. FIELDNAME"
        row_match = re.search(
            r'row "(?:Zum Auswählen[^"]*Leertaste\.|To select a row, press the space bar\.)\s+(?P<field_name>[A-Z_0-9/]+)',
            block,
        )
        if not row_match:
            continue

        field_name = row_match.group("field_name")

        # Look for the key checkbox pattern - it's right after the field name gridcell
        # The structure is:
        #   gridcell "FIELDNAME":
        #     - textbox
        #   gridcell "":
        #     - checkbox "" [checked] [disabled]  <- KEY checkbox
        # We need to find checkbox with [checked] that comes after gridcell "FIELDNAME"
        # but is in the next gridcell (not the same one)
        key_pattern = re.compile(
            r'gridcell "' + re.escape(field_name) + r'":\s*\n'  # Field name gridcell
            r"\s*- textbox\s*\n"  # Its textbox child
            r"\s*- gridcell[^:]*:\s*\n"  # Next gridcell (Key column)
            r"\s*- checkbox[^\n]*\[checked\]",  # Key checkbox with [checked]
        )

        if key_pattern.search(block):
            key_fields.add(field_name)

    # Second pass: parse field data from row text
    # Row format: "Zum Auswählen... FIELDNAME [maybe checkboxes] DATA_ELEMENT DATATYPE LENGTH DEC COORD DESCRIPTION"
    # English: "To select a row, press the space bar. FIELDNAME ..."
    # The row text contains all field info as space-separated values after the selection text
    row_pattern = re.compile(
        r'row "(?:Zum Auswählen[^"]*Leertaste\.|To select a row, press the space bar\.)\s+(?P<row_data>[^"]+)"',
        re.MULTILINE,
    )

    for match in row_pattern.finditer(yaml_content):
        row_data = match.group("row_data")

        # Split by whitespace, filter out empty strings and checkbox Unicode chars
        # Checkbox chars are in Unicode Private Use Area (U+E000-U+F8FF)
        parts = [p for p in row_data.split() if p and not (len(p) == 1 and ord(p) >= 0xE000)]

        # Expected: FIELDNAME DATA_ELEMENT DATATYPE LENGTH DECIMALS COORD DESCRIPTION...
        # But we need at least 6 parts before the description
        if len(parts) < 7:
            continue

        field_name = parts[0]

        # Find the data type by looking for a 2-10 char uppercase string
        # Data type comes after data element, which comes after field name
        datatype = None
        datatype_idx = -1
        for i, p in enumerate(parts[1:], 1):
            if re.match(r"^[A-Z][A-Z0-9]{1,9}$", p) and not p.isdigit():
                # Could be data element or data type - data type is shorter
                if datatype is None or len(p) < len(datatype):
                    datatype = p
                    datatype_idx = i

        if datatype is None or datatype_idx < 2:
            continue

        # Length and decimals follow the data type
        try:
            length = int(parts[datatype_idx + 1])
            decimals_raw = int(parts[datatype_idx + 2])
            # Use None for non-numeric types (where decimals is 0)
            decimals = decimals_raw if decimals_raw > 0 else None
            # Skip coord system (parts[datatype_idx + 3])
            # Description is everything after coord system
            description = " ".join(parts[datatype_idx + 4 :])
        except (IndexError, ValueError):
            continue

        # Clean up description
        description = description.strip()

        fields.append(
            SE11Field(
                name=field_name,
                datatype=datatype,
                length=length,
                decimals=decimals,
                description=description,
                is_key=field_name in key_fields,
            )
        )

    return fields


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
        # Normalize names to list
        name_list = [names] if isinstance(names, str) else list(names)

        if not name_list:
            return SE11Result.failure("No names provided")

        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        entries: list[SE11Entry] = []
        errors: list[SE11Error] = []

        for name in name_list:
            now = datetime.now(UTC)

            try:
                # Navigate to SE11 fresh for each lookup to avoid stale DOM issues
                # Small wait to let page stabilize before navigation
                await page.wait_for_timeout(300)
                tx_result = await sap_transaction_impl("SE11")
                if not tx_result.success:
                    errors.append(
                        SE11Error(
                            name=name,
                            object_type=object_type,
                            error=f"Failed to navigate to SE11: {tx_result.error}",
                            retrieved_at=now,
                        )
                    )
                    continue

                # Determine field label based on object type and language
                # German: "Datenbanktabelle" / "Datentyp"
                # English: "Database table" / "Data type"
                if object_type == "table":
                    # Wait for SE11 screen to load by waiting for the radio button
                    # This handles the async nature of SAP navigation
                    table_radio = page.get_by_role("radio", name=re.compile(r"Datenbanktabelle|Database table", re.I))
                    try:
                        await table_radio.wait_for(state="visible", timeout=10000)
                    except Exception:
                        # If wait fails, capture page state for debugging
                        page_title = await page.title()
                        logger.warning("SE11: Page title when radio not found: %s", page_title)
                        all_radios = page.get_by_role("radio")
                        all_count = await all_radios.count()
                        logger.warning("SE11: Total radio buttons on page: %d", all_count)
                        errors.append(
                            SE11Error(
                                name=name,
                                object_type=object_type,
                                error=(
                                    f"SE11 screen did not load (page title: '{page_title}'). "
                                    "Could not find 'Database table' / 'Datenbanktabelle' radio button. "
                                    "This tool currently supports German (DE) and English (EN) SAP languages."
                                ),
                                retrieved_at=now,
                            )
                        )
                        continue
                    await table_radio.click()
                    await page.wait_for_timeout(100)

                    # Fill the table name field - try multiple selectors
                    table_field = page.locator('[id*="TBMA_VAL"], [id*="TBMA-VAL"]').first
                    field_count = await table_field.count()
                    logger.debug("SE11: Table field locator count: %d for %s", field_count, name)

                    if field_count == 0:
                        # Try by label
                        table_field = page.get_by_role("textbox", name=re.compile(r"Tabellenname|Table name", re.I))
                        field_count = await table_field.count()
                        logger.debug("SE11: Table field by role count: %d for %s", field_count, name)

                    if field_count == 0:
                        # Try a broader selector
                        table_field = page.locator("input[title*='Tabellenname'], input[title*='Table name']").first
                        field_count = await table_field.count()
                        logger.debug("SE11: Table field by title count: %d for %s", field_count, name)

                    if field_count == 0:
                        errors.append(
                            SE11Error(
                                name=name,
                                object_type=object_type,
                                error="Could not find table name field in SE11",
                                retrieved_at=now,
                            )
                        )
                        continue

                    # Clear and fill - triple-click to select all, then type
                    await table_field.click(click_count=3)  # Select all
                    await page.wait_for_timeout(50)
                    await page.keyboard.type(name.upper())  # Type the name

                    # Verify the value was set
                    field_value = await table_field.input_value()
                    logger.debug("SE11: Table field value after fill: '%s' (expected: '%s')", field_value, name.upper())

                else:  # structure
                    # Wait for SE11 screen to load by waiting for the radio button
                    type_radio = page.get_by_role("radio", name=re.compile(r"Datentyp|Data type", re.I))
                    try:
                        await type_radio.wait_for(state="visible", timeout=10000)
                    except Exception:
                        page_title = await page.title()
                        logger.warning("SE11: Page title when radio not found: %s", page_title)
                        errors.append(
                            SE11Error(
                                name=name,
                                object_type=object_type,
                                error=(
                                    f"SE11 screen did not load (page title: '{page_title}'). "
                                    "Could not find 'Data type' / 'Datentyp' radio button. "
                                    "This tool currently supports German (DE) and English (EN) SAP languages."
                                ),
                                retrieved_at=now,
                            )
                        )
                        continue
                    await type_radio.click()
                    await page.wait_for_timeout(100)

                    # Fill the data type field
                    type_field = page.get_by_role("textbox", name=re.compile(r"Dictionary.*Typ|Dictionary.*type", re.I))
                    field_count = await type_field.count()
                    if field_count == 0:
                        errors.append(
                            SE11Error(
                                name=name,
                                object_type=object_type,
                                error="Could not find data type name field in SE11",
                                retrieved_at=now,
                            )
                        )
                        continue
                    await type_field.click(click_count=3)
                    await page.wait_for_timeout(50)
                    await page.keyboard.type(name.upper())

                # Click the Display button (more reliable than F7 in WebGUI)
                await page.wait_for_timeout(500)  # Wait for UI to stabilize
                display_button = page.get_by_role("button", name=re.compile(r"^Anzeigen$|^Display$", re.I))
                btn_count = await display_button.count()
                logger.debug("SE11: Display button count for %s: %d", name, btn_count)
                if btn_count > 0:
                    await display_button.first.click(force=True)
                else:
                    # Fall back to F7 - log warning as this may indicate unsupported language
                    logger.warning(
                        "SE11: Display button ('Anzeigen'/'Display') not found for %s, falling back to F7. "
                        "If this fails, the SAP language may not be supported (only DE/EN tested).",
                        name,
                    )
                    await page.keyboard.press("F7")
                await page.wait_for_timeout(500)  # Wait after click
                await page.wait_for_load_state("networkidle")

                # Debug: check page title to verify navigation
                page_title = await page.title()
                logger.debug("SE11: Page title after F7 for %s: %s", name, page_title)

                # Check status bar for errors
                status_bar = page.locator("#sapStatusBarAll, [id*='STATUSBAR']").first
                status_text = await status_bar.text_content() if await status_bar.count() > 0 else ""
                logger.debug(
                    "SE11: Status bar after F7 for %s: '%s'", name, status_text.strip() if status_text else "(empty)"
                )

                if status_text and any(
                    err in status_text.lower()
                    for err in ["existiert nicht", "does not exist", "nicht gefunden", "not found"]
                ):
                    errors.append(
                        SE11Error(
                            name=name,
                            object_type=object_type,
                            error=f"Object '{name}' not found in ABAP Dictionary",
                            retrieved_at=now,
                        )
                    )
                    # Press F3 to go back and continue with next
                    await page.keyboard.press("F3")
                    await page.wait_for_load_state("networkidle")
                    continue

                # Get accessibility snapshot
                snapshot = await page.locator("body").aria_snapshot()
                logger.debug("SE11: Got snapshot for %s, length: %d chars", name, len(snapshot))

                # Parse the snapshot
                parse_result = _parse_se11_yaml(snapshot, object_type)

                # Log if parsing failed
                if isinstance(parse_result, SE11Error):
                    logger.warning("SE11: Parse failed for %s: %s", name, parse_result.error)
                    # Save snapshot for debugging
                    debug_path = Path(f"se11_debug_{name}.yaml")
                    debug_path.write_text(snapshot, encoding="utf-8")
                    logger.warning("SE11: Saved debug snapshot to %s", debug_path)

                if isinstance(parse_result, SE11Entry):
                    # Verify the parsed name matches what we requested
                    if parse_result.name.upper() == name.upper():
                        entries.append(parse_result)
                    else:
                        # Wrong object displayed - likely a navigation issue
                        errors.append(
                            SE11Error(
                                name=name,
                                object_type=object_type,
                                error=f"Object '{name}' not found (screen showed '{parse_result.name}')",
                                retrieved_at=now,
                            )
                        )
                else:
                    # Ensure error has the requested name (not "UNKNOWN" or wrong name)
                    if parse_result.name != name.upper():
                        parse_result = SE11Error(
                            name=name,
                            object_type=object_type,
                            error=parse_result.error,
                            retrieved_at=parse_result.retrieved_at,
                        )
                    errors.append(parse_result)

                # No need for F3 - we re-navigate to SE11 for each lookup

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error looking up %s in SE11", name)
                errors.append(
                    SE11Error(
                        name=name,
                        object_type=object_type,
                        error=f"Error looking up '{name}': {e}",
                        retrieved_at=now,
                    )
                )
                # No need for F3 recovery - we re-navigate to SE11 for each lookup

        # Build the final result
        if entries:
            final_result = SE11Result(entries=entries, errors=errors)
        else:
            final_result = SE11Result.failure(
                error=f"All {len(errors)} lookups failed",
                entries=[],
                errors=errors,
            )

        # If output_file provided, write to file and return summary
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write full result as JSON
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

        # For large results without output_file, warn but still return
        if len(name_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning %d objects inline - consider using output_file parameter " "to avoid context overflow",
                len(name_list),
            )

        return final_result
