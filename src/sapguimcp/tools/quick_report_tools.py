"""sap_quick_report composite tool: enter a transaction, fill the selection screen, press F8, read the result."""

import logging
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.manager import get_backend
from sapguimcp.models.quick_report_models import QuickReportResult, ScreenClassification
from sapguimcp.models.sap_results import ScreenText, StatusBarInfo, TableData
from sapguimcp.tools.classic_list_helpers import read_classic_list_lines
from sapguimcp.tools.sap_tools import _transaction_desktop
from sapguimcp.utils import resolve_output_file_path, write_json_output_file

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend

logger = logging.getLogger(__name__)

_MAX_POST_F8_KEYS = 3
# After F8 the screen is resolved once it shows one of these (a result, no data, or an error to report).
_RESOLVED = (
    ScreenClassification.TABLE,
    ScreenClassification.LIST,
    ScreenClassification.EMPTY,
    ScreenClassification.ERROR,
)


async def _read_list_lines(backend: "DesktopBackend", max_rows: int) -> list[str]:
    """The lines of the classic list on screen (empty if there is none)."""
    session = backend.require_session()
    lines: list[str] = await backend.com.run(
        lambda: read_classic_list_lines(session, max_rows), retry_server_fault=True
    )
    return lines


async def _classify(  # noqa: PLR0911
    backend: "DesktopBackend", selection_screen: tuple[str | None, str | None], max_rows: int
) -> tuple[ScreenClassification, StatusBarInfo, TableData | None, list[str] | None]:
    """Classify the screen after F8 from its structure and the status bar type, never from SAP's UI texts.

    Returns the classification, the status bar and the rows read (table or list lines).
    """
    status = await backend.get_status_bar()
    if status.type == "E":
        return ScreenClassification.ERROR, status, None, None
    if await backend.check_popup():
        return ScreenClassification.UNKNOWN, status, None, None

    table = await backend.read_table(max_rows=max_rows)
    if table.headers:
        if not table.rows:
            return ScreenClassification.EMPTY, status, None, None
        return ScreenClassification.TABLE, status, table, None
    if status.type == "W":
        return ScreenClassification.ERROR, status, None, None

    info = await backend.get_screen_info()
    if (info.program, info.dynpro) == selection_screen:
        # F8 did not leave the selection screen: SAP reports "no data" as a message there.
        empty = status.type in ("S", "I") and bool(status.message)
        return ScreenClassification.EMPTY if empty else ScreenClassification.ERROR, status, None, None

    lines = await _read_list_lines(backend, max_rows)
    if lines:
        return ScreenClassification.LIST, status, None, lines
    return ScreenClassification.UNKNOWN, status, None, None


async def _fill_selection_screen(
    backend: "DesktopBackend",
    fields: dict[str, str] | None,
    checkboxes: dict[str, bool] | None,
    radios: dict[str, bool] | None,
    warnings: list[str],
) -> str | None:
    """Fill the selection screen. Returns an error text if something could not be set, so that F8 is not pressed."""
    problems: list[str] = []
    if fields:
        filled = await backend.fill_form(fields)
        if not filled.success:
            problems.append(filled.error or "fields could not be filled")
    for label, checked in (checkboxes or {}).items():
        try:
            await backend.set_checkbox(label, checked)
        except ValueError as exc:
            problems.append(str(exc))
    for label, selected in (radios or {}).items():
        if not selected:
            warnings.append(f"Radio button '{label}' was not changed: a radio button can only be selected")
            continue
        try:
            await backend.set_radio_button(label)
        except ValueError as exc:
            problems.append(str(exc))
    return "; ".join(problems) or None


async def _execute_quick_report(  # noqa: PLR0911  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements
    backend: "DesktopBackend",
    tcode: str,
    fields: dict[str, str] | None = None,
    checkboxes: dict[str, bool] | None = None,
    radios: dict[str, bool] | None = None,
    max_rows: int = 30,
    post_f8_keys: list[str] | None = None,
    output_file: str | None = None,
) -> QuickReportResult:
    """Run the pipeline. Anything that goes wrong on the way becomes a failure result."""
    if max_rows < 1:
        return QuickReportResult.failure(
            error=f"max_rows must be >= 1, got {max_rows}", tcode=tcode, screen_type=ScreenClassification.ERROR
        )
    if output_file:  # checked first: the report must not run when its result cannot be written
        try:
            resolve_output_file_path(output_file)
        except ValueError as exc:
            return QuickReportResult.failure(error=str(exc), tcode=tcode, screen_type=ScreenClassification.ERROR)

    warnings: list[str] = []
    try:
        # Shared with sap_transaction: an unknown transaction code is no error to SAP GUI (it stays on the old
        # screen and says so in the status bar), which that function turns into a failure.
        entered = await _transaction_desktop(backend, tcode, new_window=False)
        if not entered.success:
            return QuickReportResult.failure(
                error=f"Failed to open transaction {tcode}: {entered.error}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
            )
        await backend.wait_for_ready()
        opened = await backend.get_status_bar()
        if opened.type == "E":  # SAP refused the transaction (e.g. no authorization)
            return QuickReportResult.failure(
                error=f"Failed to open transaction {tcode}: {opened.message}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
            )

        problem = await _fill_selection_screen(backend, fields, checkboxes, radios, warnings)
        if problem:
            return QuickReportResult.failure(
                error=f"Selection screen not filled, F8 was not pressed: {problem}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
                warnings=warnings,
            )

        screen = await backend.get_screen_info()
        selection_screen = (screen.program, screen.dynpro)
        await backend.press_key("F8")
        await backend.wait_for_ready()
        classification, status, table, lines = await _classify(backend, selection_screen, max_rows)

        keys = list(post_f8_keys or [])
        if len(keys) > _MAX_POST_F8_KEYS:
            warnings.append(f"post_f8_keys has {len(keys)} keys, only the first {_MAX_POST_F8_KEYS} are used")
            keys = keys[:_MAX_POST_F8_KEYS]
        for key in keys:
            if classification in _RESOLVED:
                break
            await backend.press_key(key)
            await backend.wait_for_ready()
            classification, status, table, lines = await _classify(backend, selection_screen, max_rows)

        screen_text: ScreenText | None = None
        if classification in (ScreenClassification.ERROR, ScreenClassification.UNKNOWN):
            screen_text = await backend.get_screen_text()
        result = QuickReportResult(
            tcode=tcode,
            screen_type=classification,
            page_title=await backend.get_page_title(),
            status_bar_type=status.type,
            status_bar_message=status.message,
            table=table,
            list_lines=lines,
            screen_text=screen_text,
            popup=await backend.check_popup(),
            warnings=warnings,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("sap_quick_report failed", extra={"tcode": tcode})
        return QuickReportResult.failure(
            error=f"Pipeline error: {exc}", tcode=tcode, screen_type=ScreenClassification.ERROR, warnings=warnings
        )

    if output_file:
        try:
            write_json_output_file(output_file, result.model_dump(mode="json"))
        except (ValueError, OSError) as exc:  # the report ran: keep its result and say why it was not written
            result.warnings.append(f"output_file was not written: {exc}")
    return result


def register_quick_report_tools(mcp: FastMCP) -> None:
    """Register the sap_quick_report tool with the MCP server."""

    @mcp.tool(
        description=(
            "Run a report transaction in one call: enter the transaction, fill the selection screen (fields, "
            "checkboxes, radio buttons), press Execute (F8) and return the result.\n\n"
            "Works with any report or list transaction that has a selection screen (VA05, ME2M, MB51, FBL1N, "
            "Z-transactions, ...). Fields are matched by label or technical name. A field, checkbox or radio "
            "button that cannot be found fails the call before F8. SAP remembers the last values of a selection "
            "screen: fields you do not pass keep their previous value.\n\n"
            "screen_type tells what came back: table (ALV grid or table control, in `table`), list (classic list, "
            "in `list_lines`), empty (no data), error (status bar text and screen text say why) or unknown (screen "
            "text, or the open popup). The session stays on that screen, so you can continue with the individual "
            "tools. If a transaction shows a popup after F8, pass post_f8_keys=['Enter'] to dismiss it.\n\n"
            "Do NOT use for transactions with a dedicated tool (SE16: sap_se16_query, SM37: sap_sm37_lookup, "
            "SE11/SE24/SE37: the lookup tools) or without a selection screen (BP, VA01)."
        ),
        annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False),
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
        """Execute a transaction, fill the selection screen, press F8, return the result.

        Args:
            tcode: SAP transaction code (e.g. "VA05", "ME2M", "FBL1N").
            fields: Label (or technical name) to value pairs for the input fields of the selection screen.
            checkboxes: Label to checked pairs for checkboxes of the selection screen.
            radios: Label to True pairs for radio buttons to select (a radio button cannot be unselected).
            max_rows: Maximum rows (or list lines) to read from the result. Must be >= 1.
            post_f8_keys: Keys to press after F8 to dismiss popups (e.g. ["Enter"]), at most 3. Each key is only
                pressed while the result is still unresolved.
            output_file: If provided, write the result as JSON to this file (inside the output directory).
            session: Session ID (e.g. "s1", "s2"). None uses the primary session.
            agent_id: Agent ID for multi-agent session binding.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_quick_report")
        except ValueError as exc:
            return QuickReportResult.failure(
                error=f"Session error: {exc}", tcode=tcode, screen_type=ScreenClassification.ERROR
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
