"""Protocol definitions for the SAP UI backend abstraction.

Five focused sub-protocols combined into one ``SapUiBackend`` type.
Tools depend on ``SapUiBackend``; implementations (e.g. ``WebGuiBackend``)
satisfy it via structural typing — no inheritance required.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.models import (
    ButtonInfo,
    ClosePopupResult,
    DropdownFillResult,
    FieldInfo,
    FillFormResult,
    FormFieldsResult,
    KeyboardResult,
    LoginResult,
    PopupInfo,
    ScreenInfo,
    ScreenText,
    SessionStatus,
    StatusBarInfo,
    TableCellClickResult,
    TableData,
    ToolResult,
    TransactionResult,
)


class CheckActivateResult(ToolResult):
    """Result of a check-and-activate editor operation."""

    messages: list[str] = Field(
        default_factory=list,
        description="Check and activate status messages",
    )
    activated: bool = Field(
        default=False,
        description="Whether the object was successfully activated",
    )


# ---------------------------------------------------------------------------
# Sub-protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class SapUiPrimitives(Protocol):
    """Low-level UI interaction — fill, click, type, press."""

    async def fill_field(self, label: str, value: str) -> None:
        """Fill a labelled input field. Raises ``ValueError`` on failure."""
        ...

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult: ...

    async def fill_grid_cell(self, row: int, column: int | str, value: str) -> None: ...

    async def click_button(self, label: str) -> None: ...

    async def click_tab(self, label: str) -> None: ...

    async def press_key(self, key: str) -> KeyboardResult: ...

    async def type_text(self, text: str) -> None: ...

    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult: ...


@runtime_checkable
class SapUiInspection(Protocol):
    """Read state from the SAP UI."""

    async def get_status_bar(self) -> StatusBarInfo: ...

    async def get_screen_info(self) -> ScreenInfo: ...

    async def get_screen_text(self, include_dropdown_options: bool = False) -> ScreenText: ...

    async def discover_fields(self) -> list[FieldInfo]: ...

    async def get_form_fields(self) -> FormFieldsResult: ...

    async def discover_buttons(self) -> list[ButtonInfo]: ...

    async def get_snapshot(self) -> AriaSnapshot: ...

    async def take_screenshot(self) -> bytes: ...

    async def read_table(self) -> TableData: ...

    async def click_table_cell(self, row: int, column: int | str, action: str = "click") -> TableCellClickResult: ...

    async def get_dropdown_options(self, label: str) -> list[str]: ...


@runtime_checkable
class SapNavigation(Protocol):
    """Navigation and session lifecycle."""

    async def login(
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
    ) -> LoginResult: ...

    async def enter_transaction(self, tcode: str) -> TransactionResult: ...

    async def get_session_status(self) -> SessionStatus: ...

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None: ...

    async def bring_to_front(self) -> None: ...


@runtime_checkable
class SapEditor(Protocol):
    """Source code editor operations (SE38/SE24/SE37 editors)."""

    async def read_editor_source(self) -> str | None: ...

    async def replace_editor_source(self, code: str) -> bool: ...

    async def check_and_activate(self) -> CheckActivateResult: ...


@runtime_checkable
class SapPopup(Protocol):
    """Popup/dialog detection and handling."""

    async def check_popup(self) -> PopupInfo | None: ...

    async def dismiss_popup(
        self,
        button_label: str | None = None,
        use_close_button: bool = False,
    ) -> ClosePopupResult: ...


@runtime_checkable
class SapUiBackend(
    SapUiPrimitives,
    SapUiInspection,
    SapNavigation,
    SapEditor,
    SapPopup,
    Protocol,
):
    """Combined protocol — the single type that tools depend on."""

    ...
