"""
Parser for SPRO (Customizing IMG) search result ARIA snapshots.

Extracts IMG activities from the search results dialog, which contains
a 3-column grid: activity name, parent node, and area.

The results dialog appears as:
  dialog "Trefferliste zum Suchbegriff \"LAND\"":   (DE)
  dialog "Hit List for Search Term \"country\"":    (EN)
"""

import logging
import re
from datetime import UTC, datetime

from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SM30_ROW_SELECT_HINT_DE,
    SM30_ROW_SELECT_HINT_EN,
    SPRO_RESULTS_DIALOG_DE,
    SPRO_RESULTS_DIALOG_EN,
)
from sapguimcp.models.spro_models import SPROActivity, SPROSearchResult

logger = logging.getLogger(__name__)

__all__ = [
    "parse_spro_search_results",
]

# =============================================================================
# Regex Patterns (based on real ARIA snapshots)
# =============================================================================

# Results dialog detection (DE/EN)
# DE: dialog "Trefferliste zum Suchbegriff \"LAND\""
# EN: dialog "Search Term \"COUNTRY\" Hit List"
# Note: dialog titles contain escaped quotes (\") so we use .*? instead of [^"]*
_RESULTS_DIALOG_PATTERN = re.compile(
    rf'dialog ".*?(?:{re.escape(SPRO_RESULTS_DIALOG_DE)}|{re.escape(SPRO_RESULTS_DIALOG_EN)})',
)

# Data row with selection hint prefix
_DATA_ROW_PATTERN = re.compile(
    rf'- row "(?:{re.escape(SM30_ROW_SELECT_HINT_DE)}|{re.escape(SM30_ROW_SELECT_HINT_EN)})',
)

# Gridcell value extraction
_GRIDCELL_WITH_VALUE_PATTERN = re.compile(r'gridcell "(?P<value>[^"]*)"')
_GRIDCELL_EMPTY_PATTERN = re.compile(r"^\s*- gridcell:\s*$")

# Selection cell text patterns to skip
_SELECTION_CELL_PATTERNS = [
    SM30_ROW_SELECT_HINT_DE,
    SM30_ROW_SELECT_HINT_EN,
]


# =============================================================================
# Parser
# =============================================================================


def _is_selection_cell(value: str) -> bool:
    """Check if a gridcell value is the row selection hint text."""
    return any(pattern in value for pattern in _SELECTION_CELL_PATTERNS)


def _has_results_dialog(snapshot: str) -> bool:
    """Check if the snapshot contains a SPRO search results dialog."""
    return _RESULTS_DIALOG_PATTERN.search(snapshot) is not None


def _extract_results_section(snapshot: str) -> str:
    """Extract the results dialog section from the snapshot."""
    match = _RESULTS_DIALOG_PATTERN.search(snapshot)
    if not match:
        return ""
    return snapshot[match.start() :]


def parse_spro_search_results(  # pylint: disable=too-many-branches
    snapshot: AriaSnapshot,
    query: str,
) -> SPROSearchResult:
    """
    Parse SPRO search results from ARIA snapshot.

    The results dialog contains a grid with 3 data columns:
    - Gefundene Treffer / Hits Found: activity name
    - Übergeordneter Knoten / Higher-Level Node: parent node
    - Im Bereich / In Area: broad area

    Args:
        snapshot: YAML accessibility snapshot
        query: The search keyword that was used

    Returns:
        SPROSearchResult with parsed activities
    """
    now = datetime.now(UTC)

    # Check for results dialog
    if not _has_results_dialog(snapshot):
        # Could be: no results, still loading, or search failed
        return SPROSearchResult(
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    # Extract the results section
    results_section = _extract_results_section(snapshot)
    activities: list[SPROActivity] = []

    lines = results_section.split("\n")
    in_data_row = False
    current_cells: list[str] = []

    for line in lines:
        # Start of data row
        if _DATA_ROW_PATTERN.search(line):
            if current_cells:
                _save_activity(current_cells, activities)
            current_cells = []
            in_data_row = True
            continue

        if in_data_row:
            stripped = line.strip()

            # End of data section
            if stripped.startswith("- rowgroup") or stripped.startswith("- toolbar:"):
                if current_cells:
                    _save_activity(current_cells, activities)
                in_data_row = False
                current_cells = []
                continue

            # Skip non-data elements within rows
            if stripped.startswith("- button") or stripped.startswith("- textbox"):
                continue

            # Extract gridcell value
            match = _GRIDCELL_WITH_VALUE_PATTERN.search(line)
            if match:
                value = match.group("value")
                if not _is_selection_cell(value):
                    current_cells.append(value)
            elif _GRIDCELL_EMPTY_PATTERN.match(line):
                current_cells.append("")

    # Don't forget the last row
    if in_data_row and current_cells:
        _save_activity(current_cells, activities)

    return SPROSearchResult(
        query=query,
        activities=activities,
        activity_count=len(activities),
        retrieved_at=now,
    )


def _save_activity(cells: list[str], activities: list[SPROActivity]) -> None:
    """Convert 3 grid cells into an SPROActivity."""
    if not cells:
        return

    activity_name = cells[0]
    parent_node = cells[1] if len(cells) > 1 else ""
    area = cells[2] if len(cells) > 2 else ""

    if activity_name:
        activities.append(
            SPROActivity(
                activity_name=activity_name,
                parent_node=parent_node,
                area=area,
            )
        )
