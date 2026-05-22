"""sap_quick_report composite tool — pipeline, classifier, registration."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.manager import get_backend
from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
from sapguimcp.models.sap_results import StatusBarInfo, TableData
from sapguimcp.models.screen_state import SelectionScreenState
from sapguimcp.tools.screen_state_helpers import ensure_screen_state

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

# Patterns that indicate "no data" in status bar (case-insensitive)
_EMPTY_PATTERNS: tuple[str, ...] = (
    "keine daten",
    "no data",
    "keine werte",
    "no entries",
    "kein job",
    "no job",
    "keine belege",
    "no documents",
)

# Page titles that indicate SAP Easy Access (main menu), not a report result.
_EASY_ACCESS_TITLES: tuple[str, ...] = (
    "sap easy access",
    "sap-easy-access",
)


async def classify_result_screen(  # pylint: disable=too-many-return-statements
    backend: WebGuiBackend | DesktopBackend,
) -> tuple[ScreenClassification, StatusBarInfo]:
    """Classify the current screen after F8.

    Priority:
    1. Status bar type "E" → ERROR
    2. Status bar contains empty-data pattern → EMPTY
    3. Status bar type "W" (Warning) → ERROR (SAP refused to execute, e.g.
       "Selektion wurde nicht eingeschränkt")
    4. Page title is Easy Access → ERROR (transaction didn't navigate away)
    5. ARIA snapshot contains grid → TABLE
    5b. ARIA snapshot contains list/listitem → LIST
    6. Still on selection screen (textbox + Ausführen button visible) → ERROR
    7. Otherwise → UNKNOWN
    """
    status_bar = await backend.get_status_bar()

    # 1. Error
    if status_bar.type == "E":
        return ScreenClassification.ERROR, status_bar

    # 2. Empty
    msg_lower = status_bar.message.lower()
    if any(pattern in msg_lower for pattern in _EMPTY_PATTERNS):
        return ScreenClassification.EMPTY, status_bar

    # 3. Warning — SAP showed a warning after F8 (e.g. selection not restricted).
    #    The report did not execute; treat as error so the agent can decide next steps.
    if status_bar.type == "W":
        return ScreenClassification.ERROR, status_bar

    # 4. Easy Access — transaction didn't open or invalid tcode bounced back
    page_title = await backend.get_page_title()
    if any(ea in page_title.lower() for ea in _EASY_ACCESS_TITLES):
        return ScreenClassification.ERROR, status_bar

    # 5. Table (check ARIA snapshot for grid role)
    snapshot = await backend.get_snapshot()
    snapshot_str = str(snapshot)
    # In ARIA YAML snapshots, grids appear as "- grid" at some indentation level
    if re.search(r"^\s*- grid\b", snapshot_str, re.MULTILINE):
        return ScreenClassification.TABLE, status_bar

    # 5b. Classic list (list/listitem roles, no grid)
    if re.search(r"^\s*- (?:list|listitem)\b", snapshot_str, re.MULTILINE):
        return ScreenClassification.LIST, status_bar

    # 6. Still on selection screen — F8 didn't navigate away.
    #    Selection screens have input textboxes.  Some transactions also show
    #    the Ausführen button, others (e.g. VF05) do not.  At this point we
    #    already ruled out grid, list, error, empty, and Easy Access, so
    #    textboxes remaining strongly indicates we never left the selection
    #    screen.
    if "textbox" in snapshot_str:
        logger.debug("classify_result_screen: still on selection screen after F8")
        return ScreenClassification.ERROR, status_bar

    # 7. Unknown
    return ScreenClassification.UNKNOWN, status_bar


_MAX_POST_F8_KEYS = 3
_F8_MAX_RETRIES = 3

# Labels for the SAP "Execute" button (DE + EN, with/without highlight marker)
_EXECUTE_BUTTON_LABELS: tuple[str, ...] = (
    "Ausführen",
    "Ausführen Hervorgehoben",
    "Execute",
    "Execute Highlighted",
)


async def _press_f8(backend: WebGuiBackend | DesktopBackend, tcode: str, attempt: int) -> None:
    """Execute the report by clicking the Ausführen button or pressing F8.

    Prefers a direct DOM click on the Execute button (reliable across all
    focus states).  Falls back to ``keyboard.press("F8")`` when the button
    is not found (some transactions hide it).
    """
    for label in _EXECUTE_BUTTON_LABELS:
        try:
            await backend.click_button(label)
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        # Button was clicked — wait for the server roundtrip.
        # This must be OUTSIDE the try/except so a timeout doesn't
        # cause us to retry with the next label (click already fired).
        await backend.wait_for_ready()
        logger.debug(
            "F8 via click_button(%s) attempt %d",
            label,
            attempt,
            extra={"tcode": tcode},
        )
        return

    # Fallback: keyboard F8
    logger.debug("F8 via keyboard (attempt %d)", attempt, extra={"tcode": tcode})
    await backend.press_key("F8")


async def _execute_quick_report(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches
    backend: WebGuiBackend | DesktopBackend,
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

    # 0. Validate max_rows (Field(ge=1) on tool signature is schema-only)
    if max_rows < 1:
        return QuickReportResult.failure(
            error=f"max_rows must be >= 1, got {max_rows}",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )

    # 1. Runtime guard: desktop backend
    if backend.backend_type == "desktop":
        return QuickReportResult.failure(
            error="sap_quick_report requires WebGUI backend. Use individual tools on desktop.",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )

    try:
        return await _run_pipeline(
            backend,
            tcode=tcode,
            fields=fields,
            checkboxes=checkboxes,
            radios=radios,
            max_rows=max_rows,
            post_f8_keys=post_f8_keys,
            output_file=output_file,
            warnings=warnings,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("sap_quick_report pipeline error for tcode=%s", tcode)
        return QuickReportResult.failure(
            error=f"Pipeline error: {exc}",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )


async def _run_pipeline(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
    backend: WebGuiBackend | DesktopBackend,
    tcode: str,
    fields: dict[str, str] | None,
    checkboxes: dict[str, bool] | None,
    radios: dict[str, bool] | None,
    max_rows: int,
    post_f8_keys: list[str] | None,
    output_file: str | None,
    warnings: list[str],
) -> QuickReportResult:
    """Inner pipeline logic — called by _execute_quick_report inside try/except."""
    # 2. Enter transaction
    tx_result = await backend.enter_transaction(tcode)
    if not tx_result.success:
        return QuickReportResult.failure(
            error=f"Failed to open transaction {tcode}: {tx_result.error}",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )

    await backend.wait_for_ready()

    # Wait for SAP's client-side JS to finish initialising the screen.
    # networkidle is insufficient: toolbar buttons and event handlers
    # may not be attached yet, causing F8 to be silently ignored.
    await backend.wait_for_sap_ready()

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

    # 4. Execute report (F8) — retry up to 3 times if screen doesn't change.
    #    Strategy: click the Ausführen button (DOM click, most reliable),
    #    fall back to keyboard F8 if the button is not found.
    classification = ScreenClassification.UNKNOWN
    status_bar = StatusBarInfo(type="none", message="")

    for attempt in range(1, _F8_MAX_RETRIES + 1):
        await _press_f8(backend, tcode, attempt)
        classification, status_bar = await classify_result_screen(backend)

        # If we got a definitive result, stop retrying.
        if classification not in (ScreenClassification.ERROR, ScreenClassification.UNKNOWN):
            break

        # UNKNOWN with empty status bar likely means SAP is still rendering
        # (e.g. loading popup). Wait and re-classify once.
        if classification == ScreenClassification.UNKNOWN and not status_bar.message:
            await backend.wait(2000)
            await backend.wait_for_ready()
            classification, status_bar = await classify_result_screen(backend)
            if classification != ScreenClassification.ERROR:
                break

        # ERROR with a real SAP message (E/W) means SAP responded —
        # don't retry, it's a genuine error, not a missed F8.
        if status_bar.type in ("E", "W"):
            break

        # Otherwise F8 was likely swallowed — retry with increasing delay.
        logger.warning(
            "F8 attempt %d/%d: still on selection screen, retrying",
            attempt,
            _F8_MAX_RETRIES,
            extra={"tcode": tcode},
        )
        if attempt < _F8_MAX_RETRIES:
            await backend.wait(500 * attempt)  # 500ms, 1000ms

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
            ScreenClassification.LIST,
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

    if classification in (ScreenClassification.TABLE, ScreenClassification.LIST):
        try:
            table = await backend.read_table(max_rows=max_rows)
        except Exception as exc:  # pylint: disable=broad-except
            warnings.append(f"read_table failed: {exc}")
            table = TableData(headers=[], rows=[], total_rows=0, start_row=1)

    elif classification == ScreenClassification.UNKNOWN:
        screen_text = await backend.get_screen_text()

        # Fallback: get_status_bar() may return empty if SAP hasn't
        # updated the DOM yet (race with networkidle). screen_text
        # captures it more reliably. Re-check empty patterns.
        if screen_text and screen_text.status_bar:
            sb_text_lower = screen_text.status_bar.lower()
            if any(pattern in sb_text_lower for pattern in _EMPTY_PATTERNS):
                classification = ScreenClassification.EMPTY
                screen_text = None  # not needed for EMPTY

        if classification == ScreenClassification.UNKNOWN:
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
        screen_text=(
            screen_text if classification in (ScreenClassification.ERROR, ScreenClassification.UNKNOWN) else None
        ),
        warnings=warnings,
    )

    # 9. Output file
    if output_file:
        Path(output_file).write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )

    return result


def register_quick_report_tools(mcp: FastMCP) -> None:
    """Register sap_quick_report tool with the MCP server."""

    @mcp.tool(
        description=(
            "Execute a transaction, fill the selection screen (fields, checkboxes, "
            "radio buttons), press Execute (F8), and return the result — all in one call.\n\n"
            "Works with any SAP report/list transaction that has a selection screen "
            "(VA05, ME2M, MB51, FBL1N, Z-transactions, etc.).\n\n"
            "After execution, you remain on the result screen. If the result is "
            "'unknown', use individual tools to investigate further.\n\n"
            "If you already know a transaction shows a popup after F8 (e.g., a variant "
            "selection dialog), pass post_f8_keys=['Enter'] to dismiss it automatically.\n\n"
            "Do NOT use for:\n"
            "- SE16 (use sap_se16_query instead)\n"
            "- SM37 (use sap_sm37_lookup instead — has job log support)\n"
            "- Transactions without selection screens (e.g., BP, VA01)\n"
            "- SE11/SE24/SE37 (use dedicated lookup tools)\n\n"
            "WebGUI-only. Returns an error on desktop backend."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False),
    )
    async def sap_quick_report(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        tcode: str,
        fields: dict[str, str] | None = None,
        checkboxes: dict[str, bool] | None = None,
        radios: dict[str, bool] | None = None,
        max_rows: int = Field(default=30, ge=1),
        post_f8_keys: list[str] | None = None,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> QuickReportResult:
        """Execute a transaction, fill selection screen, press F8, return result.

        Args:
            tcode: SAP transaction code (e.g., "VA05", "ME2M", "FBL1N").
            fields: Label-value pairs for text fields on the selection screen.
            checkboxes: Label-checked pairs for checkboxes on the selection screen.
            radios: Label-selected pairs for radio buttons on the selection screen.
            max_rows: Maximum rows to read from the result table. Must be >= 1.
            post_f8_keys: Keys to press after F8 to dismiss popups (e.g., ["Enter"]).
                Max 3 keys. Each key is only pressed if the screen is still unresolved.
            output_file: If provided, write the result as JSON to this file path.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent ID for multi-agent session binding.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_quick_report")
        except ValueError as exc:
            return QuickReportResult.failure(
                error=f"Session error: {exc}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
            )
        return await _execute_quick_report(
            backend,
            tcode=tcode,
            fields=fields,
            checkboxes=checkboxes,
            radios=radios,
            max_rows=max_rows,
            post_f8_keys=post_f8_keys,
            output_file=output_file,
        )
