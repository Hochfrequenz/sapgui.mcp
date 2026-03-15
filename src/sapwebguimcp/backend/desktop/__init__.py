"""Desktop backend — SAP GUI Scripting (COM) implementation of SapUiBackend.

Bridges the async MCP protocol to synchronous COM calls via a dedicated
ComThread. Methods that don't apply to desktop (JS, CSS selectors) raise
NotImplementedError.
"""

# pylint: disable=broad-exception-caught,too-many-public-methods

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import TYPE_CHECKING, Any, cast

import sapwebguimcp.sapgui._login as _login_mod
from sapwebguimcp.backend.desktop._com_thread import ComThread
from sapwebguimcp.backend.desktop._element_finder import (
    _flatten,
    find_button_by_label,
    find_checkbox_by_label,
    find_combobox_by_label,
    find_field_by_label,
    find_radio_by_label,
    find_tab_by_label,
)
from sapwebguimcp.backend.desktop._key_mapping import key_to_vkey
from sapwebguimcp.backend.types import ComTreeSnapshot
from sapwebguimcp.models.alv_models import TableCellClickResult
from sapwebguimcp.models.base import PopupInfo, ToolResult
from sapwebguimcp.models.sap_results import (
    ButtonInfo,
    FieldFillError,
    FieldInfo,
    FormField,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SessionInfo,
    SessionStatus,
    StatusBarInfo,
    StatusBarType,
    TableData,
    TableRow,
    TransactionResult,
)

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import CheckActivateResult
    from sapwebguimcp.models.sap_results import (
        ClosePopupResult,
        DropdownFillResult,
        FillFormResult,
        FormFieldsResult,
    )
    from sapwebguimcp.sapgui.components.session import GuiSession

logger = logging.getLogger(__name__)


class DesktopBackend:
    """SapUiBackend implementation using SAP GUI Scripting (COM).

    Each instance wraps one GuiSession. All COM calls are dispatched
    to a shared ComThread for apartment-threading safety.
    """

    def __init__(self, com_thread: ComThread | None = None) -> None:
        self._com = com_thread or ComThread()
        self._session: GuiSession | None = None
        self._agent_bindings: dict[str, str] = {}  # session_id -> agent_id

    def _require_session(self) -> GuiSession:
        """Return the current session or raise."""
        if self._session is None:
            raise RuntimeError("Not logged in — call login() first")
        return self._session

    # ---- SapNavigation ----

    async def login(  # pylint: disable=unused-argument,too-many-arguments,too-many-positional-arguments
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
        session_id: str | None = None,
    ) -> LoginResult:
        """Log into SAP GUI desktop (url is ignored — uses SAP_CONNECTION_NAME)."""
        from sapwebguimcp.models.config import get_settings  # pylint: disable=import-outside-toplevel

        settings = get_settings()
        connection_name = settings.sap_connection_name
        if not connection_name:
            return LoginResult(success=False, error="SAP_CONNECTION_NAME not configured")

        try:
            session = await self._com.run(
                lambda: _login_mod.login(
                    connection_name=connection_name,
                    client=client,
                    user=username,
                    password=password,
                    language=language,
                )
            )
            self._session = session
            user_name = await self._com.run(lambda: str(session.info.user))
            logger.info(
                "login",
                extra={"connection": connection_name, "user": user_name, "success": True},
            )
            return LoginResult(success=True, user=user_name)
        except Exception as e:
            logger.warning(
                "login",
                extra={"connection": connection_name, "user": username, "success": False, "error": str(e)},
            )
            return LoginResult(success=False, error=str(e))

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        """Navigate to a transaction code."""
        session = self._require_session()

        def _enter() -> str:
            okcd = session.find_by_id("wnd[0]/tbar[0]/okcd")
            cast(Any, okcd).text = f"/n{tcode}"
            wnd = session.find_by_id("wnd[0]")
            cast(Any, wnd).send_v_key(0)
            return str(cast(Any, session.find_by_id("wnd[0]")).text)

        try:
            title = await self._com.run(_enter)
            logger.info("transaction", extra={"tcode": tcode, "title": title, "success": True})
            return TransactionResult(
                success=True,
                tcode=tcode,
                page_title=title,
            )
        except Exception as e:
            logger.warning("transaction", extra={"tcode": tcode, "success": False, "error": str(e)})
            return TransactionResult(success=False, tcode=tcode, error=str(e))

    async def get_session_status(self) -> SessionStatus:
        """Check whether the SAP session is logged in and responsive."""
        if self._session is None:
            return SessionStatus(success=True, status="logged_off", message="Not logged in")
        session = self._session
        try:
            user = await self._com.run(lambda: str(session.info.user))
            return SessionStatus(success=True, status="active", message=f"Logged in as {user}")
        except Exception:
            return SessionStatus(success=True, status="unknown", message="Session not responsive")

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        """Wait until the session is no longer busy."""
        session = self._require_session()
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while asyncio.get_running_loop().time() < deadline:
            busy = await self._com.run(lambda: bool(session.busy))
            if not busy:
                return
            await asyncio.sleep(0.2)

    async def bring_to_front(self) -> None:
        """Bring the SAP GUI window to the foreground."""
        session = self._require_session()
        await self._com.run(
            lambda: (
                cast(Any, session.find_by_id("wnd[0]")).iconify(),
                cast(Any, session.find_by_id("wnd[0]")).restore(),
            )
        )

    async def wait(self, timeout_ms: int = 200) -> None:
        """Wait for a fixed duration."""
        await asyncio.sleep(timeout_ms / 1000)

    async def start_keepalive(self, interval_seconds: int = 300) -> None:
        """No-op — desktop sessions don't time out like WebGUI."""

    async def stop_keepalive(self) -> bool:
        """No-op. Returns False (no keepalive was running)."""
        return False

    async def open_new_session(self, tcode: str) -> tuple[str | None, int, str | None]:
        """Open a transaction in a new session/mode (/o)."""
        session = self._require_session()

        try:
            await self._com.run(session.create_session)
            await asyncio.sleep(1)

            def _navigate() -> tuple[str | None, int, str | None]:
                conn_com = session.com.Parent
                count = conn_com.Children.Count
                if count < 2:
                    return None, count, None
                new_ses_com = conn_com.Children(count - 1)
                new_id = str(new_ses_com.Id)
                # Enter transaction in new session
                new_ses_com.FindById("wnd[0]/tbar[0]/okcd").Text = f"/n{tcode}"
                new_ses_com.FindById("wnd[0]").SendVKey(0)
                title = str(new_ses_com.FindById("wnd[0]").Text)
                return new_id, count, title

            sid, count, title = await self._com.run(_navigate)
            logger.info("open_session", extra={"tcode": tcode, "session_id": sid, "count": count})
            return sid, count, title
        except Exception:
            logger.exception("open_session")
            return None, 1, None

    async def list_sessions(self) -> list[SessionInfo]:
        """List all sessions in the current connection."""
        session = self._require_session()

        def _list() -> list[dict[str, Any]]:
            conn = session.com.Parent
            result = []
            for i in range(conn.Children.Count):
                ses = conn.Children(i)
                result.append(
                    {
                        "session_id": str(ses.Id),
                        "tcode": str(ses.Info.Transaction),
                        "title": str(ses.FindById("wnd[0]").Text),
                        "is_primary": i == 0,
                    }
                )
            return result

        raw_items = await self._com.run(_list)
        # Add agent bindings on the main thread (not on the COM thread)
        for item in raw_items:
            item["agent_id"] = self._agent_bindings.get(item["session_id"])
        return [SessionInfo(**item) for item in raw_items]

    async def close_session(self, session_id: str) -> bool:
        """Close a session by ID."""
        session = self._require_session()

        def _close() -> bool:
            conn = session.com.Parent
            try:
                conn.CloseSession(session_id)
                return True
            except Exception:
                return False

        result = await self._com.run(_close)
        logger.info("close_session", extra={"session_id": session_id, "success": result})
        return result

    async def bind_session(self, session_id: str, agent_id: str) -> str | None:
        """Bind an agent to a session."""
        prev = self._agent_bindings.get(session_id)
        self._agent_bindings[session_id] = agent_id
        return prev

    async def release_session(self, session_id: str) -> str | None:
        """Release agent binding from a session."""
        return self._agent_bindings.pop(session_id, None)

    async def has_session(self, session_id: str) -> bool:
        """Check whether a session exists."""
        session = self._require_session()

        def _check() -> bool:
            conn = session.com.Parent
            for i in range(conn.Children.Count):
                if str(conn.Children(i).Id) == session_id:
                    return True
            return False

        return await self._com.run(_check)

    async def is_page_closed(self) -> bool:
        """Check whether the session has been closed."""
        if self._session is None:
            return True
        session = self._session  # capture to local for closure safety
        try:
            await self._com.run(lambda: session.info.user)
            return False
        except Exception:
            logger.debug("session_closed")
            return True

    async def close_page(self) -> None:
        """Close the connection."""
        if self._session is None:
            return
        try:
            session = self._session
            await self._com.run(
                lambda: cast(Any, session).com.Parent.CloseConnection()  # pylint: disable=unnecessary-lambda
            )
        except Exception:
            pass
        self._session = None
        logger.info("close_connection")

    def get_session_token(self) -> str:
        """Return opaque token identifying the session."""
        if self._session is None:
            return ""
        return str(self._session.id)

    # ---- SapUiInspection ----

    async def get_status_bar(self) -> StatusBarInfo:
        """Read the SAP status bar."""
        session = self._require_session()

        def _read() -> tuple[str, str]:
            sbar = session.find_by_id("wnd[0]/sbar")
            return str(cast(Any, sbar).text), str(cast(Any, sbar).message_type)

        text, msg_type = await self._com.run(_read)
        bar_type: StatusBarType = cast(StatusBarType, msg_type) if msg_type in ("S", "E", "W", "I", "A") else "none"
        logger.debug("status_bar", extra={"type": bar_type, "message": text})
        return StatusBarInfo(success=True, type=bar_type, message=text)

    async def get_screen_info(self) -> ScreenInfo:
        """Get technical screen information."""
        session = self._require_session()

        def _read() -> dict[str, Any]:
            info = session.info
            wnd = session.find_by_id("wnd[0]")
            return {
                "transaction": str(info.transaction),
                "title": str(cast(Any, wnd).text),
                "program": str(info.program),
                "dynpro": str(info.screen_number),
            }

        data = await self._com.run(_read)
        return ScreenInfo(success=True, url="desktop://sap", **data)

    async def get_screen_text(  # pylint: disable=unused-argument
        self, include_dropdown_options: bool = False
    ) -> ScreenText:
        """Get readable text from the current screen via dump_tree."""
        session = self._require_session()

        def _read() -> dict[str, Any]:
            wnd = session.find_by_id("wnd[0]")
            title = str(cast(Any, wnd).text)
            sbar = session.find_by_id("wnd[0]/sbar")
            sbar_text = str(cast(Any, sbar).text)
            tree = cast(Any, wnd).dump_tree(max_depth=3)

            labels, buttons, tabs, content = [], [], [], []
            for elem in _flatten(tree):
                t = elem.type_as_number
                txt = elem.text.strip()
                if not txt:
                    continue
                if t == 30:  # GuiLabel
                    labels.append(txt)
                elif t == 40:  # GuiButton
                    buttons.append(txt)
                elif t == 91:  # GuiTab
                    tabs.append(txt)
                else:
                    content.append(txt)

            return {
                "title": title,
                "status_bar": sbar_text or None,
                "tabs": tabs,
                "labels": list(dict.fromkeys(labels)),
                "buttons": list(dict.fromkeys(buttons)),
                "table_headers": [],
                "main_content": content,
            }

        data = await self._com.run(_read)
        return ScreenText(success=True, **data)

    async def discover_fields(self) -> list[FieldInfo]:
        """Discover input fields on the current screen."""
        session = self._require_session()

        def _discover() -> list[dict[str, Any]]:
            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            fields = []
            input_types = {31, 32, 33, 34}  # txt, ctxt, pwd, cmb
            for elem in _flatten(tree):
                if elem.type_as_number in input_types:
                    fields.append(
                        {
                            "id": elem.id,
                            "name": elem.name,
                            "label": None,
                            "type": elem.type,
                            "selector": elem.id,
                            "value": elem.text,
                        }
                    )
            return fields

        items = await self._com.run(_discover)
        logger.debug("discover_fields", extra={"count": len(items)})
        return [FieldInfo(**item) for item in items]

    async def get_form_fields(  # pylint: disable=unused-argument
        self, *, include_dropdown_options: bool = False
    ) -> FormFieldsResult:
        """Detect form fields with their current values and associated labels."""
        from sapwebguimcp.models.sap_results import (
            FormFieldsResult as _FormFieldsResult,  # pylint: disable=import-outside-toplevel
        )

        session = self._require_session()

        def _discover() -> list[dict[str, Any]]:
            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=5)
            flat = _flatten(tree)

            # Build label map: name -> label text
            label_map: dict[str, str] = {}
            for elem in flat:
                if elem.type_as_number == 30 and elem.text.strip():  # GuiLabel
                    label_map[elem.name] = elem.text.strip()

            # Type number to SapFieldType mapping
            type_map = {
                31: "text",  # GuiTextField
                32: "text",  # GuiCTextField
                33: "text",  # GuiPasswordField
                34: "dropdown",  # GuiComboBox
                42: "checkbox",  # GuiCheckBox
                41: "radio",  # GuiRadioButton
            }

            fields: list[dict[str, Any]] = []
            for elem in flat:
                if elem.type_as_number not in type_map:
                    continue
                field_type = type_map[elem.type_as_number]
                label_text = label_map.get(elem.name, elem.name)
                field_dict: dict[str, Any] = {
                    "id": elem.id,
                    "label": label_text,
                    "field_type": field_type,
                    "current_value": elem.text if elem.text else None,
                }
                if field_type in ("checkbox", "radio"):
                    field_dict["checked"] = bool(elem.text)
                fields.append(field_dict)
            return fields

        items = await self._com.run(_discover)
        logger.debug("get_form_fields", extra={"count": len(items)})
        return _FormFieldsResult(
            success=True,
            fields=[FormField(**item) for item in items],
        )

    async def discover_buttons(self) -> list[ButtonInfo]:
        """Discover clickable buttons on the current screen."""
        session = self._require_session()

        def _discover() -> list[dict[str, Any]]:
            wnd = session.find_by_id("wnd[0]")
            tree = cast(Any, wnd).dump_tree(max_depth=3)
            buttons: list[dict[str, Any]] = []
            for elem in _flatten(tree):
                if elem.type_as_number == 40 and elem.text.strip():  # GuiButton
                    buttons.append({"label": elem.text.strip(), "id": elem.id, "selector": elem.id})
            return buttons

        items = await self._com.run(_discover)
        logger.debug("discover_buttons", extra={"count": len(items)})
        return [ButtonInfo(**item) for item in items]

    async def get_snapshot(self) -> ComTreeSnapshot:
        """Get a text dump of the SAP GUI element tree.

        Returns ComTreeSnapshot — an indented tree of element types, names,
        and text values from dump_tree(). This is NOT an ARIA snapshot.
        Used for LLM context, not structured parsing.
        """
        session = self._require_session()

        def _dump() -> str:
            wnd = session.find_by_id("wnd[0]")
            tree = cast(Any, wnd).dump_tree(max_depth=5)
            lines = []
            for elem in _flatten(tree):
                indent = "  " * elem.id.count("/")
                lines.append(f"{indent}{elem.type}[{elem.name}]: {elem.text!r}")
            return "\n".join(lines)

        text = await self._com.run(_dump)
        return ComTreeSnapshot(text)

    async def take_screenshot(self) -> bytes:
        """Take a screenshot of the SAP GUI window."""
        session = self._require_session()

        def _screenshot() -> bytes:
            wnd = session.find_by_id("wnd[0]")
            tmp = os.path.join(tempfile.gettempdir(), "sapgui_screenshot.png")
            cast(Any, wnd).hard_copy(tmp, 2)  # 2 = PNG
            with open(tmp, "rb") as f:
                data = f.read()
            os.unlink(tmp)
            return data

        try:
            result = await self._com.run(_screenshot)
            logger.debug("screenshot", extra={"bytes": len(result)})
            return result
        except Exception:
            logger.exception("screenshot")
            raise

    async def read_table(
        self,
        start_row: int = 1,
        end_row: int | None = None,
        max_rows: int = 100,
    ) -> TableData:
        """Read data from an ALV grid or table control."""
        session = self._require_session()

        def _read() -> dict[str, Any]:  # pylint: disable=too-many-locals
            from sapwebguimcp.sapgui.components.grid import GuiGridView  # pylint: disable=import-outside-toplevel

            # Find grid or table in the user area
            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            grid_id = None
            for elem in _flatten(tree):
                if elem.type_as_number in (122, 80):
                    grid_id = elem.id
                    break

            if grid_id is None:
                return {"headers": [], "rows": [], "total_rows": 0, "start_row": 1}

            grid = session.find_by_id(grid_id)
            if isinstance(grid, GuiGridView):
                row_count = cast(Any, grid).row_count
                col_order = cast(Any, grid).column_order
                headers = []
                for ci in range(col_order.Count):
                    col_name = str(col_order(ci))
                    headers.append(col_name)

                actual_end = min(end_row or (start_row + max_rows - 1), row_count)
                rows = []
                for ri in range(start_row - 1, actual_end):
                    data = {}
                    for col_name in headers:
                        data[col_name] = str(cast(Any, grid).get_cell_value(ri, col_name))
                    rows.append({"row": ri + 1, "data": data})

                return {
                    "headers": headers,
                    "rows": rows,
                    "total_rows": row_count,
                    "start_row": start_row,
                    "end_row": actual_end,
                }

            return {"headers": [], "rows": [], "total_rows": 0, "start_row": 1}

        try:
            data = await self._com.run(_read)
        except Exception:
            logger.exception("read_table")
            raise
        rows = [TableRow(**r) for r in data.pop("rows", [])]
        logger.debug(
            "read_table",
            extra={"rows": len(rows), "start": data.get("start_row"), "end": data.get("end_row")},
        )
        return TableData(success=True, rows=rows, **data)

    async def click_table_cell(self, row: int, column: int | str, action: str = "click") -> TableCellClickResult:
        """Click a cell in an ALV grid table."""
        session = self._require_session()

        def _click() -> None:
            from sapwebguimcp.sapgui.components.grid import GuiGridView  # pylint: disable=import-outside-toplevel

            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            for elem in _flatten(tree):
                if elem.type_as_number == 122:
                    grid = session.find_by_id(elem.id)
                    if isinstance(grid, GuiGridView):
                        col_name = str(column)
                        if isinstance(column, int):
                            col_order = cast(Any, grid).column_order
                            col_name = str(col_order(column))
                        if action == "double_click":
                            cast(Any, grid).double_click(row - 1, col_name)
                        else:
                            cast(Any, grid).click(row - 1, col_name)
                        return
            raise ValueError("No ALV grid found on screen")

        try:
            await self._com.run(_click)
            return TableCellClickResult(success=True, row=row, column=str(column), selector_used="com")
        except Exception as e:
            return TableCellClickResult(success=False, row=row, column=str(column), selector_used="com", error=str(e))

    async def get_dropdown_options(self, label: str) -> list[str]:  # pylint: disable=unused-argument
        """Get options from a dropdown (not yet implemented — needs element finder)."""
        return []

    async def get_page_title(self) -> str:
        """Get the current window title."""
        session = self._require_session()
        return await self._com.run(lambda: str(cast(Any, session.find_by_id("wnd[0]")).text))

    # ---- SapUiPrimitives (only press_key in Phase 1) ----

    async def press_key(self, key: str) -> KeyboardResult:
        """Send a keyboard shortcut via SAP VKey."""
        session = self._require_session()
        try:
            vkey = key_to_vkey(key)
        except KeyError:
            return KeyboardResult(success=False, key=key, error=f"Unknown key: {key}")

        def _press() -> tuple[str, str, str]:
            wnd = session.find_by_id("wnd[0]")
            cast(Any, wnd).send_v_key(vkey)
            title = str(cast(Any, session.find_by_id("wnd[0]")).text)
            sbar = session.find_by_id("wnd[0]/sbar")
            return title, str(cast(Any, sbar).text), str(cast(Any, sbar).message_type)

        try:
            title, sbar_text, sbar_type = await self._com.run(_press)
            resolved_type: StatusBarType = (
                cast(StatusBarType, sbar_type) if sbar_type in ("S", "E", "W", "I", "A") else "none"
            )
            logger.debug("press_key", extra={"key": key, "vkey": vkey, "title": title})
            return KeyboardResult(
                success=True,
                key=key,
                page_title=title,
                status_bar_read=True,
                status_bar_type=resolved_type,
                status_bar_message=sbar_text,
            )
        except Exception as e:
            return KeyboardResult(success=False, key=key, error=str(e))

    # ---- Stub methods (Phase 2 + 3) ----

    async def fill_field(self, label: str, value: str) -> None:
        """Fill a labelled input field."""
        session = self._require_session()

        def _fill() -> None:
            field = find_field_by_label(session, label)
            if field is None:
                raise ValueError(f"Field not found: {label}")
            cast(Any, field).text = value

        await self._com.run(_fill)
        logger.info("fill_field", extra={"label": label, "value": value})

    async def fill_main_input(self, value: str, labels: list[str]) -> bool:
        """Fill the main form input — try each label, fill first match."""
        session = self._require_session()

        def _fill() -> bool:
            for lbl in labels:
                field = find_field_by_label(session, lbl)
                if field is not None:
                    cast(Any, field).text = value
                    return True
            return False

        result = await self._com.run(_fill)
        logger.info("fill_main_input", extra={"value": value, "found": result})
        return result

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult:
        """Fill multiple form fields."""
        from sapwebguimcp.models.sap_results import (
            FillFormResult as _FillFormResult,  # pylint: disable=import-outside-toplevel
        )

        session = self._require_session()

        def _fill() -> dict[str, Any]:
            filled: list[str] = []
            not_found: list[str] = []
            errors: list[dict[str, str]] = []
            for label, value in fields.items():
                try:
                    field = find_field_by_label(session, label)
                    if field is None:
                        not_found.append(label)
                        continue
                    cast(Any, field).text = value
                    filled.append(label)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    errors.append({"field": label, "error": str(exc)})
            return {"filled": filled, "not_found": not_found, "errors": errors}

        data = await self._com.run(_fill)
        logger.info(
            "fill_form",
            extra={"filled": len(data["filled"]), "not_found": len(data["not_found"]), "errors": len(data["errors"])},
        )
        has_failures = len(data["not_found"]) > 0 or len(data["errors"]) > 0
        error_msg = None
        if has_failures:
            parts = []
            if data["not_found"]:
                parts.append(f"Fields not found: {', '.join(data['not_found'])}")
            if data["errors"]:
                parts.append(f"Errors: {', '.join(e['field'] for e in data['errors'])}")
            error_msg = "; ".join(parts)
        return _FillFormResult(
            success=not has_failures,
            error=error_msg,
            filled=data["filled"],
            not_found=data["not_found"],
            errors=[FieldFillError(**e) for e in data["errors"]],
        )

    async def fill_grid_cell(self, row: int, column: int | str, value: str) -> None:
        """Fill a grid/table cell."""
        session = self._require_session()

        def _fill() -> None:
            from sapwebguimcp.sapgui.components.grid import GuiGridView  # pylint: disable=import-outside-toplevel

            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            for elem in _flatten(tree):
                if elem.type_as_number in (122, 80):
                    grid = session.find_by_id(elem.id)
                    if isinstance(grid, GuiGridView):
                        col_name = str(column)
                        if isinstance(column, int):
                            col_order = cast(Any, grid).column_order
                            col_name = str(col_order(column))
                        cast(Any, grid).set_cell_value(row - 1, col_name, value)
                        return
            raise ValueError("No ALV grid found on screen")

        await self._com.run(_fill)
        logger.info("fill_grid_cell", extra={"row": row, "column": column, "value": value})

    async def click_button(self, label: str) -> None:
        """Click a button by label."""
        session = self._require_session()

        def _click() -> None:
            btn = find_button_by_label(session, label)
            if btn is None:
                raise ValueError(f"Button not found: {label}")
            cast(Any, btn).press()

        await self._com.run(_click)
        logger.info("click_button", extra={"label": label})

    async def click_tab(self, label: str) -> None:
        """Click a tab by label."""
        session = self._require_session()

        def _click() -> None:
            tab = find_tab_by_label(session, label)
            if tab is None:
                raise ValueError(f"Tab not found: {label}")
            cast(Any, tab).select()

        await self._com.run(_click)
        logger.info("click_tab", extra={"label": label})

    async def type_text(self, text: str) -> None:
        """Type text into the focused element."""
        session = self._require_session()

        def _type() -> None:
            wnd = session.find_by_id("wnd[0]")
            focus_elem = cast(Any, wnd).focused_element
            if focus_elem is not None:
                focus_elem.text = text
            else:
                raise ValueError("No focused element found")

        await self._com.run(_type)
        logger.info("type_text", extra={"length": len(text)})

    async def set_checkbox(self, label: str, checked: bool) -> None:
        """Set a checkbox by label."""
        session = self._require_session()

        def _set() -> None:
            chk = find_checkbox_by_label(session, label)
            if chk is None:
                raise ValueError(f"Checkbox not found: {label}")
            cast(Any, chk).selected = checked

        await self._com.run(_set)
        logger.info("set_checkbox", extra={"label": label, "checked": checked})

    async def set_radio_button(self, label: str) -> None:
        """Select a radio button by label."""
        session = self._require_session()

        def _set() -> None:
            rad = find_radio_by_label(session, label)
            if rad is None:
                raise ValueError(f"Radio button not found: {label}")
            cast(Any, rad).selected = True

        await self._com.run(_set)
        logger.info("set_radio_button", extra={"label": label})

    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult:
        """Select a dropdown option."""
        from sapwebguimcp.models.sap_results import (
            DropdownFillResult as _DropdownFillResult,  # pylint: disable=import-outside-toplevel
        )

        session = self._require_session()

        def _select() -> dict[str, Any]:
            cmb = find_combobox_by_label(session, label)
            if cmb is None:
                # Also try find_field_by_label as fallback
                cmb = find_field_by_label(session, label)
            if cmb is None:
                return {"success": False, "error_message": f"Dropdown not found: {label}"}
            try:
                cast(Any, cmb).value = option
                return {"success": True}
            except Exception as exc:  # pylint: disable=broad-exception-caught
                return {"success": False, "error_message": str(exc)}

        data = await self._com.run(_select)
        logger.info("select_dropdown", extra={"label": label, "option": option, "success": data["success"]})
        return _DropdownFillResult(**data)

    async def focus_and_type(  # pylint: disable=unused-argument
        self, accessible_name: str, text: str, delay_ms: int = 0
    ) -> bool:
        """Focus and type into an element by name."""
        session = self._require_session()

        def _type() -> bool:
            field = find_field_by_label(session, accessible_name)
            if field is None:
                return False
            cast(Any, field).text = text
            return True

        result = await self._com.run(_type)
        logger.info("focus_and_type", extra={"name": accessible_name, "found": result})
        return result

    async def fill_element_by_locator(self, locator: str, value: str, delay_ms: int = 30) -> bool:
        """Fill element by CSS selector — not supported on desktop."""
        raise NotImplementedError("CSS selectors not supported on desktop SAP GUI")

    async def click_element(self, selector: str) -> bool:
        """Click element by CSS selector — not supported on desktop."""
        raise NotImplementedError("CSS selectors not supported on desktop SAP GUI")

    def load_js(self, filename: str) -> str:
        """Load JavaScript helper — not supported on desktop."""
        raise NotImplementedError("JavaScript not supported on desktop SAP GUI")

    async def evaluate_javascript(self, script: str, arg: Any = None) -> Any:
        """Evaluate JavaScript — not supported on desktop."""
        raise NotImplementedError("JavaScript not supported on desktop SAP GUI")

    # ---- SapEditor stubs (Phase 3) ----

    async def read_editor_source(self) -> str | None:
        """Read ABAP editor source (not yet implemented)."""
        raise NotImplementedError("read_editor_source not yet implemented — Phase 3")

    async def replace_editor_source(self, code: str) -> bool:
        """Replace ABAP editor source (not yet implemented)."""
        raise NotImplementedError("replace_editor_source not yet implemented — Phase 3")

    async def check_and_activate(self) -> CheckActivateResult:
        """Run syntax check and activate (not yet implemented)."""
        raise NotImplementedError("check_and_activate not yet implemented — Phase 3")

    async def dismiss_language_dialog(self) -> None:
        """Dismiss language mismatch dialog (not yet implemented)."""
        raise NotImplementedError("dismiss_language_dialog not yet implemented — Phase 3")

    # ---- SapPopup stubs (Phase 3) ----

    async def check_popup(self) -> PopupInfo | None:
        """Detect popup/dialog (not yet implemented)."""
        raise NotImplementedError("check_popup not yet implemented — Phase 3")

    async def dismiss_popup(self, button_label: str | None = None, use_close_button: bool = False) -> ClosePopupResult:
        """Dismiss a popup (not yet implemented)."""
        raise NotImplementedError("dismiss_popup not yet implemented — Phase 3")
