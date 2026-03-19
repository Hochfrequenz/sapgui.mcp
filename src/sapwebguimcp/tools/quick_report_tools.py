"""sap_quick_report composite tool — pipeline, classifier, registration."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sapwebguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
from sapwebguimcp.models.sap_results import StatusBarInfo

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

# Patterns that indicate "no data" in status bar (case-insensitive)
_EMPTY_PATTERNS: tuple[str, ...] = (
    "keine daten",
    "no data",
    "keine werte",
    "no entries",
)


async def classify_result_screen(
    backend: SapUiBackend,
) -> tuple[ScreenClassification, StatusBarInfo]:
    """Classify the current screen after F8.

    Priority:
    1. Status bar type "E" → ERROR
    2. Status bar contains empty-data pattern → EMPTY
    3. ARIA snapshot contains grid → TABLE
    4. Otherwise → UNKNOWN
    """
    status_bar = await backend.get_status_bar()

    # 1. Error
    if status_bar.type == "E":
        return ScreenClassification.ERROR, status_bar

    # 2. Empty
    msg_lower = status_bar.message.lower()
    if any(pattern in msg_lower for pattern in _EMPTY_PATTERNS):
        return ScreenClassification.EMPTY, status_bar

    # 3. Table (check ARIA snapshot for grid role)
    snapshot = await backend.get_snapshot()
    snapshot_str = str(snapshot)
    # In ARIA YAML snapshots, grids appear as "- grid" at some indentation level
    if re.search(r"^\s*- grid\b", snapshot_str, re.MULTILINE):
        return ScreenClassification.TABLE, status_bar

    # 4. Unknown
    return ScreenClassification.UNKNOWN, status_bar
