"""sap_quick_report composite tool: enter a transaction, fill the selection screen, press F8, read the result."""

import logging
import re
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.desktop._key_mapping import key_to_vkey
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
_CLASSIC_LIST_SCREEN = ("SAPMSSY0", "120")  # program and screen of every classic list, also of its detail lists
# A plain code, or a code in a namespace (/NAMESPACE/NAME, optionally with parameters). Every other code starting
# with "/" is a command (/n, /o, /i, /nex, /*, /h ...) that leaves the transaction or opens another window.
_TCODE = re.compile(r"(?:/[A-Z0-9_]{3,10}/)?[A-Za-z0-9_]+(?: .*)?")  # namespace upper case: "/nab/x" is a command


def _check_output_file(output_file: str) -> None:
    """Raise ValueError if ``output_file`` cannot be written, without touching it (the report must not run first)."""
    path = resolve_output_file_path(output_file)
    if path.is_symlink():
        raise ValueError("output_file must not be a symbolic link")
    if path.is_dir():
        raise ValueError("output_file must name a file, not a directory")
    for parent in path.parents:
        if parent.exists():
            if not parent.is_dir():
                raise ValueError(f"output_file cannot be created: {parent.name} is a file, not a directory")
            break


async def _read_list_lines(backend: "DesktopBackend", max_rows: int) -> list[str]:
    """The lines of the classic list on screen (empty if there is none)."""
    session = backend.require_session()
    # one line more than wanted, to tell whether the list was cut off
    lines: list[str] = await backend.com.run(
        lambda: read_classic_list_lines(session, max_rows + 1, wide=True), retry_server_fault=True
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
        # F8 did not leave the selection screen: SAP reports "no data" as a message there. Limit of this heuristic:
        # any other success or info message on the selection screen (e.g. "job scheduled") also reads as "empty";
        # the status bar message is returned, so the caller can tell.
        empty = status.type in ("S", "I") and bool(status.message)
        return ScreenClassification.EMPTY if empty else ScreenClassification.ERROR, status, None, None

    # Only a classic list screen has the positioned labels the list reader looks at; a dynpro may have such labels too.
    on_list = (info.program, (info.dynpro or "").lstrip("0")) == _CLASSIC_LIST_SCREEN  # COM gives 120, not 0120
    lines = await _read_list_lines(backend, max_rows) if on_list else []
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
            _check_output_file(output_file)
        except ValueError as exc:
            return QuickReportResult.failure(error=str(exc), tcode=tcode, screen_type=ScreenClassification.ERROR)

    if not _TCODE.fullmatch(tcode):
        return QuickReportResult.failure(
            error=f"tcode must be a transaction code (/NAMESPACE/NAME is fine), not a command: '{tcode}'",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )
    keys = list(post_f8_keys or [])
    for key in keys:
        try:
            key_to_vkey(key)
        except KeyError as exc:
            return QuickReportResult.failure(
                error=f"Invalid post_f8_keys entry: {exc.args[0]}", tcode=tcode, screen_type=ScreenClassification.ERROR
            )

    warnings: list[str] = []
    executed = False  # F8 was sent: the report may have run
    try:
        # Fields, keys and F8 go to the topmost window: with a popup open they would hit the popup.
        popup = await backend.check_popup()
        if popup:
            return QuickReportResult.failure(
                error="Cannot start: a modal dialog is open (dismiss it first with sap_close_popup). "
                f"Dialog: {popup.message or 'confirmation required'}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
                popup=popup,
            )
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
        popup = await backend.check_popup()
        if popup:  # e.g. an authorization or system message instead of the selection screen
            return QuickReportResult.failure(
                error=f"Transaction {tcode} opened a dialog instead of the selection screen: "
                f"{popup.message or popup.title or 'no text'}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
                popup=popup,
            )
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
        executed = True
        pressed = await backend.press_key("F8")
        if not pressed.success:
            return QuickReportResult.failure(
                error=f"F8 could not be sent: {pressed.error}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
                report_executed=False,
                warnings=warnings,
            )
        await backend.wait_for_ready()
        classification, status, table, lines = await _classify(backend, selection_screen, max_rows)

        if len(keys) > _MAX_POST_F8_KEYS:
            warnings.append(f"post_f8_keys has {len(keys)} keys, only the first {_MAX_POST_F8_KEYS} are used")
            keys = keys[:_MAX_POST_F8_KEYS]
        for key in keys:
            if not await backend.check_popup():  # the keys are for popups only
                break
            pressed = await backend.press_key(key)
            if not pressed.success:
                return QuickReportResult.failure(
                    error=f"Key {key} could not be sent after F8: {pressed.error}",
                    tcode=tcode,
                    screen_type=classification,
                    report_executed=True,
                    warnings=warnings,
                )
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
            list_lines=lines[:max_rows] if lines is not None else None,
            report_executed=True,
            list_truncated=lines is not None and len(lines) > max_rows,
            screen_text=screen_text,
            popup=await backend.check_popup(),
            warnings=warnings,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("sap_quick_report failed", extra={"tcode": tcode})
        return QuickReportResult.failure(
            error=f"Pipeline error: {exc}",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
            report_executed=executed,
            warnings=warnings,
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
            "F8 really runs the report: reports that post, change or delete data will do so. Use display reports "
            "or the report's test-run option.\n\n"
            "Works with any report or list transaction that has a selection screen (VA05, ME2M, MB51, FBL1N, "
            "Z-transactions, ...). tcode must be a transaction code (namespaces like /NAMESPACE/NAME are fine, "
            "/n or /o commands are not). Fields are matched by label or technical name. "
            "SAP remembers the last values of a selection screen: fields you do not pass keep their previous value.\n\n"
            "success=false with report_executed=false: F8 was not sent. Causes: an open popup, an unknown "
            "transaction, a field, checkbox or radio button that cannot be found, an invalid post_f8_keys entry "
            "or an unusable output_file; the error says which. success=false with report_executed=true: F8 was "
            "sent and the call failed afterwards (a post_f8_keys press, reading the result); the report may have "
            "run, so check the screen with the individual tools and do not retry blindly. success=true: F8 was "
            "pressed and screen_type tells what came back: table (ALV grid or table control, in `table`), "
            "list (classic list, in `list_lines`), empty (no data), error (SAP answered with an error or warning, "
            "or F8 did not leave the selection screen; status bar and screen text say why) or unknown (screen "
            "text, or the open popup). The session stays on that screen, so you can continue with the individual "
            "tools.\n\n"
            "If a transaction shows a popup after F8, pass post_f8_keys=['Enter'] to answer it. The keys are "
            "pressed only while a popup is open, and Enter accepts the popup's default button, which may be a "
            "confirmation (e.g. Yes).\n\n"
            "Do NOT use for transactions with a dedicated tool (SE16: sap_se16_query, SM37: sap_sm37_lookup, "
            "SE11/SE24/SE37: the lookup tools) or without a selection screen (BP, VA01)."
        ),
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False),
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
            post_f8_keys: Keys to press after F8 to answer popups (e.g. ["Enter"], the default button), at most 3.
                Each key is only pressed while a popup is open.
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
