"""Protocol definitions for the SAP UI backend abstraction.

Five focused sub-protocols combined into one ``SapUiBackend`` type.
Tools depend on ``SapUiBackend``; implementations (e.g. ``WebGuiBackend``)
satisfy it via structural typing — no inheritance required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import Field

# Import from specific submodules to avoid circular import through models/__init__.py.
# Only ToolResult needed at runtime (CheckActivateResult subclass).
# All other model types are used only in annotations (resolved as strings via PEP 563).
from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.models.base import PopupInfo, ToolResult

if TYPE_CHECKING:
    from sapwebguimcp.models.alv_models import TableCellClickResult
    from sapwebguimcp.models.sap_results import (
        ButtonInfo,
        ClosePopupResult,
        DropdownFillResult,
        FieldInfo,
        FillFormResult,
        FormFieldsResult,
        KeyboardResult,
        LoginResult,
        ScreenInfo,
        ScreenText,
        SessionStatus,
        StatusBarInfo,
        TableData,
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

    async def fill_main_input(self, value: str, labels: list[str]) -> bool:
        """Fill the main form input, skipping toolbar/combobox inputs."""

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult:
        """Fill multiple form fields at once."""

    async def fill_grid_cell(self, row: int, column: int | str, value: str) -> None:
        """Fill a grid/table cell by row index and column identifier."""

    async def click_button(self, label: str) -> None:
        """Click a button identified by its label text."""

    async def click_tab(self, label: str) -> None:
        """Click a tab identified by its label text."""

    async def press_key(self, key: str) -> KeyboardResult:
        """Send a keyboard shortcut (e.g. ``F5``, ``Ctrl+S``, ``Enter``)."""

    async def type_text(self, text: str) -> None:
        """Type text into the currently focused element."""

    async def set_checkbox(self, label: str, checked: bool) -> None:
        """Set a checkbox by its ARIA label. Raises ``ValueError`` if not found."""

    async def set_radio_button(self, label: str) -> None:
        """Select a radio button by its ARIA label. Raises ``ValueError`` if not found."""

    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult:
        """Select an option from a dropdown field."""

    async def evaluate_javascript(self, script: str) -> Any:
        """Evaluate a JavaScript expression in the browser and return the result."""


@runtime_checkable
class SapUiInspection(Protocol):
    """Read state from the SAP UI."""

    async def get_status_bar(self) -> StatusBarInfo:
        """Read the SAP status bar message."""

    async def get_screen_info(self) -> ScreenInfo:
        """Get technical screen information (program, transaction)."""

    async def get_screen_text(self, include_dropdown_options: bool = False) -> ScreenText:
        """Get all readable text from the current screen."""

    async def discover_fields(self) -> list[FieldInfo]:
        """Discover input fields on the current screen."""

    async def get_form_fields(self, *, include_dropdown_options: bool = False) -> FormFieldsResult:
        """Detect form fields with their current values and types."""

    async def discover_buttons(self) -> list[ButtonInfo]:
        """Discover clickable buttons on the current screen."""

    async def get_snapshot(self) -> AriaSnapshot:
        """Get an ARIA accessibility snapshot of the page."""

    async def take_screenshot(self) -> bytes:
        """Take a screenshot of the current page as PNG bytes."""

    async def read_table(
        self,
        start_row: int = 1,
        end_row: int | None = None,
        max_rows: int = 100,
    ) -> TableData:
        """Read data from an ALV grid or table on the screen."""

    async def click_table_cell(self, row: int, column: int | str, action: str = "click") -> TableCellClickResult:
        """Click a cell in an ALV grid table."""

    async def get_dropdown_options(self, label: str) -> list[str]:
        """Get available options for a dropdown field."""

    async def get_page_title(self) -> str:
        """Get the current page/window title."""


@runtime_checkable
class SapNavigation(Protocol):
    """Navigation and session lifecycle."""

    async def login(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
    ) -> LoginResult:
        """Log into SAP Web GUI."""

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        """Navigate to a transaction code."""

    async def get_session_status(self) -> SessionStatus:
        """Check whether the SAP session is logged in and responsive."""

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        """Wait until the SAP page has finished loading."""

    async def bring_to_front(self) -> None:
        """Bring the SAP browser window to the foreground."""

    async def wait(self, timeout_ms: int = 200) -> None:
        """Wait for a fixed duration (e.g. to let popups render)."""


@runtime_checkable
class SapEditor(Protocol):
    """Source code editor operations (SE38/SE24/SE37 editors)."""

    async def read_editor_source(self) -> str | None:
        """Read the current source code from an open ABAP editor."""

    async def replace_editor_source(self, code: str) -> bool:
        """Replace the entire source code in an open ABAP editor."""

    async def check_and_activate(self) -> CheckActivateResult:
        """Run syntax check (Ctrl+F2) and activate (Ctrl+F3)."""

    async def dismiss_language_dialog(self) -> None:
        """Dismiss the 'Different original and logon languages' dialog if present."""


@runtime_checkable
class SapPopup(Protocol):
    """Popup/dialog detection and handling."""

    async def check_popup(self) -> PopupInfo | None:
        """Detect whether a popup/dialog is currently visible."""

    async def dismiss_popup(
        self,
        button_label: str | None = None,
        use_close_button: bool = False,
    ) -> ClosePopupResult:
        """Dismiss a popup by clicking a button or the close control."""


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
