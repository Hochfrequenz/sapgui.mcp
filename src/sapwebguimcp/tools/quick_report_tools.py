"""sap_quick_report composite tool — pipeline, classifier, registration."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from sapwebguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
from sapwebguimcp.models.sap_results import ScreenText, StatusBarInfo, TableData
from sapwebguimcp.models.screen_state import SelectionScreenState
from sapwebguimcp.tools._backend_utils import _is_desktop_backend
from sapwebguimcp.tools.screen_state_helpers import ensure_screen_state

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


_MAX_POST_F8_KEYS = 3


async def _execute_quick_report(
    backend: SapUiBackend,
    tcode: str,
    fields: dict[str, str] | None = None,
    checkboxes: dict[str, bool] | None = None,
    radios: dict[str, bool] | None = None,
    max_rows: int = 30,
    post_f8_keys: list[str] | None = None,
    output_file: str | None = None,
) -> QuickReportResult:
    """Execute the quick report pipeline."""
    warnings: list[str] = []

    # 1. Runtime guard: desktop backend
    if _is_desktop_backend(backend):
        return QuickReportResult.failure(
            error="sap_quick_report requires WebGUI backend. Use individual tools on desktop.",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )

    # 2. Enter transaction
    tx_result = await backend.enter_transaction(tcode)
    if not tx_result.success:
        return QuickReportResult.failure(
            error=f"Failed to open transaction {tcode}: {tx_result.error}",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )

    await backend.wait_for_ready()

    # 3. Fill selection screen (if any fields/checkboxes/radios given)
    if fields or checkboxes or radios:
        target = SelectionScreenState(
            fields=fields or {},
            checkboxes=checkboxes or {},
            radios=radios or {},
        )
        state_result = await ensure_screen_state(backend, target)
        if not state_result.success:
            warnings.append(f"Selection screen: {state_result.error}")
        warnings.extend(state_result.warnings)

    # 4. Press F8
    await backend.press_key("F8")

    # 5. Wait for SAP
    await backend.wait_for_ready()

    # 6. Classify, then apply post_f8_keys (max 3, with early exit)
    classification, status_bar = await classify_result_screen(backend)

    effective_keys = list(post_f8_keys or [])
    if len(effective_keys) > _MAX_POST_F8_KEYS:
        warnings.append(
            f"post_f8_keys has {len(effective_keys)} keys, max {_MAX_POST_F8_KEYS}. "
            f"Ignoring keys after index {_MAX_POST_F8_KEYS}."
        )
        effective_keys = effective_keys[:_MAX_POST_F8_KEYS]

    for key in effective_keys:
        # If screen is already classifiable, skip remaining keys
        if classification in (
            ScreenClassification.TABLE,
            ScreenClassification.EMPTY,
            ScreenClassification.ERROR,
        ):
            break

        # Press key, wait, and re-classify
        await backend.press_key(key)
        await backend.wait_for_ready()
        classification, status_bar = await classify_result_screen(backend)

    # 7. Parse by classification
    page_title = await backend.get_page_title()
    table = None
    screen_text = None

    if classification == ScreenClassification.TABLE:
        try:
            table = await backend.read_table(max_rows=max_rows)
        except Exception as exc:
            warnings.append(f"read_table failed: {exc}")
            table = TableData(headers=[], rows=[], total_rows=0, start_row=1)

    elif classification == ScreenClassification.UNKNOWN:
        screen_text = await backend.get_screen_text()
        logger.warning(
            "Unclassified screen after F8",
            extra={
                "tcode": tcode,
                "page_title": page_title,
                "status_bar_type": status_bar.type,
                "status_bar_message": status_bar.message,
            },
        )

    elif classification == ScreenClassification.ERROR:
        screen_text = await backend.get_screen_text()

    # 8. Build result
    result = QuickReportResult(
        tcode=tcode,
        screen_type=classification,
        page_title=page_title,
        status_bar_type=status_bar.type,
        status_bar_message=status_bar.message,
        table=table,
        screen_text=screen_text if classification in (ScreenClassification.ERROR, ScreenClassification.UNKNOWN) else None,
        warnings=warnings,
    )

    # 9. Output file
    if output_file:
        Path(output_file).write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )

    return result
