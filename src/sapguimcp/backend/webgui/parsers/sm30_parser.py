"""
Parser for SM30 (Table Maintenance View) ARIA snapshots.

Extracts structured row data from SM30 display mode grids, handling:
- Dynamic column headers (views have 2 to 20+ columns)
- Data rows with gridcell values
- View type detection (flat vs unsupported/SM34)
- German and English label support
- View not found detection via status note or initial screen heading
"""

import logging
import re
from datetime import UTC, datetime

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SE16_COLUMN_SELECTION_DE,
    SE16_COLUMN_SELECTION_EN,
    SM30_INITIAL_SCREEN_DE,
    SM30_INITIAL_SCREEN_EN,
    SM30_NOT_FOUND_DE,
    SM30_NOT_FOUND_EN,
    SM30_ROW_SELECT_HINT_DE,
    SM30_ROW_SELECT_HINT_EN,
)
from sapguimcp.models.sm30_models import SM30Row, SM30ViewResult, SM30ViewType

logger = logging.getLogger(__name__)

__all__ = [
    "parse_sm30_snapshot",
    "parse_sm30_columns",
    "parse_sm30_rows",
    "detect_sm30_view_type",
]

# =============================================================================
# Regex Patterns (based on real ARIA snapshots)
# =============================================================================

# Column header extraction from grid
# Real format: - columnheader "Land/Reg."
_COLUMNHEADER_PATTERN = re.compile(r'columnheader "(?P<name>[^"]+)"')

# Data row detection - DE/EN variants
# DE: row "Zum Auswählen einer Zeile drücken Sie die Leertaste. AD Andorra":
# EN: row "To select a row, press the space bar. AD Andorra":
_DATA_ROW_PATTERN = re.compile(
    rf'- row "(?:{re.escape(SM30_ROW_SELECT_HINT_DE)}|{re.escape(SM30_ROW_SELECT_HINT_EN)})',
)

# Gridcell value extraction
# Real format: - gridcell "AD": (with value) or - gridcell: (empty)
_GRIDCELL_WITH_VALUE_PATTERN = re.compile(r'gridcell "(?P<value>[^"]*)"')
_GRIDCELL_EMPTY_PATTERN = re.compile(r"^\s*- gridcell:\s*$")

# Row selection column names to skip (DE/EN)
_SELECTION_COLUMN_NAMES = {
    SE16_COLUMN_SELECTION_DE,
    SE16_COLUMN_SELECTION_EN,
}

# Selection gridcell text patterns to skip
_SELECTION_CELL_PATTERNS = [
    SM30_ROW_SELECT_HINT_DE,
    SM30_ROW_SELECT_HINT_EN,
]

# Not found detection
# Real format: note "Fehler Meldungsleiste Tabelle/View ZZZNOTEXIST99 ist nicht im Dictionary vorhanden"
_NOT_FOUND_PATTERNS = [
    "ist nicht im Dictionary vorhanden",
    "is not in the Dictionary",
    SM30_NOT_FOUND_DE,
    SM30_NOT_FOUND_EN,
    "nicht vorhanden",
    "not found",
    "kein Pflegedialog",
    "no maintenance dialog",
]

# View description from heading
# DE: heading "Sicht \"Globale Parameter der Länder/Regionen\" anzeigen: Übersicht"
# EN: heading "Display View \"Countries\": Overview"
_VIEW_TITLE_DE_PATTERN = re.compile(
    r'heading "Sicht \\?"(?P<desc>[^"\\]+)\\?" (?:anzeigen|ändern)',
    re.IGNORECASE,
)
_VIEW_TITLE_EN_PATTERN = re.compile(
    r'heading "(?:Display|Change) View \\?"(?P<desc>[^"\\]+)\\?"',
    re.IGNORECASE,
)

# Row count from button
# Real format: button "Eintrag 1 von 249" or button "Entry 1 of 249"
_ROW_COUNT_PATTERN = re.compile(
    r'button "(?:Eintrag|Entry)\s+\d+\s+(?:von|of)\s+(?P<total>\d+)"',
)


# =============================================================================
# Detection Functions
# =============================================================================


def detect_sm30_view_type(snapshot: AriaSnapshot) -> SM30ViewType:
    """
    Detect whether the SM30 snapshot shows a flat table or an unsupported view type.

    Returns "flat" if a grid with columnheaders is found.
    Returns "unsupported" if still on initial screen, SM34 redirect, or no grid found.
    """
    # Check if still on initial screen (not found or navigation failed)
    if _is_initial_screen(snapshot):
        return "unsupported"

    # Check for grid with column headers (indicates flat table)
    if _COLUMNHEADER_PATTERN.search(snapshot):
        return "flat"

    return "unsupported"


def _is_initial_screen(snapshot: str) -> bool:
    """Check if we're still on the SM30 initial screen."""
    header_section = "\n".join(snapshot.split("\n")[:10])
    return SM30_INITIAL_SCREEN_DE in header_section or SM30_INITIAL_SCREEN_EN in header_section


def _is_view_not_found(snapshot: str) -> bool:
    """Check if the snapshot indicates the view was not found."""
    snapshot_lower = snapshot.lower()
    return any(pattern.lower() in snapshot_lower for pattern in _NOT_FOUND_PATTERNS)


def _extract_view_description(snapshot: str) -> str:
    """Extract the view description from the page heading."""
    match = _VIEW_TITLE_DE_PATTERN.search(snapshot)
    if match:
        return match.group("desc").strip()

    match = _VIEW_TITLE_EN_PATTERN.search(snapshot)
    if match:
        return match.group("desc").strip()

    return ""


def _extract_total_row_count(snapshot: str) -> int | None:
    """Extract total row count from the 'Eintrag X von Y' button."""
    match = _ROW_COUNT_PATTERN.search(snapshot)
    if match:
        return int(match.group("total"))
    return None


# =============================================================================
# Column Parsing
# =============================================================================


def parse_sm30_columns(snapshot: AriaSnapshot) -> list[str]:
    """
    Extract column names from the SM30 grid header row.

    Skips the row selection column (present in both display and edit mode).
    Handles variable column counts dynamically.

    Args:
        snapshot: ARIA snapshot YAML content

    Returns:
        List of column names in order (excluding selection column)
    """
    columns: list[str] = []

    # Find the grid section and extract columnheaders before the first data row
    grid_start = snapshot.find("- grid:")
    if grid_start == -1:
        grid_start = snapshot.find("grid:")
    if grid_start == -1:
        logger.warning("No grid found in SM30 snapshot")
        return columns

    # Find the first data row to bound our search
    first_data_row = _DATA_ROW_PATTERN.search(snapshot[grid_start:])
    if first_data_row:
        header_section = snapshot[grid_start : grid_start + first_data_row.start()]
    else:
        # No data rows, search whole grid section
        header_section = snapshot[grid_start:]

    # Extract all columnheader values from header section
    for match in _COLUMNHEADER_PATTERN.finditer(header_section):
        col_name = match.group("name")
        if col_name not in _SELECTION_COLUMN_NAMES:
            columns.append(col_name)

    return columns


# =============================================================================
# Row Parsing
# =============================================================================


def _is_selection_cell(value: str) -> bool:
    """Check if a gridcell value is the row selection hint text."""
    return any(pattern in value for pattern in _SELECTION_CELL_PATTERNS)


def parse_sm30_rows(  # pylint: disable=too-many-branches
    snapshot: AriaSnapshot, columns: list[str] | None = None
) -> list[SM30Row]:
    """
    Extract data rows from SM30 display grid snapshot.

    Each row is returned as an SM30Row with values dict mapping column name to value.
    The first gridcell in each row (selection hint) is skipped.

    Args:
        snapshot: ARIA snapshot YAML content
        columns: Column names (if None, will be extracted from snapshot)

    Returns:
        List of SM30Row instances
    """
    if columns is None:
        columns = parse_sm30_columns(snapshot)

    if not columns:
        logger.warning("No columns found, cannot parse SM30 rows")
        return []

    rows: list[SM30Row] = []
    lines = snapshot.split("\n")
    in_data_row = False
    current_cells: list[str] = []

    for line in lines:
        # Check for start of a data row
        if _DATA_ROW_PATTERN.search(line):
            # Save previous row if valid
            if current_cells:
                _save_row(current_cells, columns, rows)
            current_cells = []
            in_data_row = True
            continue

        if in_data_row:
            # Check for end of data section (next rowgroup or non-grid content)
            stripped = line.strip()
            if stripped.startswith("- rowgroup") or stripped.startswith("- menu:"):
                if current_cells:
                    _save_row(current_cells, columns, rows)
                in_data_row = False
                current_cells = []
                continue

            # Check if we hit a new non-data row (like a button between rows)
            if stripped.startswith("- button"):
                continue

            # Extract gridcell value
            match = _GRIDCELL_WITH_VALUE_PATTERN.search(line)
            if match:
                value = match.group("value")
                # Skip the selection hint cell
                if not _is_selection_cell(value):
                    current_cells.append(value)
            elif _GRIDCELL_EMPTY_PATTERN.match(line):
                current_cells.append("")

    # Don't forget the last row
    if in_data_row and current_cells:
        _save_row(current_cells, columns, rows)

    return rows


def _save_row(
    cells: list[str],
    columns: list[str],
    rows: list[SM30Row],
) -> None:
    """Save cells as an SM30Row if valid (has data)."""
    if not cells:
        return

    values: dict[str, str] = {}
    for i, col_name in enumerate(columns):
        if i < len(cells):
            values[col_name] = cells[i]
        else:
            values[col_name] = ""

    if values:
        rows.append(SM30Row(values=values))


# =============================================================================
# Main Parser
# =============================================================================


def parse_sm30_snapshot(
    snapshot: AriaSnapshot,
    view_name: str,
) -> SM30ViewResult:
    """
    Parse SM30 display snapshot into structured data.

    This is the main entry point. Handles:
    - View not found (status note or initial screen)
    - SM34 redirect detection
    - Flat table parsing (dynamic columns + rows)

    Args:
        snapshot: The YAML accessibility snapshot from browser_snapshot
        view_name: The view/table name being looked up

    Returns:
        SM30ViewResult with parsed data or error
    """
    now = datetime.now(UTC)

    # Check for view not found
    if _is_view_not_found(snapshot) and _is_initial_screen(snapshot):
        return SM30ViewResult.failure(
            error=f"View '{view_name}' not found",
            view_name=view_name,
            description="",
            view_type="unsupported",
            columns=[],
            rows=[],
            row_count=0,
            retrieved_at=now,
        )

    # Detect view type
    view_type = detect_sm30_view_type(snapshot)

    if view_type == "unsupported":
        return SM30ViewResult.failure(
            error=(
                f"View '{view_name}' has an unsupported layout or requires SM34 "
                "(Extended Table Maintenance). Only flat table views are supported."
            ),
            view_name=view_name,
            description=_extract_view_description(snapshot),
            view_type="unsupported",
            columns=[],
            rows=[],
            row_count=0,
            retrieved_at=now,
        )

    # Parse flat table
    description = _extract_view_description(snapshot)
    columns = parse_sm30_columns(snapshot)
    rows = parse_sm30_rows(snapshot, columns)
    total_rows = _extract_total_row_count(snapshot)

    return SM30ViewResult(
        view_name=view_name,
        description=description,
        view_type="flat",
        columns=columns,
        rows=rows,
        row_count=total_rows if total_rows is not None else len(rows),
        retrieved_at=now,
    )
