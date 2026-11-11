"""
Parser for ST22 (Short Dump Analysis) ARIA snapshots.

Extracts short dump list data from the ST22 initial screen (count buttons)
and from the dump list ALV grid. Also provides best-effort parsing of
dump detail text pages with raw_text fallback.

ST22 structure (DE/EN):
- Initial screen: Selection screen with "Heute"/"Today" and "Gestern"/"Yesterday"
  buttons, each followed by a count button like "N Laufzeitfehler"/"N Runtime Errors".
- Dump list: ALV-like grid with rows containing time, program, error type, user, etc.
  Each row may use "row" or "gridcell" ARIA patterns.
- Dump detail: Scrollable text document with section headers like
  "Was ist geschehen?" / "What happened?", source code excerpts, call stacks.
"""

import logging
import re
from collections.abc import Iterable

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import LanguagePack
from sapguimcp.lang.schema import DumpSection
from sapguimcp.lang.text import compiled
from sapguimcp.models.st22_models import ST22Dump, ST22DumpDetail

logger = logging.getLogger(__name__)

__all__ = [
    "is_no_dumps_message",
    "parse_st22_dump_list",
    "parse_st22_dump_detail",
    "parse_st22_initial_screen",
]

# Max raw_text size (~10KB)
_MAX_RAW_TEXT_LENGTH = 10240

# =============================================================================
# Initial Screen Parsing
# =============================================================================


def _dump_count_pattern(t: LanguagePack) -> re.Pattern[str]:
    """Dump count on the initial screen: button "N Runtime Errors"."""
    return compiled(rf'button "(\d+)\s+{t.st22.runtime_errors.alt}"')


def parse_st22_initial_screen(snapshot: AriaSnapshot, t: LanguagePack) -> dict[str, int]:
    """Parse the ST22 initial screen to extract dump counts.

    Returns dict with keys "today" and "yesterday" mapping to dump counts.
    Returns 0 for missing counts.
    """
    counts: dict[str, int] = {"today": 0, "yesterday": 0}
    count_pattern = _dump_count_pattern(t)
    today_buttons = tuple(f'- button "{label}"' for label in t.st22.today)
    yesterday_buttons = tuple(f'- button "{label}"' for label in t.st22.yesterday)

    lines = snapshot.split("\n")
    # Find the Today and Yesterday buttons
    # The count button follows immediately after each
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(today_buttons):
            # Look for count button on the next line
            if i + 1 < len(lines):
                match = count_pattern.search(lines[i + 1])
                if match:
                    counts["today"] = int(match.group(1))
        elif stripped.startswith(yesterday_buttons):
            if i + 1 < len(lines):
                match = count_pattern.search(lines[i + 1])
                if match:
                    counts["yesterday"] = int(match.group(1))

    return counts


_MESSAGE_LINE = re.compile(r"\s*(?:-\s+)?(?:note|status|alert)(?![\w-])")
"""An ARIA line of the status bar / message area, as opposed to grid cells and text of the result data."""


def _message_lines(snapshot: str) -> str:
    """The status bar / message lines of a snapshot (the result data must not decide whether a list is empty)."""
    return "\n".join(line for line in snapshot.split("\n") if _MESSAGE_LINE.match(line))


def is_no_dumps_message(snapshot: AriaSnapshot, t: LanguagePack) -> bool:
    """Check if the snapshot contains a 'no dumps found' status message."""
    return t.st22.no_dumps.contains(_message_lines(snapshot))


# =============================================================================
# Dump List Parsing
# =============================================================================

# Row pattern for ST22 dump list
# ST22 dump list rows typically have: time, program, include, error_type, short_text, user
# The exact structure depends on ALV configuration

# Pattern to match a row with multiple cells in ARIA snapshot
_ROW_PATTERN = re.compile(r'^\s*-\s+row\s+"([^"]*)"')
_CELL_PATTERN = re.compile(r'cell\s+"([^"]*)"')

# Column header pattern
_COLUMNHEADER_PATTERN = re.compile(r'columnheader\s+"([^"]*)"')

# Gridcell pattern (alternative ALV rendering)
_GRIDCELL_PATTERN = re.compile(r'gridcell\s+"([^"]*)"')


def _identify_columns(snapshot: str) -> list[str]:
    """Extract column header names from the snapshot."""
    headers: list[str] = []
    for match in _COLUMNHEADER_PATTERN.finditer(snapshot):
        name = match.group(1).strip()
        if name:
            headers.append(name)
    return headers


def _map_column_to_field(col_name: str, t: LanguagePack) -> str | None:  # pylint: disable=too-many-return-statements
    """Map a column header name to a field name."""
    col = col_name.strip()

    # Time column
    if t.st22.col_time.equals(col):
        return "time"
    # Program column
    if t.st22.col_program.equals(col):
        return "program"  # lang-ok: code keys of the parsed row
    # Include column
    if col.lower() == "include":
        return "include"
    # Error type column
    if t.st22.col_error_type.equals(col):
        return "error_type"
    # Short text column
    if t.st22.col_short_text.equals(col):
        return "short_text"
    # User column
    if t.common.user.equals(col):
        return "user"  # lang-ok: code keys of the parsed row

    return None


def _try_heuristic_row(cells: list[str], dumps: list[ST22Dump]) -> None:
    """Try to create a dump entry from cells using heuristic field detection."""
    if len(cells) < 3:
        return

    # Heuristic: A dump row has time (HH:MM:SS), program name, error type
    has_time = any(re.match(r"\d{2}:\d{2}:\d{2}", c.strip()) for c in cells)
    has_upper = any(re.match(r"[A-Z_/]{3,}", c.strip()) for c in cells)
    if not (has_time and has_upper):
        return

    row_data: dict[str, str] = {}
    for cell in cells:
        cell = cell.strip()
        if not cell:
            continue
        if re.match(r"\d{2}:\d{2}:\d{2}", cell) and "time" not in row_data:
            row_data["time"] = cell
        elif re.match(r"[A-Z_/]{3,}", cell):
            if "error_type" not in row_data and "_" in cell:
                row_data["error_type"] = cell
            elif "program" not in row_data:  # lang-ok: code keys of the parsed row
                row_data["program"] = cell  # lang-ok: code keys of the parsed row
            elif "include" not in row_data:
                row_data["include"] = cell
            elif "user" not in row_data:  # lang-ok: code keys of the parsed row
                row_data["user"] = cell  # lang-ok: code keys of the parsed row

    if row_data.get("time"):
        dumps.append(
            ST22Dump(
                index=len(dumps),
                time=row_data.get("time", ""),
                program=row_data.get("program", ""),  # lang-ok: code keys of the parsed row
                include=row_data.get("include") or None,
                error_type=row_data.get("error_type", ""),
                short_text=row_data.get("short_text", ""),
                user=row_data.get("user", ""),  # lang-ok: code keys of the parsed row
            )
        )


def _flush_row(
    cells: list[str],
    column_mapping: dict[int, str],
    dumps: list[ST22Dump],
) -> None:
    """Process collected cells for a row and append to dumps if valid."""
    if len(cells) < 2:
        return

    row_data: dict[str, str] = {}
    for idx, value in enumerate(cells):
        field = column_mapping.get(idx)
        if field:
            row_data[field] = value.strip()

    if "error_type" in row_data or "program" in row_data:  # lang-ok: code keys of the parsed row
        dumps.append(
            ST22Dump(
                index=len(dumps),
                time=row_data.get("time", ""),
                program=row_data.get("program", ""),  # lang-ok: code keys of the parsed row
                include=row_data.get("include") or None,
                error_type=row_data.get("error_type", ""),
                short_text=row_data.get("short_text", ""),
                user=row_data.get("user", ""),  # lang-ok: code keys of the parsed row
            )
        )


def parse_st22_dump_list(snapshot: AriaSnapshot, t: LanguagePack) -> list[ST22Dump]:  # pylint: disable=too-many-branches,too-many-locals
    """Parse the ST22 dump list from an ARIA snapshot.

    Handles multiple formats:
    1. ALV grid with columnheader + gridcell rows
    2. Row-based format with cell elements
    3. Text-based format from ST22's custom list

    Returns list of ST22Dump entries with sequential 0-based indexes matching
    the UI row order (for correct row selection when fetching detail).
    """
    dumps: list[ST22Dump] = []

    if is_no_dumps_message(snapshot, t):
        return dumps

    lines = snapshot.split("\n")

    # Strategy 1: Look for columnheader rows to build column mapping
    headers = _identify_columns(snapshot)
    if headers:
        column_mapping: dict[int, str] = {}
        for i, header in enumerate(headers):
            field = _map_column_to_field(header, t)
            if field:
                column_mapping[i] = field

        if column_mapping:
            # Collect gridcell/cell values per row block
            # Headers end after last columnheader line, then data rows follow
            past_headers = False
            current_row_cells: list[str] = []

            for line in lines:
                if "columnheader" in line:
                    past_headers = True
                    continue

                if not past_headers:
                    continue

                # Check if this line starts a new row
                is_row_start = re.match(r"\s*-\s+row\b", line) is not None

                # Collect gridcell or cell values
                gridcells = _GRIDCELL_PATTERN.findall(line)
                cells_found = _CELL_PATTERN.findall(line) if not gridcells else gridcells

                if is_row_start and current_row_cells:
                    # Flush previous row
                    _flush_row(current_row_cells, column_mapping, dumps)
                    current_row_cells = []

                if cells_found:
                    current_row_cells.extend(cells_found)
                elif is_row_start:
                    # New row started, reset
                    if current_row_cells:
                        _flush_row(current_row_cells, column_mapping, dumps)
                    current_row_cells = []

            # Flush final row
            if current_row_cells:
                _flush_row(current_row_cells, column_mapping, dumps)

    # Strategy 2: Look for row elements with cells (common in SAP WebGUI ALV)
    # Accumulate cells per row block across lines
    if not dumps:
        current_cells: list[str] = []
        in_row = False

        for line in lines:
            is_row_line = _ROW_PATTERN.match(line) is not None
            cells_on_line = _CELL_PATTERN.findall(line)

            if is_row_line:
                # Flush previous row
                if current_cells:
                    _try_heuristic_row(current_cells, dumps)
                current_cells = []
                in_row = True

            if cells_on_line and in_row:
                current_cells.extend(cells_on_line)

        # Flush final row
        if current_cells:
            _try_heuristic_row(current_cells, dumps)

    return dumps


# =============================================================================
# Dump Detail Text Parsing
# =============================================================================


def _extract_text_content(snapshot: str) -> str:
    """Extract readable text content from ARIA snapshot, stripping ARIA markup."""
    text_parts: list[str] = []
    # Match text content in quotes (from various ARIA elements like text:, heading, etc.)
    text_pattern = re.compile(r'"([^"]{2,})"')
    for match in text_pattern.finditer(snapshot):
        text = match.group(1)
        # Skip ARIA role names and short labels
        if not text.startswith(("button", "textbox", "checkbox", "menuitem")):
            text_parts.append(text)
    return "\n".join(text_parts)


def _heading_text(line: str) -> str:
    """A line as it is compared with a heading: trimmed, lower case, without a trailing question mark."""
    return line.strip().rstrip("?").strip().lower()


def _is_heading(line: str, headings: Iterable[str]) -> bool:
    """The whole line is one of ``headings`` (optionally followed by ':'), not prose that merely contains one."""
    text = _heading_text(line)
    for heading in headings:
        wanted = _heading_text(heading)
        if text == wanted or text.startswith(wanted + ":"):
            return True
    return False


def _extract_section(
    text: str,
    start_markers: Iterable[str],
    end_markers: Iterable[str],
    end_pattern: re.Pattern[str] | None = None,
) -> str:
    """Extract the sections under every heading in ``start_markers`` (screen order), best-effort.

    A heading is a whole line. A section ends at the next heading in ``start_markers`` or ``end_markers`` or at a
    line that starts like ``end_pattern`` (the source code headings).
    """
    starts = list(start_markers)
    boundaries = [*starts, *end_markers]
    body: list[str] = []
    collecting = False
    for line in text.split("\n"):
        if _is_heading(line, starts):
            collecting = True
        elif _is_heading(line, boundaries) or (end_pattern is not None and end_pattern.match(line.strip())):
            collecting = False
        elif collecting and line.strip():
            body.append(line.strip())
    return "\n".join(body)


def _extract_error_type(text: str, t: LanguagePack) -> str:
    """Extract error type from dump detail text."""
    # Pattern: "Laufzeitfehler: RABAX_STATE" or "Runtime Error: MESSAGE_TYPE_X"
    # The error type contains underscores and is ALL CAPS
    label = t.st22.runtime_errors.alt
    patterns = [
        # "Laufzeitfehler: RABAX_STATE" / "Runtime Error: MESSAGE_TYPE_X"
        compiled(rf"{label}\s*[:]\s*([A-Z][A-Z_0-9]+)"),
        # Error name on its own line after a header
        compiled(rf"{label}\s*\n\s*([A-Z][A-Z_0-9]{{2,}})"),
        # Standalone error name with underscore (highly likely to be an error type)
        re.compile(r"\b([A-Z][A-Z_0-9]*_[A-Z_0-9]+)\b"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            candidate = match.group(1)
            # Skip known non-error tokens
            if candidate in ("ABAP", "SAP", "GUI", "HTML", "RFC", "HTTP"):
                continue
            return candidate
    return ""


def _extract_program(text: str, t: LanguagePack) -> str:
    """Extract program name from dump detail text."""
    patterns = [
        # "Programm: ZTEST_PROGRAM" or "Program: SAPMV45A" (case-sensitive value)
        compiled(rf"{t.common.program.alt}\s*[:]\s*([A-Z][A-Z0-9_/]+)"),
        # "Source Code of ZPROG" / "Quelltext des Programms ZPROG"
        compiled(rf"{t.st22.source_code_of.alt}\s+([A-Z][A-Z0-9_/]+)"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def _extract_line_number(text: str, t: LanguagePack) -> int | None:
    """Extract source line number from dump detail text."""
    patterns = [
        compiled(rf"{t.st22.source_line.alt}[:\s]+(\d+)"),
        compiled(rf"{t.st22.line.alt}\s+(\d+)\s+"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    return None


def _extract_call_stack(text: str, t: LanguagePack) -> list[str]:
    """Extract call stack entries from dump detail text (best-effort)."""
    text_lower = text.lower()
    start_pos = -1
    for marker in t.st22.call_stack_heading:
        pos = text_lower.find(marker.lower())
        if pos >= 0:
            start_pos = pos
            break

    if start_pos < 0:
        return []

    # Extract lines that look like stack entries
    chunk = text[start_pos : start_pos + 3000]
    lines = chunk.split("\n")
    stack: list[str] = []
    for line in lines[1:]:  # Skip the header line
        stripped = line.strip()
        if not stripped:
            if stack:
                break  # Empty line after entries = end of stack
            continue
        # Stack entries typically contain program names with uppercase + line numbers
        if re.search(r"[A-Z_/]{3,}", stripped):
            stack.append(stripped)
        elif stack:
            break  # Non-matching line after entries = end of stack

    return stack[:50]  # Cap at 50 entries


def parse_st22_dump_detail(snapshot: AriaSnapshot, t: LanguagePack) -> ST22DumpDetail:
    """Parse ST22 dump detail from an ARIA snapshot.

    Best-effort parsing: extracts known sections when possible,
    always provides raw_text as fallback.

    Args:
        snapshot: YAML accessibility snapshot from the ST22 dump detail screen
        t: Language pack of the session

    Returns:
        ST22DumpDetail with extracted data and raw_text fallback
    """
    # Extract readable text
    raw_text = _extract_text_content(snapshot)
    if len(raw_text) > _MAX_RAW_TEXT_LENGTH:
        raw_text = raw_text[:_MAX_RAW_TEXT_LENGTH] + "\n... [truncated]"

    # Best-effort section extraction
    sections = t.st22.section
    what_happened = _extract_section(
        raw_text,
        sections[DumpSection.WHAT_HAPPENED],
        [
            *sections[DumpSection.HOW_TO_CORRECT],
            *sections[DumpSection.ERROR_ANALYSIS],
            *t.st22.other_headings,
            *t.st22.call_stack_heading,
        ],
        end_pattern=t.st22.source_code_start.pattern,
    )

    how_to_correct = _extract_section(
        raw_text,
        sections[DumpSection.HOW_TO_CORRECT],
        [
            *sections[DumpSection.ERROR_ANALYSIS],
            *t.st22.other_headings,
            *t.st22.call_stack_heading,
        ],
        end_pattern=t.st22.source_code_start.pattern,
    )

    return ST22DumpDetail(
        error_type=_extract_error_type(raw_text, t),
        short_text="",  # Populated from list data by caller
        what_happened=what_happened,
        how_to_correct=how_to_correct,
        program=_extract_program(raw_text, t),
        include=None,
        line=_extract_line_number(raw_text, t),
        call_stack=_extract_call_stack(raw_text, t),
        raw_text=raw_text,
    )
