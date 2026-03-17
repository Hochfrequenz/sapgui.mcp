"""Desktop backend — SAP GUI Scripting (COM) implementation of SapUiBackend.

Bridges the async MCP protocol to synchronous COM calls via a dedicated
ComThread. Methods that don't apply to desktop (JS, CSS selectors) raise
NotImplementedError.
"""

# pylint: disable=broad-exception-caught,too-many-public-methods,too-many-lines

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

import sapwebguimcp.sapgui._login as _login_mod
from sapwebguimcp.backend.desktop._com_thread import ComThread
from sapwebguimcp.backend.desktop._session_registry import DesktopSessionRegistry

#: Per-async-task session ID — set by BackendManager before each tool call.
#: MUST be read on the async side (in _require_session), NEVER inside a ComThread lambda.
_current_session_id: ContextVar[str | None] = ContextVar("_current_session_id", default=None)
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

    Manages multiple GuiSession objects via ``DesktopSessionRegistry``.
    A ``ContextVar`` (set by ``BackendManager``) determines which session
    is used for each async task.  All COM calls are dispatched to a shared
    ``ComThread`` for apartment-threading safety.
    """

    def __init__(self, com_thread: ComThread | None = None) -> None:
        self._com = com_thread or ComThread()
        self._registry = DesktopSessionRegistry()

    @property
    def _session(self) -> GuiSession | None:
        """Backward compat: return primary session (s1)."""
        try:
            return self._registry.get_session("s1")
        except ValueError:
            return None

    def _require_session(self) -> GuiSession:
        """Return the session for the current async context.

        Reads ``_current_session_id`` ContextVar to determine which session.
        Defaults to ``'s1'`` if no ContextVar is set (backward compat).
        """
        session_id = _current_session_id.get()
        return self._registry.get_session(session_id)  # None → "s1"

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
            self._registry.register(session)  # → "s1"
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
        """Open a transaction in a new session/mode (/o).

        Returns ``(registry_session_id, session_count, page_title)``.
        The session ID is a registry ID like ``'s2'``, not a COM path.
        """
        session = self._require_session()

        try:
            await self._com.run(session.create_session)
            await asyncio.sleep(1)

            def _navigate() -> tuple[Any, int, str | None]:
                from sapwebguimcp.sapgui._factory import wrap_com_object  # pylint: disable=import-outside-toplevel

                conn_com = session.com.Parent
                count = conn_com.Children.Count
                if count < 2:
                    return None, count, None
                new_ses_com = conn_com.Children(count - 1)
                new_gui_session = wrap_com_object(new_ses_com)
                # Enter transaction in new session
                new_ses_com.FindById("wnd[0]/tbar[0]/okcd").Text = f"/n{tcode}"
                new_ses_com.FindById("wnd[0]").SendVKey(0)
                title = str(new_ses_com.FindById("wnd[0]").Text)
                return new_gui_session, count, title

            result_session, count, title = await self._com.run(_navigate)
            if result_session is None:
                return None, count, None
            session_id = self._registry.register(result_session)
            logger.info("open_session", extra={"tcode": tcode, "session_id": session_id, "count": count})
            return session_id, count, title
        except Exception:
            logger.exception("open_session")
            return None, 1, None

    async def list_sessions(self) -> list[SessionInfo]:
        """List all sessions from the registry with their COM properties."""
        result: list[SessionInfo] = []
        for sid in self._registry.list_sessions():
            try:
                ses = self._registry.get_session(sid)

                def _info(s: Any = ses) -> dict[str, str]:
                    return {
                        "tcode": str(s.com.Info.Transaction),
                        "title": str(s.com.FindById("wnd[0]").Text),
                    }

                info = await self._com.run(_info)
                result.append(
                    SessionInfo(
                        session_id=sid,
                        is_primary=(sid == "s1"),
                        agent_id=self._registry.get_bound_agent(sid),
                        **info,
                    )
                )
            except (ValueError, Exception):  # pylint: disable=broad-exception-caught
                logger.warning("Skipping session %s in listing (COM error)", sid)
        return result

    async def close_session(self, session_id: str) -> bool:
        """Close a session by registry ID (e.g. 's2')."""
        if not self._registry.has_session(session_id):
            return False
        try:
            target = self._registry.get_session(session_id)
            primary = self._registry.get_session("s1")

            def _close(t: Any = target, p: Any = primary) -> bool:
                # Get COM ID on the COM thread (Id property requires COM context)
                com_id = str(t.com.Id)
                conn = p.com.Parent
                conn.CloseSession(com_id)
                return True

            result = await self._com.run(_close)
        except Exception:  # pylint: disable=broad-exception-caught
            result = False
        self._registry.unregister(session_id)
        logger.info("close_session", extra={"session_id": session_id, "success": result})
        return result

    async def bind_session(self, session_id: str, agent_id: str) -> str | None:
        """Bind an agent to a session."""
        prev = self._registry.get_bound_agent(session_id)
        self._registry.bind(session_id, agent_id)
        return prev

    async def release_session(self, session_id: str) -> str | None:
        """Release agent binding from a session."""
        prev = self._registry.get_bound_agent(session_id)
        self._registry.release(session_id)
        return prev

    async def has_session(self, session_id: str) -> bool:
        """Check whether a session exists in the registry."""
        return self._registry.has_session(session_id)

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
        for sid in list(self._registry.list_sessions()):
            self._registry.unregister(sid)
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

            # Find grid or table in the full window tree (not just usr).
            # SE16N places ALV grids in wnd[0]/shellcont, not wnd[0]/usr.
            wnd = session.find_by_id("wnd[0]")
            tree = cast(Any, wnd).dump_tree(max_depth=5)
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

            wnd = session.find_by_id("wnd[0]")
            tree = cast(Any, wnd).dump_tree(max_depth=5)
            for elem in _flatten(tree):
                if elem.type_as_number == 122:
                    grid = session.find_by_id(elem.id)
                    if isinstance(grid, GuiGridView):
                        col_name = str(column)
                        if isinstance(column, int):
                            col_order = cast(Any, grid).column_order
                            col_name = str(col_order(column))
                        if action in ("dblclick", "double_click"):
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
        """Focus and type into an element by accessible name or field name.

        Tries multiple strategies:
        1. Direct find_by_id with common prefixes (fast, works for field names like GD-TAB)
        2. find_field_by_label (label text matching, slower)
        """
        session = self._require_session()

        def _type() -> bool:
            # Strategy 1: try direct find_by_id with common prefixes (fast)
            for prefix in ("txt", "ctxt", "pwd", "cmb"):
                try:
                    field = session.find_by_id(f"wnd[0]/usr/{prefix}{accessible_name}", raise_error=False)
                    if field is not None:
                        cast(Any, field).text = text
                        logger.debug(
                            "focus_and_type_found",
                            extra={"field_name": accessible_name, "strategy": "direct", "prefix": prefix},
                        )
                        return True
                except Exception as exc:
                    logger.debug(
                        "focus_and_type_error",
                        extra={"field_name": accessible_name, "prefix": prefix, "error": str(exc)},
                    )
            # Strategy 2: label-based search (slower)
            field = find_field_by_label(session, accessible_name)
            if field is None:
                return False
            cast(Any, field).text = text
            return True

        result = await self._com.run(_type)
        logger.info("focus_and_type", extra={"field_name": accessible_name, "found": result})
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

    # ---- SapEditor ----

    @staticmethod
    def _find_editor_shell_raw(session: Any) -> tuple[Any, str] | None:
        """Find an AbapEditor or TextEdit shell via raw COM.

        Returns ``(raw_com_shell, sub_type)`` or ``None``.
        Uses raw COM ``FindById`` to avoid pysapgui wrapper issues
        with ``GuiAbapEditor`` property access.
        """
        raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
        usr = session.find_by_id("wnd[0]/usr")
        tree = cast(Any, usr).dump_tree(max_depth=5)
        for elem in _flatten(tree):
            if elem.type_as_number == 122:  # GuiShell
                shell = session.find_by_id(elem.id)
                sub_type = getattr(cast(Any, shell), "sub_type", "")
                if sub_type in ("AbapEditor", "TextEdit"):
                    # Extract relative ID (wnd[0]/...) from full path (/app/con[N]/ses[N]/wnd[0]/...)
                    full_id = elem.id
                    wnd_idx = full_id.find("wnd[")
                    relative_id = full_id[wnd_idx:] if wnd_idx >= 0 else full_id
                    raw_shell = raw_session.FindById(relative_id, False)
                    if raw_shell is None:
                        raw_shell = getattr(shell, "com", getattr(shell, "_com", shell))
                    return raw_shell, sub_type
        return None

    async def read_editor_source(self) -> str | None:
        """Read the current source code from an open ABAP editor.

        Walks the element tree to find a ``GuiAbapEditor`` or ``GuiTextedit``
        and reads all lines via the raw COM ``GetLineCount`` / ``GetLineText``
        interface.
        """
        session = self._require_session()

        def _read() -> str | None:
            result = DesktopBackend._find_editor_shell_raw(session)
            if result is None:
                return None
            raw_shell, sub_type = result
            # GuiAbapEditor: GetLineCount() + GetLineText(i) on raw COM
            try:
                num_lines = raw_shell.GetLineCount()
                lines = [raw_shell.GetLineText(i) for i in range(num_lines)]
                return "\n".join(lines)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("read_editor_source: GetLineCount/GetLineText failed", extra={"sub_type": sub_type})
            # GuiTextedit fallback: NumberOfLines + GetLineText
            try:
                num_lines = raw_shell.NumberOfLines
                lines = [str(raw_shell.GetLineText(i)) for i in range(num_lines)]
                return "\n".join(lines)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "read_editor_source",
                    extra={"sub_type": sub_type, "error": "Could not read lines from editor"},
                )
            return None

        source = await self._com.run(_read)
        logger.info("read_editor_source", extra={"found": source is not None})
        return source

    async def replace_editor_source(self, code: str) -> bool:
        """Replace the entire source code in an open ABAP editor.

        For ``GuiAbapEditor``: SelectRange + Delete + InsertText.
        For ``GuiTextedit``: sets the ``Text`` property directly.
        """
        session = self._require_session()

        def _replace() -> bool:
            import time  # pylint: disable=import-outside-toplevel

            result = DesktopBackend._find_editor_shell_raw(session)
            if result is None:
                return False
            raw_shell, sub_type = result
            # GuiAbapEditor: SelectRange + Delete + InsertText(text, line, col).
            # SelectRange(startLine, startCol, endLine, endCol) creates a proper
            # selection that Delete() respects (unlike SelectAll which doesn't).
            # InsertText signature: (text: str, line: int, col: int) — undocumented.
            # InsertText drops the last segment after \n, so append \n to the code.
            max_col = 9999  # SAP clamps to actual line length
            if sub_type == "AbapEditor":
                try:
                    # Clear: SelectRange all + Delete, repeated because the first
                    # pass may leave a residual empty line that still has content
                    # in the editor buffer.
                    for _ in range(2):
                        cnt = raw_shell.GetLineCount()
                        raw_shell.SelectRange(0, 0, cnt - 1, max_col)
                        time.sleep(0.1)
                        raw_shell.Delete()
                        time.sleep(0.1)
                    # Insert new code (trailing \n ensures last line is included)
                    insert_code = code if code.endswith("\n") else code + "\n"
                    raw_shell.InsertText(insert_code, 0, 0)
                    time.sleep(0.2)
                    return True
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.warning("replace_editor_source AbapEditor failed: %s", exc)
                    return False
            # GuiTextedit: set Text property
            try:
                raw_shell.Text = code
                return True
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "replace_editor_source",
                    extra={"sub_type": sub_type, "error": "Text property unavailable"},
                )
            return False

        replaced = await self._com.run(_replace)
        logger.info("replace_editor_source", extra={"success": replaced, "length": len(code)})
        return replaced

    async def check_and_activate(self) -> CheckActivateResult:
        """Run syntax check (Ctrl+F2) and activate (Ctrl+F3).

        Sends VKey 26 (check), reads status bar, handles "Inactive Objects"
        popup, then sends VKey 27 (activate) and reads status bar again.
        """
        from sapwebguimcp.backend.protocol import CheckActivateResult as _CheckActivateResult

        session = self._require_session()

        def _check_activate() -> tuple[list[str], bool]:
            wnd = session.find_by_id("wnd[0]")
            messages: list[str] = []

            # Check (Ctrl+F2 = VKey 26)
            cast(Any, wnd).send_v_key(26)
            sbar = session.find_by_id("wnd[0]/sbar")
            msg = str(cast(Any, sbar).text)
            check_type = str(cast(Any, sbar).message_type)
            if msg:
                messages.append(f"Check: {msg}")

            # If check failed, return early without activating
            if check_type == "E":
                return messages, False

            # Handle "Inactive Objects" popup if it appears
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is not None:
                cast(Any, popup).send_v_key(0)  # Confirm with Enter

            # Activate (Ctrl+F3 = VKey 27)
            cast(Any, wnd).send_v_key(27)
            sbar = session.find_by_id("wnd[0]/sbar")
            msg = str(cast(Any, sbar).text)
            msg_type = str(cast(Any, sbar).message_type)
            if msg:
                messages.append(f"Activate: {msg}")

            # Handle "Inactive Objects" popup again
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is not None:
                cast(Any, popup).send_v_key(0)

            activated = msg_type != "E"
            return messages, activated

        try:
            messages, activated = await self._com.run(_check_activate)
            logger.info(
                "check_and_activate",
                extra={"activated": activated, "message_count": len(messages)},
            )
            return _CheckActivateResult(success=True, messages=messages, activated=activated)
        except Exception as e:
            logger.warning("check_and_activate", extra={"error": str(e)})
            return _CheckActivateResult(success=False, error=str(e), messages=[], activated=False)

    async def dismiss_language_dialog(self) -> None:
        """Dismiss the 'Different original and logon languages' dialog if present.

        Checks for modal wnd[1] containing "originalsprache" or "original"/"language"
        text, and presses Enter to confirm.
        """
        session = self._require_session()

        def _dismiss() -> bool:
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is None:
                return False
            text = str(cast(Any, popup).text).lower()
            if "originalsprache" in text or ("original" in text and "language" in text):
                cast(Any, popup).send_v_key(0)  # Enter to confirm
                return True
            return False

        dismissed = await self._com.run(_dismiss)
        logger.info("dismiss_language_dialog", extra={"dismissed": dismissed})

    # ---- SapPopup ----

    async def check_popup(self) -> PopupInfo | None:
        """Detect whether a popup/dialog is currently visible.

        Checks if wnd[1] exists, then reads its title, text content,
        and button labels to build a PopupInfo.
        """
        from sapwebguimcp.models.base import PopupButton, PopupType

        session = self._require_session()

        def _check() -> dict[str, Any] | None:
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is None:
                return None
            title = str(cast(Any, popup).text)
            # Collect elements from the popup
            tree = cast(Any, popup).dump_tree(max_depth=2)
            flat = _flatten(tree)
            buttons: list[dict[str, str | None]] = []
            for elem in flat:
                if elem.type_as_number == 40 and elem.text.strip():  # GuiButton
                    buttons.append({"label": elem.text.strip(), "id": elem.id})
            # Collect text content (labels and text fields)
            texts: list[str] = []
            for elem in flat:
                if elem.type_as_number in (30, 31) and elem.text.strip():
                    texts.append(elem.text.strip())
            message = " ".join(texts) if texts else title
            return {"title": title, "message": message, "buttons": buttons}

        data = await self._com.run(_check)
        if data is None:
            logger.debug("check_popup", extra={"found": False})
            return None

        # Determine popup type from title/message heuristics
        popup_type = PopupType.UNKNOWN
        msg_lower = (data["message"] or "").lower()
        title_lower = (data["title"] or "").lower()
        combined = msg_lower + " " + title_lower
        if any(kw in combined for kw in ("error", "fehler")):
            popup_type = PopupType.ERROR
        elif any(kw in combined for kw in ("information", "hinweis")):
            popup_type = PopupType.INFO
        elif any(kw in combined for kw in ("confirm", "bestätigung", "ja", "nein", "yes", "no")):
            popup_type = PopupType.CONFIRM

        popup_buttons = [PopupButton(label=b["label"], id=b.get("id")) for b in data["buttons"]]
        logger.info(
            "check_popup",
            extra={"found": True, "type": popup_type, "button_count": len(popup_buttons)},
        )
        return PopupInfo(
            popup_type=popup_type,
            message=data["message"],
            buttons=popup_buttons,
        )

    async def dismiss_popup(self, button_label: str | None = None, use_close_button: bool = False) -> ClosePopupResult:
        """Dismiss a popup by clicking a button or the close control.

        If use_close_button is True, closes the popup window directly.
        If button_label is given, finds and clicks the matching button.
        Otherwise, presses Enter (VKey 0) as default.
        """
        from sapwebguimcp.models.sap_results import ClosePopupResult as _ClosePopupResult

        session = self._require_session()

        def _dismiss() -> dict[str, Any]:
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is None:
                return {"dismissed": False, "button_clicked": None}

            if use_close_button:
                cast(Any, popup).close()
                return {"dismissed": True, "button_clicked": None}

            if button_label:
                # Find button by label in popup
                tree = cast(Any, popup).dump_tree(max_depth=2)
                for elem in _flatten(tree):
                    if elem.type_as_number == 40 and button_label.lower() in elem.text.lower():
                        btn = session.find_by_id(elem.id)
                        cast(Any, btn).press()
                        return {"dismissed": True, "button_clicked": elem.text.strip()}

            # Default: press Enter
            cast(Any, popup).send_v_key(0)
            return {"dismissed": True, "button_clicked": None}

        try:
            data = await self._com.run(_dismiss)
            # Read status bar after dismissal
            sbar_text = ""
            sbar_type: StatusBarType = "none"
            if data["dismissed"]:
                try:

                    def _read_sbar() -> tuple[str, str]:
                        sbar = session.find_by_id("wnd[0]/sbar")
                        return str(cast(Any, sbar).text), str(cast(Any, sbar).message_type)

                    sbar_text, raw_type = await self._com.run(_read_sbar)
                    if raw_type == "A":
                        raw_type = "E"  # map Abort to Error
                    if raw_type in ("S", "E", "W", "I"):
                        sbar_type = cast(StatusBarType, raw_type)
                except Exception:
                    pass

            logger.info(
                "dismiss_popup",
                extra={
                    "dismissed": data["dismissed"],
                    "button": data["button_clicked"],
                    "use_close": use_close_button,
                },
            )
            return _ClosePopupResult(
                success=data["dismissed"],
                error=None if data["dismissed"] else "No popup found",
                button_clicked=data["button_clicked"],
                popup_closed=data["dismissed"],
                status_bar_type=sbar_type,
                status_bar_message=sbar_text,
            )
        except Exception as e:
            logger.warning("dismiss_popup", extra={"error": str(e)})
            return _ClosePopupResult(
                success=False,
                error=str(e),
                popup_closed=False,
            )
