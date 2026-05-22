"""
Parser for SLG1 (Application Log) ARIA snapshots.

Extracts log entries from the SLG1 log display grid. The SLG1 result screen
uses a split-screen layout:
  - Top: Grid with log headers (date/time/user, count, ext ID, object, subobject, etc.)
  - Bottom: Grid with messages for the selected log (Typ, Meldungstext)

The top grid columns (DE / EN):
  Datum/Uhrzeit/Benutzer | Date/Time/User
  Anzahl                 | Number
  Externe Identifikation | External Identification
  Objekttext             | Object Text
  Unterobjekttext        | Subobject Text
  Transaktionscode       | Transaction Code
  Programm               | Program
  Modus                  | Mode
  Protokollnummer        | Log Number

Each row's first gridcell contains a nested button with "DD.MM.YYYY HH:MM:SS USER".
Other gridcells contain button children with the cell value, or text "Leer"/"Empty".

Handles German and English label support.
"""

import logging
import re
from datetime import UTC, datetime

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SLG1_INITIAL_SCREEN_DE,
    SLG1_INITIAL_SCREEN_EN,
    SLG1_LOG_LIST_SCREEN_DE,
    SLG1_LOG_LIST_SCREEN_EN,
    SLG1_NO_LOGS_FOUND_DE,
    SLG1_NO_LOGS_FOUND_EN,
)
from sapguimcp.models.slg1_models import (
    SLG1LogEntry,
    SLG1LogListResult,
)

logger = logging.getLogger(__name__)

__all__ = [
    "is_slg1_initial_screen",
    "is_slg1_log_list_screen",
    "is_slg1_no_results",
    "parse_slg1_log_list",
]

# Max limits per design doc
MAX_LOGS = 50

# --- Regex patterns based on real ARIA snapshots ---

# Row pattern: matches the row description line in the YAML snapshot
# Example: '    - row "0 Leer /SDF/AIMAX /SDF/AIMAX_DVM Leer SAPMSSY1 Dialog-Betrieb 00000000000003779243":'
_ROW_LINE_PATTERN = re.compile(r"^\s+- row ")

# Gridcell value extraction - matches gridcell with quoted value
# Examples: '      - gridcell "4":', '      - gridcell "Leer"'
_GRIDCELL_VALUE_PATTERN = re.compile(r'gridcell "([^"]*)"')

# Gridcell without value (empty first cell)
_GRIDCELL_EMPTY_PATTERN = re.compile(r"gridcell:")

# Date/Time/User from nested button text in first gridcell
# DE: "23.02.2026 00:00:07 BATCH"
# EN: "02/23/2026 00:00:07 BATCH" or similar
_DATE_TIME_USER_PATTERN = re.compile(r'button "(\d{2}[./]\d{2}[./]\d{4}\s+\d{2}:\d{2}:\d{2}\s+\S+)"')

# Column header row detection
_COLUMN_HEADER_PATTERN = re.compile(r'row ".*Protokollnummer|row ".*Log Number', re.IGNORECASE)


def is_slg1_initial_screen(snapshot: AriaSnapshot) -> bool:
    """Check if we're on the SLG1 selection screen."""
    header = "\n".join(snapshot.split("\n")[:10])
    return SLG1_INITIAL_SCREEN_DE.lower() in header.lower() or SLG1_INITIAL_SCREEN_EN.lower() in header.lower()


def is_slg1_log_list_screen(snapshot: AriaSnapshot) -> bool:
    """Check if we're on the SLG1 log list/display screen."""
    header = "\n".join(snapshot.split("\n")[:10])
    return SLG1_LOG_LIST_SCREEN_DE.lower() in header.lower() or SLG1_LOG_LIST_SCREEN_EN.lower() in header.lower()


def is_slg1_no_results(snapshot: AriaSnapshot) -> bool:
    """Check if SLG1 returned no logs (status bar message or still on initial screen)."""
    snapshot_lower = snapshot.lower()
    return SLG1_NO_LOGS_FOUND_DE.lower() in snapshot_lower or SLG1_NO_LOGS_FOUND_EN.lower() in snapshot_lower


def _clean_cell_value(value: str) -> str:
    """Clean a cell value, converting 'Leer'/'Empty' to empty string."""
    if value.lower() in ("leer", "empty"):
        return ""
    return value.strip()


def _parse_grid_rows(snapshot: str) -> list[SLG1LogEntry]:  # pylint: disable=too-many-branches
    """
    Parse log entries from the SLG1 grid ARIA snapshot.

    The grid structure per row:
      gridcell[0]: Date/Time/User (nested button "DD.MM.YYYY HH:MM:SS USER")
      gridcell[1]: Message count (Anzahl)
      gridcell[2]: External ID
      gridcell[3]: Object text
      gridcell[4]: Subobject text
      gridcell[5]: Transaction code
      gridcell[6]: Program
      gridcell[7]: Mode
      gridcell[8]: Log number (Protokollnummer)
    """
    logs: list[SLG1LogEntry] = []
    lines = snapshot.split("\n")

    # Find the first grid section (top grid with log headers)
    in_grid = False
    past_header_row = False
    current_row_lines: list[str] = []

    for line in lines:
        # Detect grid start
        if "- grid:" in line and not in_grid:
            in_grid = True
            past_header_row = False
            continue

        if not in_grid:
            continue

        # Detect when we leave the first grid (separator or second grid)
        if in_grid and ("- separator " in line or ("- grid:" in line and past_header_row)):
            # Process any remaining row
            if current_row_lines and past_header_row:
                entry = _parse_single_row(current_row_lines)
                if entry:
                    logs.append(entry)
            break

        # Detect header row (skip it)
        if _COLUMN_HEADER_PATTERN.search(line):
            past_header_row = True
            continue

        if not past_header_row:
            continue

        # Detect data row start
        if _ROW_LINE_PATTERN.match(line):
            # Process previous row
            if current_row_lines:
                entry = _parse_single_row(current_row_lines)
                if entry:
                    logs.append(entry)
                if len(logs) >= MAX_LOGS:
                    break

            current_row_lines = [line]
        elif current_row_lines:
            current_row_lines.append(line)

    # Process last row
    if current_row_lines and past_header_row and len(logs) < MAX_LOGS:
        entry = _parse_single_row(current_row_lines)
        if entry:
            logs.append(entry)

    return logs


def _parse_single_row(row_lines: list[str]) -> SLG1LogEntry | None:  # pylint: disable=too-many-locals,too-many-branches
    """Parse a single grid row into an SLG1LogEntry."""
    row_text = "\n".join(row_lines)

    # Extract date/time/user from nested button
    date_time_match = _DATE_TIME_USER_PATTERN.search(row_text)
    date_str = ""
    time_str = ""
    user = ""
    if date_time_match:
        parts = date_time_match.group(1).split()
        if len(parts) >= 3:
            date_str = parts[0]
            time_str = parts[1]
            user = parts[2]
        elif len(parts) == 2:
            date_str = parts[0]
            time_str = parts[1]

    # Extract gridcell values in order
    # Find all gridcell values by scanning lines
    gridcell_values: list[str] = []
    for line in row_lines:
        stripped = line.strip()
        if stripped.startswith("- gridcell"):
            match = _GRIDCELL_VALUE_PATTERN.search(stripped)
            if match:
                gridcell_values.append(match.group(1))
            elif _GRIDCELL_EMPTY_PATTERN.search(stripped):
                gridcell_values.append("")  # empty gridcell (first cell with nested content)

    # Grid columns: [date_cell, count, ext_id, object, subobject, tcode, program, mode, log_number]
    # First cell is complex (nested), might be "" or have a value
    # We need at least the count and log number
    if len(gridcell_values) < 8:
        logger.debug("Row has too few gridcells: count=%r", len(gridcell_values))
        return None

    # Map values - first gridcell might be "" (complex cell) or have value
    # Shift index based on whether first cell was captured as empty or with value
    # The first real value after the date cell is the count
    try:
        # Typical: ["", count, ext_id, object, subobject, tcode, program, mode, log_number]
        # or: [count, ext_id, object, subobject, tcode, program, mode, log_number]
        # Find the log number (last value, always a long number like 00000000000003779243)
        log_number = ""
        for v in reversed(gridcell_values):
            if v and len(v) > 10 and v.isdigit():
                log_number = v
                break

        if not log_number:
            logger.debug("Could not find log number in gridcell values")
            return None

        # Find rightmost index of log_number (first occurrence could be a different cell)
        log_idx = len(gridcell_values) - 1 - gridcell_values[::-1].index(log_number)

        # Work backwards from log_number: mode, program, tcode, subobject, object, ext_id, count
        if log_idx < 7:
            logger.debug("Not enough cells before log_number")
            return None

        # gridcell_values[log_idx - 1] = mode (not used in model)
        # gridcell_values[log_idx - 2] = program (not used in model)
        # gridcell_values[log_idx - 3] = tcode (not used in model)
        subobject = _clean_cell_value(gridcell_values[log_idx - 4])
        obj = _clean_cell_value(gridcell_values[log_idx - 5])
        ext_id = _clean_cell_value(gridcell_values[log_idx - 6])
        count_str = _clean_cell_value(gridcell_values[log_idx - 7])

        if count_str and count_str.isdigit():
            message_count = int(count_str)
        else:
            logger.debug("Non-numeric message count: %r", count_str)
            message_count = 0

        return SLG1LogEntry(
            log_number=log_number,
            object=obj,
            subobject=subobject,
            external_id=ext_id,
            date=date_str,
            time=time_str,
            user=user,
            message_count=message_count,
        )
    except (IndexError, ValueError) as exc:
        logger.debug("Failed to parse row: %r", exc)
        return None


def parse_slg1_log_list(snapshot: AriaSnapshot) -> SLG1LogListResult:
    """
    Parse the full SLG1 result into a SLG1LogListResult.

    Args:
        snapshot: ARIA snapshot of the log list screen

    Returns:
        SLG1LogListResult with parsed logs
    """
    now = datetime.now(UTC)

    if is_slg1_no_results(snapshot) or is_slg1_initial_screen(snapshot):
        return SLG1LogListResult(
            logs=[],
            log_count=0,
            logs_truncated=False,
            retrieved_at=now,
        )

    logs = _parse_grid_rows(snapshot)
    logs_truncated = len(logs) >= MAX_LOGS

    return SLG1LogListResult(
        logs=logs[:MAX_LOGS],
        log_count=len(logs),
        logs_truncated=logs_truncated,
        retrieved_at=now,
    )
