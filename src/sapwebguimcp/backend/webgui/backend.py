"""WebGUI backend implementation using Playwright/CDP.

Each ``WebGuiBackend`` instance wraps a single Playwright ``Page``
(one SAP session) and implements the ``SapUiBackend`` protocol.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from sapwebguimcp.backend.protocol import CheckActivateResult
from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.backend.webgui.js_helpers import load_js, load_js_with_field_utils
from sapwebguimcp.models.alv_models import AlvCellInfo, AlvMetadata, TableCellClickResult
from sapwebguimcp.models.base import PopupButton, PopupInfo
from sapwebguimcp.models.sap_results import (
    ButtonInfo,
    ClosePopupResult,
    DropdownFillResult,
    DropdownInfo,
    FieldFillError,
    FieldInfo,
    FillFormResult,
    FormField,
    FormFieldsResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SessionStatus,
    StatusBarInfo,
    TableData,
    TableRow,
    TransactionResult,
)
from sapwebguimcp.utils import is_sap_shortcut

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers private to WebGuiBackend
# ---------------------------------------------------------------------------

# Success/error prefixes used in SAP toolbar notes.
_SUCCESS_PREFIXES = ("Erfolgreich ", "Success ")
_ERROR_PREFIXES = ("Fehler ", "Error ")
_PREFIX_STRIP = re.compile(
    r"^(Erfolgreich|Success|Fehler|Error)\s+(Meldungsleiste|Message Bar)\s+",
)
_SUCCESS_PATTERNS = re.compile(
    r"keine Syntaxfehler|No syntax errors|"
    r"Aktives Objekt wurde generiert|Objekt wurde aktiviert|Object activated|"
    r"generated successfully",
    re.IGNORECASE,
)
_ERROR_PATTERNS = re.compile(
    r"Syntaxfehler|syntax error",
    re.IGNORECASE,
)


def _parse_toolbar_note(snapshot_text: str) -> tuple[bool, str]:
    """Parse toolbar note from an ARIA snapshot to determine success/failure."""
    match = re.search(r'note\s+"([^"]+)"', snapshot_text)
    if not match:
        return False, "No status message found in toolbar"

    full_note = match.group(1)
    message = _PREFIX_STRIP.sub("", full_note).strip() or full_note

    if full_note.startswith(_SUCCESS_PREFIXES):
        return True, message
    if full_note.startswith(_ERROR_PREFIXES):
        return False, message

    if _SUCCESS_PATTERNS.search(full_note):
        return True, message
    if _ERROR_PATTERNS.search(full_note):
        return False, message
    return False, message


def _escape_css_selector(selector: str) -> str:
    """Escape special CSS characters in SAP element IDs."""
    if not selector or not selector.startswith("#"):
        return selector
    id_part = selector[1:]
    if any(f"\\{c}" in id_part for c in ":[]#,"):
        return selector  # Already escaped
    escaped_id = ""
    for char in id_part:
        if char in r":[]#,":
            escaped_id += f"\\{char}"
        else:
            escaped_id += char
    return f"#{escaped_id}"


# ---------------------------------------------------------------------------
# WebGuiBackend
# ---------------------------------------------------------------------------


class WebGuiBackend:  # pylint: disable=too-many-public-methods
    """SapUiBackend implementation using Playwright browser automation.

    Each instance wraps a single Playwright ``Page`` (one SAP session).
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    # ---- private helpers ----

    async def _find_okcode_field(self) -> Any | None:
        """Find the OK-Code field on the page."""
        element = await self._page.query_selector("#ToolbarOkCode")
        if element and await element.is_visible():
            return element
        for selector in [
            "input[id*='OkCode']",
            "input[lsdata*='OKCODE']",
            "#M0\\:46\\:11\\:1",
        ]:
            element = await self._page.query_selector(selector)
            if element and await element.is_visible():
                return element
        return None

    async def _enable_okcode_field(self) -> tuple[bool, str]:
        """Attempt to enable the OK-Code field via SAP settings menu."""
        try:
            settings_selectors = [
                "span[title*='Einstellungen']",
                "span[title*='Settings']",
                "[lsdata*='SETTINGS']",
                "span.urBtnEmph[title]",
            ]
            for selector in settings_selectors:
                element = await self._page.query_selector(selector)
                if element and await element.is_visible():
                    await element.click()
                    await self._page.wait_for_timeout(500)
                    for option_selector in [
                        "text=OK-Code",
                        "text=Transaktionsfeld",
                        "text=Transaction Field",
                    ]:
                        option = await self._page.query_selector(option_selector)
                        if option and await option.is_visible():
                            await option.click()
                            await self._page.wait_for_timeout(300)
                            return True, "Enabled OK-Code field via settings menu"
            return False, "Could not find settings menu or OK-Code option"
        except Exception as e:  # pylint: disable=broad-exception-caught
            return False, f"Error enabling OK-Code field: {e}"

    async def _dismiss_language_dialog(self) -> None:
        """Handle SAP's 'Different original and logon languages' popup."""
        snap = await self._page.locator("body").aria_snapshot()
        if "Different original and logon languages" not in snap and "Originalsprache und Anmeldesprache" not in snap:
            return
        logger.info("Detected language mismatch dialog, confirming maintenance in original language")
        maint_btn = self._page.get_by_role("button", name="Maint. in orig. lang.")
        if not await maint_btn.is_visible(timeout=2000):
            maint_btn = self._page.get_by_role("button", name="Pflege in Originalsprache")
        if await maint_btn.is_visible(timeout=2000):
            await maint_btn.click()
            await self._page.wait_for_timeout(1000)
            await self._page.wait_for_load_state("networkidle")
        else:
            logger.warning("Language dialog detected but maintenance button not found")

    # ===================================================================
    # SapNavigation
    # ===================================================================

    async def login(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
    ) -> LoginResult:
        """Navigate to SAP WebGUI and log in."""
        try:
            logger.info("Navigating to SAP Web GUI")
            await self._page.goto(url)
            await self._page.wait_for_load_state("networkidle", timeout=15000)

            # Already logged in?
            okcode_field = await self._find_okcode_field()
            if okcode_field:
                return LoginResult(url=url, already_logged_in=True)

            # Check for login form
            login_form = await self._page.query_selector('input[type="password"], input[id*="user" i]')
            if not login_form:
                return LoginResult.failure(
                    f"Navigated to {url}. No login form detected.",
                    url=url,
                )

            # Fill credentials
            await self._page.fill('#sap-client, input[name="sap-client"]', client)
            await self._page.fill('#sap-user, input[name="sap-user"]', username)
            await self._page.fill('#sap-password, input[name="sap-password"]', password)

            try:
                await self._page.evaluate(
                    load_js("set_language_field.js"),
                    {"language": language},
                )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Could not set language field")

            await self._page.click("#LOGON_BUTTON")

            try:
                await self._page.wait_for_selector("#ToolbarOkCode", timeout=15000, state="visible")
                return LoginResult(url=url, user=username)
            except Exception:  # pylint: disable=broad-exception-caught
                page_content = await self._page.content()
                if "already logged" in page_content.lower() or "bereits angemeldet" in page_content.lower():
                    try:
                        await self._page.click(
                            'button:has-text("Continue"), '
                            'button:has-text("Weiter"), '
                            'button:has-text("Fortfahren")',
                            timeout=5000,
                        )
                        await self._page.wait_for_selector("#ToolbarOkCode", timeout=10000, state="visible")
                        return LoginResult(url=url, user=username, already_logged_in=True)
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass
                return LoginResult.failure(
                    "Login attempted but SAP Easy Access not detected.",
                    url=url,
                )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Logging in to SAP")
            return LoginResult.failure(f"Error during SAP login: {e}", url=url)

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        """Enter a transaction code via the OK-Code field."""
        try:
            okcode_field = await self._find_okcode_field()
            if not okcode_field:
                success, message = await self._enable_okcode_field()
                if not success:
                    return TransactionResult.failure(
                        f"Could not find or enable OK-Code field. {message}",
                        tcode=tcode,
                    )
                okcode_field = await self._find_okcode_field()
                if not okcode_field:
                    return TransactionResult.failure(
                        "OK-Code field still not visible after enabling.",
                        tcode=tcode,
                    )

            if tcode.startswith("/n") or tcode.startswith("/o"):
                transaction_input = tcode
            else:
                transaction_input = f"/n{tcode}"

            await self._page.bring_to_front()
            await self._page.wait_for_timeout(500)
            await okcode_field.click()
            await self._page.wait_for_timeout(200)
            await self._page.evaluate(
                load_js("set_okcode_field.js"),
                {"transactionInput": transaction_input},
            )
            await self._page.wait_for_timeout(300)
            await self._page.keyboard.press("Enter")
            await self._page.wait_for_load_state("networkidle", timeout=15000)

            title = await self._page.title()
            return TransactionResult(tcode=tcode, page_title=title)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Executing transaction")
            return TransactionResult.failure(f"Error executing transaction {tcode}: {e}", tcode=tcode)

    async def get_session_status(self) -> SessionStatus:
        """Check session health."""
        try:
            if self._page.is_closed():
                return SessionStatus(status="no_page", message="Browser page is closed.")

            okcode_field = await self._find_okcode_field()
            if okcode_field:
                return SessionStatus(status="active", message="SAP session is alive and responsive.")

            login_form = await self._page.query_selector('input[type="password"], input[id*="sap-user" i], #sap-user')
            if login_form:
                return SessionStatus(
                    status="logged_off",
                    message="Login page detected. Please use sap_login to log in again.",
                )

            page_content = await self._page.content()
            timeout_indicators = [
                "session timeout",
                "sitzung abgelaufen",
                "session expired",
                "zeitüberschreitung",
                "logged off",
                "abgemeldet",
            ]
            if any(indicator in page_content.lower() for indicator in timeout_indicators):
                return SessionStatus(
                    status="timed_out",
                    message="Session has timed out. Please use sap_login to reconnect.",
                )

            return SessionStatus(
                status="unknown",
                message="Cannot determine session status. Please check browser window.",
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Checking session status")
            return SessionStatus(status="unknown", message=f"Error checking status: {e}")

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        """Wait for SAP page to finish loading."""
        await self._page.wait_for_load_state("networkidle", timeout=timeout_ms)

    async def bring_to_front(self) -> None:
        """Bring the browser window to the foreground."""
        await self._page.bring_to_front()

    # ===================================================================
    # SapUiPrimitives
    # ===================================================================

    async def fill_field(self, label: str, value: str) -> None:
        """Fill a labelled input field. Raises ``ValueError`` on failure."""
        result = await self._page.evaluate(
            load_js_with_field_utils("set_field.js"),
            {"label": label, "value": value},
        )

        # Handle dropdown fields
        if result.get("isDropdown"):
            element_id = result.get("elementId")
            if not element_id:
                raise ValueError(f"Dropdown field '{label}' found but has no ID")
            dropdown_result = await self._page.evaluate(
                load_js("select_dropdown_option.js"),
                {"elementId": element_id, "optionText": value},
            )
            if not dropdown_result.get("success"):
                error = dropdown_result.get("error", "Failed to select dropdown option")
                raise ValueError(f"Could not fill dropdown '{label}': {error}")
            await self._page.wait_for_timeout(300)
            return

        if not result.get("success"):
            raise ValueError(f"Could not fill field '{label}': {result.get('error', 'Unknown error')}")

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult:
        """Fill multiple SAP form fields in a single call."""
        if not fields:
            return FillFormResult.failure("fields cannot be empty")

        try:
            result = await self._page.evaluate(
                load_js_with_field_utils("fill_form_fields.js"),
                {"fields": fields},
            )

            filled = result.get("filled", [])
            not_found = result.get("notFound", [])
            errors = [FieldFillError(field=a["field"], error=a["error"]) for a in result.get("ambiguous", [])]
            errors.extend(FieldFillError(field=e["field"], error=e["error"]) for e in result.get("errors", []))

            return FillFormResult(filled=filled, not_found=not_found, errors=errors)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Filling form fields")
            return FillFormResult.failure(f"Error filling form fields: {e}")

    async def fill_grid_cell(self, row: int, column: int | str, value: str) -> None:
        """Fill a grid/table cell by row and column (e.g. SE16 filter fields)."""
        # Use the SE16 filter filling JS pattern
        result = await self._page.evaluate(
            load_js("fill_se16_filter.js"),
            {"row": row, "column": column, "value": value},
        )
        if not result.get("success"):
            raise ValueError(
                f"Could not fill grid cell row={row} column={column}: " f"{result.get('error', 'Unknown error')}"
            )

    async def click_button(self, label: str) -> None:
        """Click a button by label text."""
        # Try ARIA role-based selector first (most reliable for SAP)
        btn = self._page.get_by_role("button", name=label, exact=True)
        if await btn.count() > 0:
            await btn.click()
            await self._page.wait_for_timeout(300)
            return

        # Fallback: case-insensitive
        btn = self._page.get_by_role("button", name=re.compile(re.escape(label), re.IGNORECASE))
        if await btn.count() > 0:
            await btn.first.click()
            await self._page.wait_for_timeout(300)
            return

        raise ValueError(f"Button '{label}' not found")

    async def click_tab(self, label: str) -> None:
        """Click a tab by label text."""
        tab = self._page.get_by_role("tab", name=label, exact=True)
        if await tab.count() > 0:
            await tab.click()
            await self._page.wait_for_timeout(500)
            await self._page.wait_for_load_state("networkidle")
            return

        # Fallback: case-insensitive
        tab = self._page.get_by_role("tab", name=re.compile(re.escape(label), re.IGNORECASE))
        if await tab.count() > 0:
            await tab.first.click()
            await self._page.wait_for_timeout(500)
            await self._page.wait_for_load_state("networkidle")
            return

        raise ValueError(f"Tab '{label}' not found")

    async def press_key(self, key: str) -> KeyboardResult:
        """Send a keyboard shortcut to SAP."""
        try:
            await self._page.bring_to_front()
            await self._page.wait_for_timeout(100)
            await self._page.keyboard.press(key)
            await self._page.wait_for_load_state("networkidle", timeout=15000)

            title = await self._page.title()

            if is_sap_shortcut(key):
                try:
                    status_info = await self._page.evaluate(load_js("extract_status_bar.js"))
                    return KeyboardResult(
                        key=key,
                        page_title=title,
                        status_bar_read=True,
                        status_bar_type=status_info.get("type", "none"),
                        status_bar_message=status_info.get("message", ""),
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    return KeyboardResult(key=key, page_title=title, status_bar_read=False)

            return KeyboardResult(key=key, page_title=title)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Sending keyboard shortcut")
            return KeyboardResult.failure(f"Error sending keyboard shortcut {key}: {e}", key=key)

    async def type_text(self, text: str) -> None:
        """Type text character by character."""
        await self._page.keyboard.type(text)

    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult:
        """Select a dropdown option by label and option text."""
        # First check the field type to get the element ID
        field_check = await self._page.evaluate(load_js("check_field_type.js"), label)

        if not field_check.get("found"):
            return DropdownFillResult(
                success=False,
                error_message=f"Field '{label}' not found",
            )

        if not field_check.get("isDropdown"):
            return DropdownFillResult(
                success=False,
                error_message=f"Field '{label}' is not a dropdown",
            )

        element_id = field_check.get("elementId")
        if not element_id:
            return DropdownFillResult(
                success=False,
                error_message=f"Dropdown '{label}' has no element ID",
            )

        result = await self._page.evaluate(
            load_js("select_dropdown_option.js"),
            {"elementId": element_id, "optionText": option},
        )

        if result.get("success"):
            await self._page.wait_for_timeout(300)
            return DropdownFillResult(success=True)

        return DropdownFillResult(
            success=False,
            error_message=result.get("error", "Unknown dropdown error"),
            available_options=result.get("available_options"),
        )

    # ===================================================================
    # SapUiInspection
    # ===================================================================

    async def get_status_bar(self) -> StatusBarInfo:
        """Read the current message from SAP's status bar."""
        try:
            status_info = await self._page.evaluate(load_js("extract_status_bar.js"))
            return StatusBarInfo(
                type=status_info.get("type", "none"),
                message=status_info.get("message", ""),
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Reading status bar")
            return StatusBarInfo.failure(f"Error reading status bar: {e}", type="none")

    async def get_screen_info(self) -> ScreenInfo:
        """Get technical information about the current SAP screen."""
        try:
            screen_info = await self._page.evaluate(load_js("extract_screen_info.js"))
            return ScreenInfo(
                transaction=screen_info.get("transaction"),
                title=screen_info.get("title", ""),
                url=screen_info.get("url", ""),
                program=screen_info.get("program"),
                dynpro=screen_info.get("dynpro"),
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting screen info")
            return ScreenInfo.failure(f"Error getting screen info: {e}", title="", url="")

    async def get_screen_text(self, include_dropdown_options: bool = False) -> ScreenText:
        """Get all readable text from the current SAP screen."""
        try:
            result = await self._page.evaluate(load_js("extract_screen_text.js"))

            screen_text = ScreenText(
                title=result.get("title", ""),
                status_bar=result.get("statusBar") or None,
                tabs=result.get("tabs", []),
                labels=result.get("labels", []),
                buttons=result.get("buttons", []),
            )

            if include_dropdown_options:
                dropdowns = await self._fetch_dropdown_options()
                screen_text.dropdowns = dropdowns

            return screen_text

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Extracting screen text")
            return ScreenText.failure(f"Error extracting screen text: {e}")

    async def discover_fields(self) -> list[FieldInfo]:
        """Discover all input fields on the current SAP screen."""
        fields_data = await self._page.evaluate(load_js("discover_fields.js"))
        return [
            FieldInfo(
                id=f.get("id"),
                name=f.get("name"),
                field_id=f.get("fieldId"),
                label=f.get("label"),
                type=f.get("type"),
                selector=f.get("selector", ""),
                alternative_selectors=f.get("alternativeSelectors", []),
                value=f.get("value"),
            )
            for f in fields_data
        ]

    async def get_form_fields(self) -> FormFieldsResult:
        """Discover fillable form fields with type information."""
        try:
            from sapwebguimcp.models.sap_results import SapFieldType  # pylint: disable=import-outside-toplevel

            raw_fields = await self._page.evaluate(load_js("detect_form_fields.js"))
            fields = [
                FormField(
                    id=raw.get("id", ""),
                    label=raw.get("label", ""),
                    field_type=SapFieldType(raw.get("field_type", "text")),
                    current_value=raw.get("current_value"),
                    readonly=raw.get("readonly", False),
                    options=None,
                )
                for raw in raw_fields
            ]
            return FormFieldsResult(fields=fields)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting form fields")
            return FormFieldsResult.failure(f"Error getting form fields: {e}")

    async def discover_buttons(self) -> list[ButtonInfo]:
        """Discover all clickable buttons on the current SAP screen."""
        buttons_data = await self._page.evaluate(load_js("discover_buttons.js"))
        return [
            ButtonInfo(
                label=b.get("label", ""),
                id=b.get("id"),
                selector=b.get("selector"),
                shortcut=b.get("shortcut"),
                accesskey=b.get("accesskey"),
            )
            for b in buttons_data
            if b.get("label")
        ]

    async def get_snapshot(self) -> AriaSnapshot:
        """Get the ARIA accessibility tree snapshot."""
        raw = await self._page.locator("body").aria_snapshot()
        return AriaSnapshot(raw)

    async def take_screenshot(self) -> bytes:
        """Take a screenshot of the current page."""
        return await self._page.screenshot(full_page=True)

    async def read_table(self) -> TableData:
        """Read rows from an ALV grid or table on the current screen."""
        try:
            table_data = await self._page.evaluate(
                load_js("extract_table_data.js"),
                {"startRow": 1, "endRow": None, "maxRows": 100},
            )

            if "error" in table_data:
                return TableData.failure(str(table_data["error"]))

            rows = []
            for row_data in table_data.get("rows", []):
                cells = None
                if "cells" in row_data and row_data["cells"]:
                    cells = {
                        col: AlvCellInfo(
                            selector=info["selector"],
                            clickable=info.get("clickable", False),
                            hotspot=info.get("hotspot", False),
                        )
                        for col, info in row_data["cells"].items()
                    }
                rows.append(
                    TableRow(
                        row=row_data["row"],
                        data=row_data["data"],
                        cells=cells,
                    )
                )

            alv = None
            if "alv" in table_data and table_data["alv"]:
                alv_data = table_data["alv"]
                alv = AlvMetadata(
                    table_id=alv_data["table_id"],
                    selection_mode=alv_data.get("selection_mode", "NONE"),
                    hotspot_columns=alv_data.get("hotspot_columns", []),
                    column_map=alv_data.get("column_map", {}),
                )

            return TableData(
                headers=table_data.get("headers", []),
                rows=rows,
                total_rows=table_data.get("totalRows", 0),
                start_row=table_data.get("startRow", 1),
                end_row=table_data.get("endRow"),
                alv=alv,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Reading table")
            return TableData.failure(f"Error reading table: {e}")

    async def click_table_cell(self, row: int, column: int | str, action: str = "click") -> TableCellClickResult:
        """Click a cell in the current ALV grid table."""
        try:
            result = await self._page.evaluate(
                load_js("click_table_cell.js"),
                {"row": row, "column": column, "action": action, "performClick": False},
            )

            if "error" in result:
                return TableCellClickResult.failure(
                    str(result["error"]),
                    row=row,
                    column=column,
                    selector_used="",
                )

            selector = result["selector"]

            if action == "dblclick":
                await self._page.dblclick(selector)
            else:
                await self._page.click(selector)

            await asyncio.sleep(0.5)
            await self._page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(0.3)

            title = await self._page.title()
            return TableCellClickResult(
                row=row,
                column=result.get("column", column),
                selector_used=selector,
                page_title=title,
                was_hotspot=result.get("wasHotspot", False),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Clicking table cell")
            return TableCellClickResult.failure(
                f"Error clicking table cell: {e}",
                row=row,
                column=column,
                selector_used="",
            )

    async def get_dropdown_options(self, label: str) -> list[str]:
        """Get available options for a dropdown field by label."""
        field_check = await self._page.evaluate(load_js("check_field_type.js"), label)
        if not field_check.get("found") or not field_check.get("isDropdown"):
            return []
        element_id = field_check.get("elementId")
        if not element_id:
            return []
        try:
            result = await self._page.evaluate(load_js("get_dropdown_options.js"), element_id)
            if result.get("success"):
                return list(result.get("options", []))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Getting dropdown options for %r", label)
        return []

    async def _fetch_dropdown_options(self) -> list[DropdownInfo]:
        """Fetch options for all dropdown fields on the current page."""
        raw_fields = await self._page.evaluate(load_js("detect_form_fields.js"))
        dropdown_fields = [f for f in raw_fields if f.get("field_type") == "dropdown"]

        dropdowns: list[DropdownInfo] = []
        for field in dropdown_fields:
            element_id, label = field.get("id"), field.get("label", "")
            if not element_id:
                continue
            try:
                result = await self._page.evaluate(load_js("get_dropdown_options.js"), element_id)
                if result.get("success"):
                    dropdowns.append(
                        DropdownInfo(
                            id=element_id,
                            label=label,
                            options=result.get("options", []),
                        )
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Getting dropdown options for %r", element_id)
        return dropdowns

    # ===================================================================
    # SapEditor
    # ===================================================================

    async def read_editor_source(self) -> str | None:
        """Read the current source code from the SAP editor textarea."""
        from playwright.async_api import Error as PlaywrightError  # pylint: disable=import-outside-toplevel

        try:
            textarea = self._page.locator("textarea[id*='textedit']").first
            if not await textarea.is_visible(timeout=3000):
                return None
            return await textarea.input_value()
        except (PlaywrightError, OSError) as exc:
            logger.warning("Could not read editor content: %s", exc)
            return None

    async def replace_editor_source(self, code: str) -> bool:
        """Replace the entire editor content with new source code."""
        from playwright.async_api import Error as PlaywrightError  # pylint: disable=import-outside-toplevel

        try:
            textarea = self._page.locator("textarea[id*='textedit']").first
            await textarea.click()
            await self._page.keyboard.press("Control+a")
            await self._page.wait_for_timeout(200)
            await self._page.keyboard.press("Delete")
            await self._page.wait_for_timeout(200)
            await textarea.fill(code)
            return True
        except (PlaywrightError, OSError) as exc:
            logger.warning("Failed to replace editor source: %s", exc)
            return False

    async def check_and_activate(self) -> CheckActivateResult:
        """Run syntax check (Ctrl+F2) and activation (Ctrl+F3)."""
        messages: list[str] = []

        await self._page.keyboard.press("Control+F2")
        await self._page.wait_for_timeout(2000)
        await self._page.wait_for_load_state("networkidle")

        snapshot = await self._page.locator("body").aria_snapshot()
        check_ok, check_msg = _parse_toolbar_note(snapshot)
        messages.append(f"Check: {check_msg}")

        if not check_ok:
            return CheckActivateResult(success=False, messages=messages, activated=False)

        await self._page.keyboard.press("Control+F3")
        await self._page.wait_for_timeout(2000)
        await self._page.wait_for_load_state("networkidle")

        snapshot = await self._page.locator("body").aria_snapshot()

        # Handle "Inaktive Objekte" / "Inactive Objects" popup
        if "Inaktive Objekte" in snapshot or "Inactive Objects" in snapshot:
            logger.info("Detected inactive objects popup, confirming with Enter")
            await self._page.keyboard.press("Enter")
            await self._page.wait_for_timeout(2000)
            await self._page.wait_for_load_state("networkidle")
            snapshot = await self._page.locator("body").aria_snapshot()

        activate_ok, activate_msg = _parse_toolbar_note(snapshot)
        messages.append(f"Activate: {activate_msg}")

        return CheckActivateResult(success=activate_ok, messages=messages, activated=activate_ok)

    # ===================================================================
    # SapPopup
    # ===================================================================

    async def check_popup(self) -> PopupInfo | None:
        """Fast check for blocking popup dialog."""
        result = await self._page.evaluate(load_js("check_popup.js"))
        if result is None:
            return None

        buttons = [
            PopupButton(
                label=btn["label"],
                accesskey=btn.get("accesskey"),
                id=btn.get("id"),
            )
            for btn in result.get("buttons", [])
        ]

        return PopupInfo(
            message=result.get("message"),
            buttons=buttons,
            close_button_id=result.get("close_button_id"),
        )

    async def dismiss_popup(  # pylint: disable=too-many-branches
        self,
        button_label: str | None = None,
        use_close_button: bool = False,
    ) -> ClosePopupResult:
        """Dismiss an active popup dialog."""
        try:
            popup = await self.check_popup()
            if popup is None:
                return ClosePopupResult.failure("No popup to close")

            clicked_label: str
            if use_close_button:
                if not popup.has_close_button:
                    return ClosePopupResult.failure("No close button available")
                await self._page.click(_escape_css_selector(f"#{popup.close_button_id}"))
                clicked_label = "[X]"
            elif not button_label:
                return ClosePopupResult.failure("Specify button_label or use_close_button=True")
            else:
                button_lower = button_label.lower()
                matched_button: PopupButton | None = None

                for btn in popup.buttons:
                    if btn.label.lower() == button_lower:
                        matched_button = btn
                        break
                    if btn.accesskey and btn.accesskey.lower() == button_lower:
                        matched_button = btn
                        break

                if not matched_button:
                    available = [b.label for b in popup.buttons]
                    return ClosePopupResult.failure(f"Button '{button_label}' not found. Available: {available}")

                if matched_button.id:
                    await self._page.click(_escape_css_selector(f"#{matched_button.id}"))
                elif matched_button.accesskey:
                    await self._page.keyboard.press(f"Alt+{matched_button.accesskey}")
                else:
                    await self._page.click(f"button:has-text('{matched_button.label}')")
                clicked_label = matched_button.label

            await self._page.wait_for_timeout(500)
            popup_after = await self.check_popup()

            status_info = await self._page.evaluate(load_js("extract_status_bar.js"))

            return ClosePopupResult(
                button_clicked=clicked_label,
                popup_closed=popup_after is None,
                status_bar_type=status_info.get("type", "none"),
                status_bar_message=status_info.get("message", ""),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Dismissing popup")
            return ClosePopupResult.failure(f"Error dismissing popup: {e}")
