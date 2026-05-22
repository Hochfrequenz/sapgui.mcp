"""
Parser for SE16N (Data Browser) ARIA snapshots.

Extracts structured row data from SE16N result grids, handling:
- Column headers from grid header row
- Data rows with pagination (YAML-quoted and unquoted formats)
- Type coercion for numeric values (int, float)
- German locale number formatting (dot as thousands separator)
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SE16_COLUMN_SELECTION_DE,
    SE16_COLUMN_SELECTION_EN,
    SE16_HIT_COUNT_LABEL_DE,
    SE16_HIT_COUNT_LABEL_EN,
    SE16_ROW_SELECT_HINT_DE,
    SE16_ROW_SELECT_HINT_EN,
    bilingual_pattern,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Regex Patterns (compiled once for efficiency)
# =============================================================================

# Match "Number of Hits" field - handles both English and German labels
# German locale uses dot as thousands separator (e.g., "5.000" = 5000)
# Uses explicit constants: SE16_HIT_COUNT_LABEL_DE, SE16_HIT_COUNT_LABEL_EN
_HIT_COUNT_PATTERN = re.compile(
    rf'textbox "{bilingual_pattern(SE16_HIT_COUNT_LABEL_DE, SE16_HIT_COUNT_LABEL_EN)}": "(?P<count>[0-9.]+)"'
)

# Match data rows - handles BOTH formats:
# - row "To select a row..."  (no colons in row text)
# - 'row "To select a row..."':  (has colons, YAML quotes the whole line)
# Uses explicit constants: SE16_ROW_SELECT_HINT_DE, SE16_ROW_SELECT_HINT_EN
_ROW_START_PATTERN = re.compile(rf"- '?row \"{bilingual_pattern(SE16_ROW_SELECT_HINT_DE, SE16_ROW_SELECT_HINT_EN)}")

# Extract gridcell values - matches both "gridcell "value"" and "gridcell:"
_GRIDCELL_WITH_VALUE_PATTERN = re.compile(r'gridcell "(?P<value>[^"]*)"')
_GRIDCELL_EMPTY_PATTERN = re.compile(r"^\s*- gridcell:\s*$")

# Match column headers
_COLUMNHEADER_PATTERN = re.compile(r'columnheader "(?P<name>[^"]+)"')

# Match header row (contains columnheader elements) - flexible multiline matching
_HEADER_ROW_PATTERN = re.compile(
    r'- row "[^"]*":\s*\n(?:\s*- columnheader "[^"]+"[^\n]*\n?)+',
    re.MULTILINE,
)

# Type coercion patterns
_INTEGER_PATTERN = re.compile(r"^-?\d+$")
_FLOAT_PATTERN = re.compile(r"^-?\d+\.\d+$")


# =============================================================================
# Data Types
# =============================================================================


@dataclass
class SE16ParseResult:
    """Result of parsing an SE16 snapshot."""

    columns: list[str]
    rows: list[dict[str, Any]]  # Each row is {column_name: coerced_value}


# =============================================================================
# Type Coercion
# =============================================================================


def _coerce_value(value: str) -> Any:
    """
    Attempt to coerce a string value to a more specific type.

    Design decision: Using dict[str, Any] to allow smart type coercion
    (numbers, dates) while maintaining Pydantic serializability. If a value
    cannot be safely coerced, it remains as string. All values are guaranteed
    JSON-serializable.

    Coercion rules:
    1. Empty string -> empty string (preserve)
    2. Integer-like -> int (e.g., "123", "0", "-45")
    3. Float-like -> float (e.g., "123.45", "-0.5")
    4. Everything else -> string (preserve original)

    Note: We intentionally do NOT attempt date parsing because SAP date formats
    vary by locale and context. Dates are returned as strings.
    """
    if not value:
        return value

    # Try integer first (more common in SAP data)
    if _INTEGER_PATTERN.match(value):
        try:
            return int(value)
        except ValueError:
            pass

    # Try float (with decimal point)
    if _FLOAT_PATTERN.match(value):
        try:
            return float(value)
        except ValueError:
            pass

    # Return as string
    return value


# =============================================================================
# Parsing Functions
# =============================================================================


def parse_se16_hit_count(snapshot: AriaSnapshot) -> int:
    """
    Extract the "Number of Hits" value from SE16N results screen.

    Handles German locale where dot is used as thousands separator:
    - "500" -> 500
    - "5.000" -> 5000
    - "50.000" -> 50000

    Args:
        snapshot: ARIA snapshot YAML content

    Returns:
        Integer hit count, or 0 if not found
    """
    match = _HIT_COUNT_PATTERN.search(snapshot)
    if match:
        # Remove dots (German thousands separator) and convert to int
        return int(match.group("count").replace(".", ""))
    return 0


def parse_se16_columns(snapshot: AriaSnapshot) -> list[str]:
    """
    Extract column names from the SE16N grid header row.

    Skips the first column ("Column for row selection") which is just
    a checkbox column for selecting rows.

    Args:
        snapshot: ARIA snapshot YAML content

    Returns:
        List of column names in order
    """
    columns: list[str] = []

    # Find the header row section - try flexible pattern first
    header_match = _HEADER_ROW_PATTERN.search(snapshot)
    if header_match:
        header_section = header_match.group(0)
    else:
        # Fallback: look for section between "rowgroup:" and first data row
        # This handles cases where the header row format varies
        grid_start = snapshot.find("- grid:")
        if grid_start == -1:
            grid_start = snapshot.find("grid:")
        if grid_start == -1:
            logger.warning("No grid found in snapshot")
            return columns

        # Find the first data row using explicit constants
        # SE16_ROW_SELECT_HINT_EN = "To select a row"
        # SE16_ROW_SELECT_HINT_DE = "Zum Auswählen einer Zeile"
        first_row = snapshot.find(f'row "{SE16_ROW_SELECT_HINT_EN}', grid_start)
        if first_row == -1:
            first_row = snapshot.find(f"'row \"{SE16_ROW_SELECT_HINT_EN}", grid_start)
        if first_row == -1:
            first_row = snapshot.find(f'row "{SE16_ROW_SELECT_HINT_DE}', grid_start)
        if first_row == -1:
            first_row = snapshot.find(f"'row \"{SE16_ROW_SELECT_HINT_DE}", grid_start)

        if first_row == -1:
            # No data rows, use everything after grid
            header_section = snapshot[grid_start:]
        else:
            header_section = snapshot[grid_start:first_row]

    # Extract all columnheader values
    for match in _COLUMNHEADER_PATTERN.finditer(header_section):
        col_name = match.group("name")
        # Skip the row selection column
        # Uses explicit constants: SE16_COLUMN_SELECTION_DE, SE16_COLUMN_SELECTION_EN
        if col_name not in (SE16_COLUMN_SELECTION_EN, SE16_COLUMN_SELECTION_DE):
            columns.append(col_name)

    return columns


def _save_row_if_valid(
    current_cells: list[str],
    columns: list[str],
    rows: list[dict[str, Any]],
) -> None:
    """Save current cells as a row dict if valid (has more than just selection cell)."""
    if current_cells and len(current_cells) > 1:
        row_dict = _cells_to_row_dict(current_cells[1:], columns)  # Skip selection cell
        if row_dict:
            rows.append(row_dict)


def _extract_gridcell_value(line: str) -> str | None:
    """Extract value from a gridcell line, returning None if not a gridcell."""
    match = _GRIDCELL_WITH_VALUE_PATTERN.search(line)
    if match:
        return match.group("value")
    if _GRIDCELL_EMPTY_PATTERN.match(line):
        return ""
    return None


def parse_se16_rows(snapshot: AriaSnapshot, columns: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Extract data rows from SE16N grid snapshot.

    Each row is returned as a dict mapping column name to value.
    Values are type-coerced where possible (int, float).

    Args:
        snapshot: ARIA snapshot YAML content
        columns: Column names (if None, will be extracted from snapshot)

    Returns:
        List of row dicts, each mapping column_name -> coerced_value
    """
    if columns is None:
        columns = parse_se16_columns(snapshot)

    if not columns:
        logger.warning("No columns found, cannot parse rows")
        return []

    rows: list[dict[str, Any]] = []
    lines = snapshot.split("\n")
    in_data_row = False
    current_cells: list[str] = []

    for line in lines:
        # Check for start of a data row
        if _ROW_START_PATTERN.search(line):
            _save_row_if_valid(current_cells, columns, rows)
            current_cells = []
            in_data_row = True
            continue

        if in_data_row:
            # Check for end of data section
            if "- rowgroup" in line or "- menu:" in line:
                _save_row_if_valid(current_cells, columns, rows)
                in_data_row = False
                current_cells = []
                continue

            # Extract gridcell value
            cell_value = _extract_gridcell_value(line)
            if cell_value is not None:
                current_cells.append(cell_value)

    # Don't forget the last row if we ended while still in a data row
    if in_data_row:
        _save_row_if_valid(current_cells, columns, rows)

    return rows


def _cells_to_row_dict(cells: list[str], columns: list[str]) -> dict[str, Any]:
    """Convert a list of cell values to a dict using column names as keys."""
    row_dict: dict[str, Any] = {}

    for i, col_name in enumerate(columns):
        if i < len(cells):
            row_dict[col_name] = _coerce_value(cells[i])
        else:
            # Missing cell - use empty string
            row_dict[col_name] = ""

    return row_dict


def parse_se16_snapshot(snapshot: AriaSnapshot) -> SE16ParseResult:
    """
    Parse a complete SE16N snapshot into columns and rows.

    This is the main entry point for parsing SE16 results.

    Args:
        snapshot: ARIA snapshot YAML content

    Returns:
        SE16ParseResult with columns and rows
    """
    columns = parse_se16_columns(snapshot)
    rows = parse_se16_rows(snapshot, columns)

    return SE16ParseResult(columns=columns, rows=rows)
