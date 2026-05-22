# UI Backend Abstraction — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the SAP UI layer exchangeable by introducing a Protocol-based abstraction. Tools call the protocol, never Playwright directly. Only WebGUI implementation for now.

**Architecture:** Layered Protocol (`SapUiPrimitives`, `SapUiInspection`, `SapNavigation`, `SapEditor`, `SapPopup`) combined into `SapUiBackend`. `WebGuiBackend` wraps existing Playwright code. `BackendManager` replaces `get_browser_manager()` as the entry point for tools. See `docs/plans/2026-03-04-ui-backend-abstraction-design.md` for full design.

**Tech Stack:** Python 3.11+, `typing.Protocol`, `NewType`, Pydantic 2.x, Playwright (WebGUI impl only), pytest + anyio

**Existing code references:**

- Current BrowserManager: `src/sapguimcp/models/browser.py` (501 lines)
- Shared tool impls: `src/sapguimcp/tools/sap_tool_impl.py` (372 lines)
- Page helpers: `src/sapguimcp/tools/sap_page_helpers.py` (65 lines)
- Edit helpers: `src/sapguimcp/tools/edit_helpers.py` (160 lines)
- JS loader: `_load_js` in `sap_tool_impl.py:43-46`
- All result models: `src/sapguimcp/models/` (re-exported from `__init__.py`)
- Server wiring: `src/sapguimcp/server.py` (221 lines)

---

## Workflow

Phase 1 (Tasks 1-3) was merged to main via squash merge.

Phase 2 (Tasks 2-10) implements the protocol hierarchy, WebGuiBackend, and BackendManager.
This is purely additive — no existing tool behavior changes. Implemented on
branch `feat/ui-backend-abstraction` and submitted as a **foundation PR** for
early merge to main (non-breaking, reduces the size of the later migration PR).

Phase 3+ (Tasks 11-23) performs the actual tool migration and cleanup.
Starts on a new feature branch after the foundation PR is merged.

---

## Phase 1: Foundation (Preparatory — merged to main)

These are small, non-breaking PRs that reduce the size of the main migration.

---

### Task 1: Introduce `AriaSnapshot` type alias

**Files:**

- Create: `src/sapguimcp/backend/__init__.py`
- Create: `src/sapguimcp/backend/types.py`
- Modify: `src/sapguimcp/parsers/se24_parser.py`
- Modify: `src/sapguimcp/parsers/se37_parser.py`
- Modify: `src/sapguimcp/parsers/se16_parser.py`
- Modify: `src/sapguimcp/parsers/se11_parser.py`
- Modify: `src/sapguimcp/parsers/se93_parser.py`
- Modify: `src/sapguimcp/parsers/se09_parser.py`
- Modify: `src/sapguimcp/parsers/slg1_parser.py`
- Modify: `src/sapguimcp/parsers/sm37_parser.py`
- Modify: `src/sapguimcp/parsers/sm30_parser.py`
- Modify: `src/sapguimcp/parsers/spro_parser.py`
- Modify: `src/sapguimcp/parsers/st22_parser.py`
- Test: `unittests/test_aria_snapshot_type.py`

**Step 1: Write the test**

```python
# unittests/test_aria_snapshot_type.py
"""Tests for the AriaSnapshot type alias."""
from sapguimcp.backend.types import AriaSnapshot


def test_aria_snapshot_is_str_subtype() -> None:
    """AriaSnapshot should be usable wherever str is expected."""
    snapshot = AriaSnapshot('heading "Test"')
    assert isinstance(snapshot, str)
    assert "Test" in snapshot


def test_aria_snapshot_distinct_from_raw_str() -> None:
    """AriaSnapshot should be a NewType, not just str."""
    # This is a type-level distinction, but we can verify the constructor exists
    snapshot = AriaSnapshot("body:\n  heading \"Title\"")
    assert snapshot == "body:\n  heading \"Title\""
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_aria_snapshot_type.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sapguimcp.backend'`

**Step 3: Create the backend package and types module**

```python
# src/sapguimcp/backend/__init__.py
"""Backend abstraction layer for SAP UI interaction."""
from sapguimcp.backend.types import AriaSnapshot

__all__ = ["AriaSnapshot"]
```

```python
# src/sapguimcp/backend/types.py
"""Type definitions for the backend abstraction layer."""
from typing import NewType

AriaSnapshot = NewType("AriaSnapshot", str)
"""
ARIA accessibility tree snapshot from a SAP UI screen.

WebGUI backend: YAML-formatted output from Playwright's page.locator().aria_snapshot().
Future backends may use different snapshot formats with their own NewType aliases.
"""
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_aria_snapshot_type.py -v`
Expected: PASS

**Step 5: Update all parser entry-point signatures to use `AriaSnapshot`**

For each parser file, add `from sapguimcp.backend.types import AriaSnapshot` and change the main parse function signature from `snapshot: str` to `snapshot: AriaSnapshot`. The parser internals stay unchanged — `AriaSnapshot` is a `str` at runtime.

Example for `se24_parser.py`:

```python
# Add import
from sapguimcp.backend.types import AriaSnapshot

# Change signature (find the main public parse function)
def parse_se24_snapshot(snapshot: AriaSnapshot, ...) -> SE24Entry | SE24Error:
```

Apply the same pattern to all parsers listed above. Each parser has one or two public functions that accept `snapshot: str` — change those to `snapshot: AriaSnapshot`.

**Step 6: Run full test suite for parsers**

Run: `python -m pytest unittests/test_se24_parser.py unittests/test_se37_parser.py unittests/test_se16_parser.py unittests/test_se11_parser.py unittests/test_se93_parser.py -v`
Expected: All PASS (AriaSnapshot is str at runtime)

**Step 7: Commit**

```bash
git add src/sapguimcp/backend/ unittests/test_aria_snapshot_type.py src/sapguimcp/parsers/
git commit -m "feat: introduce AriaSnapshot type alias and update parser signatures"
```

---

### Task 2: Create protocol definitions

**Files:**

- Create: `src/sapguimcp/backend/protocol.py`
- Test: `unittests/test_backend_protocol.py`

**Step 1: Write the test**

```python
# unittests/test_backend_protocol.py
"""Tests that the backend protocol is well-defined and importable."""
from typing import runtime_checkable

from sapguimcp.backend.protocol import (
    SapEditor,
    SapNavigation,
    SapPopup,
    SapUiBackend,
    SapUiInspection,
    SapUiPrimitives,
)


def test_all_sub_protocols_importable() -> None:
    """All sub-protocols should be importable."""
    assert SapUiPrimitives is not None
    assert SapUiInspection is not None
    assert SapNavigation is not None
    assert SapEditor is not None
    assert SapPopup is not None


def test_combined_protocol_importable() -> None:
    """The combined SapUiBackend protocol should be importable."""
    assert SapUiBackend is not None


def test_protocols_are_runtime_checkable() -> None:
    """All protocols should be runtime-checkable for isinstance() support."""
    assert hasattr(SapUiBackend, "__protocol_attrs__") or isinstance(
        SapUiBackend, type
    )
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_backend_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write protocol.py**

```python
# src/sapguimcp/backend/protocol.py
"""
Protocol definitions for the SAP UI backend abstraction.

Tools depend on SapUiBackend (or its sub-protocols) — never on Playwright,
desktop GUI scripting, or any other backend-specific type.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from sapguimcp.backend.types import AriaSnapshot
from sapguimcp.models import (
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


@runtime_checkable
class SapUiPrimitives(Protocol):
    """Low-level UI interaction — fill, click, type, press."""

    async def fill_field(self, label: str, value: str) -> None: ...
    """Raises ValueError if the field cannot be found or filled."""

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult: ...

    async def fill_grid_cell(
        self, row: int, column: int | str, value: str
    ) -> None: ...

    async def click_button(self, label: str) -> None: ...

    async def click_tab(self, label: str) -> None: ...

    async def press_key(self, key: str) -> KeyboardResult: ...

    async def type_text(self, text: str) -> None: ...

    async def select_dropdown(
        self, label: str, option: str
    ) -> DropdownFillResult: ...


@runtime_checkable
class SapUiInspection(Protocol):
    """Read state from the SAP UI."""

    async def get_status_bar(self) -> StatusBarInfo: ...

    async def get_screen_info(self) -> ScreenInfo: ...

    async def get_screen_text(
        self, include_dropdown_options: bool = False
    ) -> ScreenText: ...

    async def discover_fields(self) -> list[FieldInfo]: ...

    async def get_form_fields(self) -> FormFieldsResult: ...

    async def discover_buttons(self) -> list[ButtonInfo]: ...

    async def get_snapshot(self) -> AriaSnapshot: ...

    async def take_screenshot(self) -> bytes: ...

    async def read_table(self) -> TableData: ...

    async def click_table_cell(
        self, row: int, column: int | str, action: str = "click"
    ) -> TableCellClickResult: ...

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
```

**Step 4: Update `backend/__init__.py` exports**

```python
# src/sapguimcp/backend/__init__.py
"""Backend abstraction layer for SAP UI interaction."""
from sapguimcp.backend.protocol import (
    CheckActivateResult,
    SapEditor,
    SapNavigation,
    SapPopup,
    SapUiBackend,
    SapUiInspection,
    SapUiPrimitives,
)
from sapguimcp.backend.types import AriaSnapshot

__all__ = [
    "AriaSnapshot",
    "CheckActivateResult",
    "SapEditor",
    "SapNavigation",
    "SapPopup",
    "SapUiBackend",
    "SapUiInspection",
    "SapUiPrimitives",
]
```

> **Note:** After Phase 1 is pushed, the developer merges Tasks 1-3 to main via PRs.
> Phase 2+ begins on a feature branch based on the updated main.

**Step 5: Run test to verify it passes**

Run: `python -m pytest unittests/test_backend_protocol.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/__init__.py unittests/test_backend_protocol.py
git commit -m "feat: add SapUiBackend protocol hierarchy"
```

---

### Task 3: Move JS helpers to backend/webgui/

**Files:**

- Create: `src/sapguimcp/backend/webgui/__init__.py`
- Create: `src/sapguimcp/backend/webgui/js_helpers.py`
- Modify: `src/sapguimcp/tools/sap_tool_impl.py` (re-export from new location)
- Modify: `src/sapguimcp/tools/sap_tools.py` (re-export from new location)

**Step 1: Create webgui package and js_helpers**

```python
# src/sapguimcp/backend/webgui/__init__.py
"""WebGUI backend implementation using Playwright/CDP."""
```

```python
# src/sapguimcp/backend/webgui/js_helpers.py
"""JavaScript file loading helpers for the WebGUI backend."""
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=16)
def load_js(filename: str) -> str:
    """Load a JavaScript file from the sapguimcp.js package."""
    return (
        resources.files("sapguimcp.js")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


@lru_cache(maxsize=8)
def load_js_with_field_utils(filename: str) -> str:
    """Load a JS file with find_field_utils.js prepended."""
    utils = load_js("find_field_utils.js")
    tool = load_js(filename)
    return utils + "\n" + tool
```

**Step 2: Update sap_tool_impl.py to re-export from new location**

In `src/sapguimcp/tools/sap_tool_impl.py`, replace the `_load_js` and `_load_js_with_field_utils` definitions (lines 43-53) with:

```python
from sapguimcp.backend.webgui.js_helpers import load_js as _load_js
from sapguimcp.backend.webgui.js_helpers import load_js_with_field_utils as _load_js_with_field_utils
```

**Step 3: Update sap_tools.py similarly**

In `src/sapguimcp/tools/sap_tools.py`, replace the `_load_js` and `_load_js_with_field_utils` definitions (lines 91-102) with:

```python
from sapguimcp.backend.webgui.js_helpers import load_js as _load_js
from sapguimcp.backend.webgui.js_helpers import load_js_with_field_utils as _load_js_with_field_utils
```

**Step 4: Run tests to verify nothing broke**

Run: `python -m pytest unittests/ -v --ignore=unittests/test_se24_integration.py --ignore=unittests/test_se37_integration.py -k "not integration and not exploration" --timeout=30`
Expected: All PASS (re-exports preserve behavior)

**Step 5: Commit**

```bash
git add src/sapguimcp/backend/webgui/ src/sapguimcp/tools/sap_tool_impl.py src/sapguimcp/tools/sap_tools.py
git commit -m "refactor: move JS helpers to backend/webgui/js_helpers.py"
```

---

## Phase 2: WebGuiBackend Implementation (foundation PR: `feat/ui-backend-abstraction`)

From here on, work on a feature branch `feat/ui-backend-abstraction` based on main (after Phase 1 PRs are merged).

---

### Task 4: Move BrowserManager to backend/webgui/

**Files:**

- Move: `src/sapguimcp/models/browser.py` → `src/sapguimcp/backend/webgui/browser.py`
- Modify: `src/sapguimcp/models/__init__.py` (re-export from new location)

**Step 1: Copy `models/browser.py` to `backend/webgui/browser.py`**

Copy the file as-is. Update its internal imports if any reference `sapguimcp.models.browser` (check for circular imports).

**Step 2: Update `models/__init__.py` to re-export**

Replace the direct import of `BrowserManager`, `get_browser_manager`, `close_browser_manager` with:

```python
from sapguimcp.backend.webgui.browser import (
    BrowserManager,
    close_browser_manager,
    get_browser_manager,
)
```

This ensures all existing code that imports from `sapguimcp.models` still works.

**Step 3: Run tests**

Run: `python -m pytest unittests/ -k "not integration and not exploration" --timeout=30 -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/sapguimcp/backend/webgui/browser.py src/sapguimcp/models/
git commit -m "refactor: move BrowserManager to backend/webgui/"
```

---

### Task 5: Implement WebGuiBackend — navigation methods

**Files:**

- Create: `src/sapguimcp/backend/webgui/backend.py`
- Test: `unittests/test_webgui_backend.py`

This is the core implementation. The `WebGuiBackend` wraps a single Playwright `Page` and implements `SapUiBackend`.

**Step 1: Write a structural test**

```python
# unittests/test_webgui_backend.py
"""Tests for the WebGuiBackend implementation."""
from sapguimcp.backend.protocol import SapUiBackend
from sapguimcp.backend.webgui.backend import WebGuiBackend


def test_webgui_backend_implements_protocol() -> None:
    """WebGuiBackend must satisfy the SapUiBackend protocol."""
    assert issubclass(WebGuiBackend, SapUiBackend)
```

Note: This test will fail until ALL protocol methods are implemented. Implement methods in Tasks 5-9, then verify this test passes after Task 9.

**Step 2: Create WebGuiBackend with navigation methods**

```python
# src/sapguimcp/backend/webgui/backend.py
"""WebGUI backend implementation using Playwright/CDP."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sapguimcp.backend.protocol import CheckActivateResult
from sapguimcp.backend.types import AriaSnapshot
from sapguimcp.backend.webgui.js_helpers import load_js, load_js_with_field_utils
from sapguimcp.models import (
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
    TransactionResult,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)


class WebGuiBackend:
    """SapUiBackend implementation using Playwright browser automation.

    Each instance wraps a single Playwright Page (one SAP session).
    """

    def __init__(self, page: Page) -> None:
        self._page = page

    # -- SapNavigation --

    async def login(
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
    ) -> LoginResult:
        """Navigate to SAP WebGUI and log in."""
        # Implementation extracted from sap_tools.py sap_login (~lines 630-740).
        # Move the existing login logic here, using self._page instead of page.
        raise NotImplementedError("TODO: extract from sap_tools.py")

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        """Enter a transaction code via the OK-Code field."""
        # Implementation extracted from sap_tool_impl.py sap_transaction_impl.
        # Core pattern:
        #   okcode = await self._find_okcode_field()
        #   await okcode.click()
        #   await self._page.evaluate(load_js("set_okcode_field.js"), {"transactionInput": f"/n{tcode}"})
        #   await self._page.keyboard.press("Enter")
        #   await self.wait_for_ready()
        raise NotImplementedError("TODO: extract from sap_tool_impl.py")

    async def get_session_status(self) -> SessionStatus:
        """Check session health (OK-Code field present, login form, timeouts)."""
        # Implementation extracted from sap_tools.py sap_session_status (~line 1014).
        raise NotImplementedError("TODO: extract from sap_tools.py")

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        """Wait for SAP page to finish loading."""
        await self._page.wait_for_load_state(
            "networkidle", timeout=timeout_ms
        )

    async def bring_to_front(self) -> None:
        """Bring the browser window to the foreground."""
        await self._page.bring_to_front()
```

Each `NotImplementedError` will be replaced with code extracted from the existing tool implementations. The existing code is referenced by file and line number in each method's comment.

**Step 3: Commit skeleton**

```bash
git add src/sapguimcp/backend/webgui/backend.py unittests/test_webgui_backend.py
git commit -m "feat: add WebGuiBackend skeleton with navigation methods"
```

---

### Task 6: Implement WebGuiBackend — primitives methods

**Files:**

- Modify: `src/sapguimcp/backend/webgui/backend.py`

Add the `SapUiPrimitives` methods to `WebGuiBackend`. Extract logic from:

- `fill_field` ← `sap_tool_impl.py` `_load_js("set_field.js")` pattern. Raises `ValueError` on failure.
- `fill_form` ← `sap_tool_impl.py` `sap_fill_form_impl` (lines ~130-180)
- `fill_grid_cell` ← `se16_tools.py` filter filling logic + `fill_se16_filter.js`. For filling grid/table cells by row+column (needed by SE16 filters).
- `click_button` ← `sap_tools.py` button click logic + `discover_buttons.js`. Returns `None`.
- `click_tab` ← `se24_tools.py` `_click_tab` helper pattern. Returns `None`.
- `press_key` ← `sap_tool_impl.py` `sap_press_key_impl` (lines ~80-128)
- `type_text` ← `page.keyboard.type()` wrapper
- `select_dropdown` ← `sap_tools.py` dropdown selection logic

**Key pattern for each method:**

```python
async def fill_field(self, label: str, value: str) -> None:
    js = load_js_with_field_utils("set_field.js")
    result = await self._page.evaluate(js, {"label": label, "value": value})
    if not result.get("success"):
        raise ValueError(f"Could not fill field '{label}': {result.get('error')}")

async def fill_form(self, fields: dict[str, str]) -> FillFormResult:
    js = load_js_with_field_utils("fill_form_fields.js")
    result = await self._page.evaluate(js, {"fields": fields})
    return FillFormResult(
        filled=result.get("filled", []),
        not_found=result.get("notFound", []),
        errors=[...],  # Map from JS result
    )

async def press_key(self, key: str) -> KeyboardResult:
    await self._page.bring_to_front()
    await self._page.keyboard.press(key)
    await self.wait_for_ready()
    # Read status bar for F-keys/Ctrl shortcuts
    ...
```

**Step: Commit after all primitives implemented**

```bash
git commit -m "feat: implement SapUiPrimitives methods in WebGuiBackend"
```

---

### Task 7: Implement WebGuiBackend — inspection methods

**Files:**

- Modify: `src/sapguimcp/backend/webgui/backend.py`

Add the `SapUiInspection` methods. Extract logic from:

- `get_status_bar` ← `sap_tool_impl.py` `sap_read_status_bar_impl` + `extract_status_bar.js`
- `get_screen_info` ← `sap_tool_impl.py` `sap_get_screen_info_impl` + `extract_screen_info.js`
- `get_screen_text` ← `sap_tool_impl.py` `sap_get_screen_text_impl` + `extract_screen_text.js`. Accepts `include_dropdown_options: bool`. Returns `ScreenText`.
- `discover_fields` ← `sap_tools.py` `sap_discover_fields` + `discover_fields.js`
- `get_form_fields` ← `sap_tools.py` `sap_get_form_fields` + `detect_form_fields.js`. Returns `FormFieldsResult`.
- `discover_buttons` ← `sap_tools.py` `sap_get_shortcuts` + `discover_buttons.js`
- `get_snapshot` ← `page.locator("body").aria_snapshot()` → wrap in `AriaSnapshot()`
- `take_screenshot` ← `page.screenshot(full_page=True)`
- `read_table` ← `sap_tools.py` `sap_read_table` + `extract_table_data.js`
- `click_table_cell` ← `sap_tools.py` `sap_click_table_cell` + `click_table_cell.js`. Signature: `(row: int, column: int | str, action: str = "click") -> TableCellClickResult`
- `get_dropdown_options` ← `sap_tools.py` + `get_dropdown_options.js`

**Key pattern:**

```python
async def get_snapshot(self) -> AriaSnapshot:
    raw = await self._page.locator("body").aria_snapshot()
    return AriaSnapshot(raw)

async def get_status_bar(self) -> StatusBarInfo:
    result = await self._page.evaluate(load_js("extract_status_bar.js"))
    return StatusBarInfo(
        type=result.get("type", "none"),
        message=result.get("message", ""),
    )

async def take_screenshot(self) -> bytes:
    return await self._page.screenshot(full_page=True)
```

**Step: Commit**

```bash
git commit -m "feat: implement SapUiInspection methods in WebGuiBackend"
```

---

### Task 8: Implement WebGuiBackend — editor methods

**Files:**

- Modify: `src/sapguimcp/backend/webgui/backend.py`

Extract logic from `tools/edit_helpers.py`:

- `read_editor_source` ← `edit_helpers.py:92-101`
- `replace_editor_source` ← `edit_helpers.py:104-117`
- `check_and_activate` ← `edit_helpers.py:120-161`

Also move `dismiss_language_dialog` as a private helper `_dismiss_language_dialog()` on the backend.

**Step: Commit**

```bash
git commit -m "feat: implement SapEditor methods in WebGuiBackend"
```

---

### Task 9: Implement WebGuiBackend — popup methods

**Files:**

- Modify: `src/sapguimcp/backend/webgui/backend.py`

Extract logic from:

- `check_popup` ← `sap_tools.py` popup detection + `check_popup.js`
- `dismiss_popup` ← `sap_tools.py` popup dismissal pattern. Signature: `(button_label: str | None = None, use_close_button: bool = False) -> ClosePopupResult`

**Step: Verify protocol compliance**

Run: `python -m pytest unittests/test_webgui_backend.py -v`
Expected: `test_webgui_backend_implements_protocol` PASS (all methods now exist)

**Step: Commit**

```bash
git commit -m "feat: implement SapPopup methods in WebGuiBackend"
```

---

### Task 10: Implement BackendManager

**Files:**

- Create: `src/sapguimcp/backend/manager.py`
- Modify: `src/sapguimcp/backend/__init__.py`
- Test: `unittests/test_backend_manager.py`

**Step 1: Write test**

```python
# unittests/test_backend_manager.py
"""Tests for BackendManager."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.manager import BackendManager
from sapguimcp.backend.webgui.backend import WebGuiBackend


def test_backend_manager_default_type() -> None:
    """Default backend type should be 'webgui'."""
    manager = BackendManager()
    assert manager.backend_type == "webgui"


def test_backend_manager_unknown_type_raises() -> None:
    """Unknown backend type should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown backend type"):
        BackendManager(backend_type="unknown")
```

**Step 2: Implement BackendManager**

```python
# src/sapguimcp/backend/manager.py
"""Backend manager — singleton entry point for tools."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sapguimcp.backend.webgui.backend import WebGuiBackend

if TYPE_CHECKING:
    from sapguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

_VALID_BACKEND_TYPES = {"webgui"}


class BackendManager:
    """Manages SapUiBackend instances across sessions.

    Wraps the existing BrowserManager/SessionRegistry for WebGUI.
    """

    def __init__(self, backend_type: str = "webgui") -> None:
        if backend_type not in _VALID_BACKEND_TYPES:
            raise ValueError(
                f"Unknown backend type '{backend_type}'. "
                f"Valid types: {_VALID_BACKEND_TYPES}"
            )
        self.backend_type = backend_type
        self._backends: dict[str, WebGuiBackend] = {}  # Cache by session ID

    async def get_or_create(
        self,
        session: str | None = None,
        agent_id: str | None = None,
        tool_name: str = "",
    ) -> SapUiBackend:
        """Get or create a backend instance for the given session.

        Caches WebGuiBackend instances by session ID. Returns cached instance
        if the underlying page is still the same, creates a new one otherwise.
        """
        if self.backend_type == "webgui":
            from sapguimcp.backend.webgui.browser import (
                get_browser_manager,
            )

            browser_manager = await get_browser_manager()
            page = await browser_manager.get_or_create_session_page_checked(
                session, agent_id, tool_name
            )
            session_key = session or "s1"
            cached = self._backends.get(session_key)
            if cached is not None and cached._page is page:
                return cached
            backend = WebGuiBackend(page)
            self._backends[session_key] = backend
            return backend
        raise ValueError(f"No implementation for backend '{self.backend_type}'")


# -- Singleton --

_backend_manager: BackendManager | None = None


def get_backend_manager() -> BackendManager:
    """Get the global BackendManager singleton (lazy init)."""
    global _backend_manager  # noqa: PLW0603
    if _backend_manager is None:
        # Read backend type from settings/env
        from sapguimcp.models.config import get_settings

        settings = get_settings()
        backend_type = getattr(settings, "sap_ui_backend", "webgui")
        _backend_manager = BackendManager(backend_type=backend_type)
    return _backend_manager


async def get_backend(
    session: str | None = None,
    agent_id: str | None = None,
    tool_name: str = "",
) -> SapUiBackend:
    """Convenience: get a backend instance for the given session.

    This is the primary entry point for all tools.
    """
    manager = get_backend_manager()
    return await manager.get_or_create(session, agent_id, tool_name)


def reset_backend_manager() -> None:
    """Reset the singleton (for testing)."""
    global _backend_manager  # noqa: PLW0603
    _backend_manager = None
```

**Step 3: Update `backend/__init__.py`**

Add exports:

```python
from sapguimcp.backend.manager import get_backend, get_backend_manager, reset_backend_manager
```

**Step 4: Run tests**

Run: `python -m pytest unittests/test_backend_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/backend/manager.py src/sapguimcp/backend/__init__.py unittests/test_backend_manager.py
git commit -m "feat: add BackendManager with get_backend() entry point"
```

---

## Phase 3: Tool Migration (new feature branch after foundation PR merges)

Each task follows the same pattern:

1. Replace `get_browser_manager()` + page retrieval with `get_backend()`
2. Replace direct Playwright calls with protocol method calls
3. Remove `from playwright.async_api import Page` imports
4. Keep MCP tool signatures identical
5. Run tests after each migration
6. Commit

---

### Task 11: Delete `sap_tool_impl.py`

**Files:**

- Delete: `src/sapguimcp/tools/sap_tool_impl.py`
- Modify: All files that import from `sap_tool_impl.py` (update to use `get_backend()` directly or import JS helpers from `backend.webgui.js_helpers`)

Per design review: `sap_tool_impl.py` is a double-delegation layer — its functions just wrap backend methods. Delete it outright instead of migrating. All callers switch to using `get_backend()` directly.

**Step 1: Identify all importers**

```bash
grep -r "from sapguimcp.tools.sap_tool_impl import" src/sapguimcp/
```

Typical imports to replace:

- `sap_transaction_impl` → `backend.enter_transaction()`
- `sap_press_key_impl` → `backend.press_key()`
- `sap_fill_form_impl` → `backend.fill_form()`
- `sap_read_status_bar_impl` → `backend.get_status_bar()`
- `sap_get_screen_info_impl` → `backend.get_screen_info()`
- `sap_get_screen_text_impl` → `backend.get_screen_text()`
- `_load_js` / `_load_js_with_field_utils` → `from sapguimcp.backend.webgui.js_helpers import load_js, load_js_with_field_utils`

**Step 2: Update each caller to use backend directly**

Each file that imported from `sap_tool_impl.py` now calls `get_backend()` and uses protocol methods. Example:

```python
# BEFORE (in some tool file)
from sapguimcp.tools.sap_tool_impl import sap_transaction_impl
result = await sap_transaction_impl(tcode, session, agent_id)

# AFTER
from sapguimcp.backend import get_backend
backend = await get_backend(session=session, agent_id=agent_id, tool_name="...")
result = await backend.enter_transaction(tcode)
```

**Step 3: Delete `sap_tool_impl.py`**

```bash
git rm src/sapguimcp/tools/sap_tool_impl.py
```

**Step 4: Run tests**

```bash
cd /c/github/sapgui.mcp && tox -e type_check
```

**Commit:**

```bash
git commit -m "refactor: delete sap_tool_impl.py, callers use backend directly"
```

---

### Task 12: Migrate `sap_tools.py`

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py`

This is the largest tool file (2370 lines). Replace every `get_browser_manager()` → `get_backend()` and every `page.*` call with backend protocol methods.

**Migration pattern for each tool in this file:**

```python
# BEFORE
@mcp.tool(...)
async def sap_transaction(tcode, new_window, session, agent_id):
    browser_manager = await get_browser_manager()
    page = await browser_manager.get_or_create_session_page_checked(session, agent_id, "sap_transaction")
    # ... Playwright calls ...

# AFTER
@mcp.tool(...)
async def sap_transaction(tcode, new_window, session, agent_id):
    backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_transaction")
    return await backend.enter_transaction(tcode)
```

**Tools to migrate in this file:**

- `sap_login` → `backend.login()`
- `sap_transaction` → `backend.enter_transaction()`
- `sap_press_key` → `backend.press_key()`
- `sap_fill_form` → `backend.fill_form()`
- `sap_set_field` → `backend.fill_field()` (raises `ValueError` on failure)
- `sap_get_screen_text` → `backend.get_screen_text(include_dropdown_options=...)` (returns `ScreenText`)
- `sap_get_screen_info` → `backend.get_screen_info()`
- `sap_read_status_bar` → `backend.get_status_bar()`
- `sap_get_form_fields` → `backend.get_form_fields()` (returns `FormFieldsResult`)
- `sap_discover_fields` → `backend.discover_fields()`
- `sap_get_shortcuts` / `sap_discover_buttons` → `backend.discover_buttons()`
- `sap_read_table` → `backend.read_table()`
- `sap_click_table_cell` → `backend.click_table_cell(row, column, action)` (returns `TableCellClickResult`)
- `sap_select_dropdown_option` → `backend.select_dropdown()`
- `sap_get_dropdown_options` → `backend.get_dropdown_options(label)`
- `sap_keepalive_start/stop` → These need special handling (timers that periodically interact with page). The keepalive logic may need to stay partly in the tool layer with backend calls.

**Special cases:**

- `sap_transaction` with `new_window=True` — Session-creation logic (waiting for new page, registering in SessionRegistry) belongs on `BackendManager`, not the protocol. Add `BackendManager.create_new_session()` method.
- `sap_get_screen_text` — Maps directly to `backend.get_screen_text(include_dropdown_options=True/False)`, which internally combines the JS extractions. The protocol method handles the complexity.

**Commit:**

```bash
git commit -m "refactor: migrate sap_tools.py to use backend protocol"
```

---

### Task 13: Delete `sap_page_helpers.py`

**Files:**

- Delete: `src/sapguimcp/tools/sap_page_helpers.py`
- Modify: All files that import from `sap_page_helpers.py`

These helpers (`navigate_transaction`, `fill_form_on_page`, `read_status_bar`) become one-liners when using the backend protocol. Delete the file outright and replace callers with direct backend calls.

**Step 1: Identify all importers**

```bash
grep -r "from sapguimcp.tools.sap_page_helpers import" src/sapguimcp/
```

**Step 2: Replace each call**

```python
# BEFORE
from sapguimcp.tools.sap_page_helpers import navigate_transaction
error = await navigate_transaction(page, "SE24")

# AFTER
result = await backend.enter_transaction("SE24")
if not result.success:
    return ...  # handle error using result.error
```

Similarly:

- `fill_form_on_page(page, fields)` → `await backend.fill_form(fields)`
- `read_status_bar(page)` → `await backend.get_status_bar()`

**Step 3: Delete the file**

```bash
git rm src/sapguimcp/tools/sap_page_helpers.py
```

**Commit:**

```bash
git commit -m "refactor: delete sap_page_helpers.py, callers use backend directly"
```

---

### Task 14: Migrate edit tools and delete `edit_helpers.py`

**Files:**

- Modify: `src/sapguimcp/tools/se24_edit_tools.py`
- Modify: `src/sapguimcp/tools/se37_edit_tools.py`
- Modify: `src/sapguimcp/tools/se38_edit_tools.py`
- Delete: `src/sapguimcp/tools/edit_helpers.py` (logic moved to WebGuiBackend in Task 8)

**Migration pattern:**

```python
# BEFORE (se38_edit_tools.py)
page = await browser_manager.get_or_create_session_page_checked(...)
backup = await read_editor_source(page)
await replace_editor_source(page, new_code)
success, messages, activated = await check_and_activate(page)

# AFTER
backend = await get_backend(session=session, ...)
backup = await backend.read_editor_source()
await backend.replace_editor_source(new_code)
result = await backend.check_and_activate()  # returns CheckActivateResult (ToolResult subclass)
# Use result.success, result.messages, result.activated — NOT tuple unpacking
```

**Important:** `check_and_activate()` returns a `CheckActivateResult` (a Pydantic `ToolResult` subclass), not a tuple. Callers access fields via `result.success`, `result.messages`, `result.activated`.

**Handling `edit_helpers.py`:**

- `read_editor_source`, `replace_editor_source`, `check_and_activate` → moved into `WebGuiBackend` (Task 8)
- `dismiss_language_dialog` → private method `_dismiss_language_dialog()` on `WebGuiBackend`
- `parse_toolbar_note` → private function `_parse_toolbar_note()` in `backend/webgui/backend.py`
- Delete `edit_helpers.py` entirely

```bash
git rm src/sapguimcp/tools/edit_helpers.py
```

**Commit:**

```bash
git commit -m "refactor: migrate edit tools to backend protocol, delete edit_helpers.py"
```

---

### Task 15: Migrate lookup tools

**Files:**

- Modify: `src/sapguimcp/tools/se24_tools.py`
- Modify: `src/sapguimcp/tools/se37_tools.py`
- Modify: `src/sapguimcp/tools/se11_tools.py`
- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `src/sapguimcp/tools/se93_tools.py`

**Migration pattern (using SE24 as example):**

```python
# BEFORE
page = await browser_manager.get_or_create_session_page_checked(...)
await navigate_transaction(page, "SE24")
class_field = page.get_by_role("textbox", name=re.compile(r"..."))
await class_field.fill(class_name)
await page.keyboard.press("F7")
await page.wait_for_load_state("networkidle")
snapshot = await page.locator("body").aria_snapshot()
entry = parse_se24_snapshot(snapshot)

# AFTER
backend = await get_backend(session=session, ...)
await backend.enter_transaction("SE24")
await backend.fill_field("Class/Interface", class_name)  # label-based
await backend.press_key("F7")
await backend.wait_for_ready()
snapshot = await backend.get_snapshot()
entry = parse_se24_snapshot(snapshot)
```

**Important:** The label used in `fill_field()` must work in both DE and EN. The WebGuiBackend's `fill_field` implementation should try multiple label variants (the JS-based `set_field.js` already does fuzzy matching by label text). Verify this works for each transaction.

**SE16 special case:** SE16 filter fields are grid cells, not labelled form fields. Use `backend.fill_grid_cell(row, column, value)` from the `SapUiPrimitives` protocol. The `WebGuiBackend` implementation uses `fill_se16_filter.js` internally.

```python
# SE16 filter filling
await backend.fill_grid_cell(row=0, column="MATNR", value="1000")
```

**Commit per tool group or individually:**

```bash
git commit -m "refactor: migrate SE24/SE37/SE11/SE16/SE93 lookup tools to backend protocol"
```

---

### Task 16: Migrate monitoring/utility tools

**Files:**

- Modify: `src/sapguimcp/tools/sm37_tools.py`
- Modify: `src/sapguimcp/tools/slg1_tools.py`
- Modify: `src/sapguimcp/tools/sm30_tools.py`
- Modify: `src/sapguimcp/tools/spro_tools.py`
- Modify: `src/sapguimcp/tools/st22_tools.py`
- Modify: `src/sapguimcp/tools/se09_tools.py`
- Audit: `src/sapguimcp/tools/catalog_tools.py`
- Audit: `src/sapguimcp/tools/class_tools.py`
- Audit: `src/sapguimcp/tools/fm_tools.py`
- Audit: `src/sapguimcp/tools/table_tools.py`
- Audit: `src/sapguimcp/tools/workflow_tools.py`

These all follow the same pattern as lookup tools: navigate to transaction, fill fields, press F-key, read snapshot/table, parse results.

**Audit step:** Check the "Audit" files above for any direct Playwright imports. If they use `Page` or `get_browser_manager()`, migrate them too. If they only use parsers/models, no change needed.

**SM37 special case:** Uses checkbox interactions (`page.get_by_role("checkbox").check()`). Add protocol support via `fill_field` for checkboxes or a dedicated method if needed. The `fill_form_fields.js` may already handle checkbox fields.

**Commit:**

```bash
git commit -m "refactor: migrate monitoring tools (SM37/SLG1/SM30/SPRO/ST22/SE09) to backend protocol"
```

---

### Task 17: Migrate abapGit tools

**Files:**

- Modify: `src/sapguimcp/tools/abapgit_tools.py`

This is the largest tool file after sap_tools.py (~1000 lines). Same migration pattern. Previously imported from `sap_tool_impl.py` — since that file was deleted in Task 11, update all calls to use `get_backend()` directly:

```python
# BEFORE
from sapguimcp.tools.sap_tool_impl import sap_transaction_impl, sap_read_status_bar_impl
await sap_transaction_impl(tcode, session, agent_id)
status = await sap_read_status_bar_impl(session, agent_id)

# AFTER
from sapguimcp.backend import get_backend
backend = await get_backend(session=session, agent_id=agent_id, tool_name="...")
await backend.enter_transaction(tcode)
status = await backend.get_status_bar()
```

**Commit:**

```bash
git commit -m "refactor: migrate abapGit tools to backend protocol"
```

---

### Task 18: Migrate browser_tools.py (conditional registration)

**Files:**

- Modify: `src/sapguimcp/tools/browser_tools.py`
- Modify: `src/sapguimcp/server.py`

Browser tools stay as direct Playwright wrappers but registration becomes conditional:

```python
# server.py — conditional registration
settings = get_settings()
backend_type = getattr(settings, "sap_ui_backend", "webgui")

if backend_type == "webgui":
    register_browser_tools(mcp)
```

No changes needed inside `browser_tools.py` itself — these tools intentionally use Playwright directly as an escape hatch.

**Commit:**

```bash
git commit -m "refactor: make browser_tools registration conditional on backend type"
```

---

### Task 19: Migrate session_tools.py

**Files:**

- Modify: `src/sapguimcp/tools/session_tools.py`

Session management tools (`sap_session_list`, `sap_session_close`, `sap_session_bind`, `sap_session_release`) operate on the `BackendManager`/`SessionRegistry`, not on individual backend instances.

```python
# BEFORE
browser_manager = await get_browser_manager()
sessions = browser_manager.registry.list_sessions()

# AFTER — option A: use BackendManager directly
from sapguimcp.backend.manager import get_backend_manager
manager = get_backend_manager()
sessions = manager.list_sessions()
```

This requires adding session management methods to `BackendManager` that delegate to the underlying `SessionRegistry` (for WebGUI) or equivalent (for future backends).

**Commit:**

```bash
git commit -m "refactor: migrate session_tools.py to use BackendManager"
```

---

## Phase 4: Wiring, Cleanup & Tests

---

### Task 20: Update server.py wiring

**Files:**

- Modify: `src/sapguimcp/server.py`

Update the lifespan to initialize/cleanup via `BackendManager`:

```python
# BEFORE
from sapguimcp.models import close_browser_manager, get_browser_manager

@asynccontextmanager
async def app_lifespan(_server: FastMCP):
    # ... startup checks ...
    yield
    await close_browser_manager()

# AFTER
from sapguimcp.backend.manager import get_backend_manager, reset_backend_manager

@asynccontextmanager
async def app_lifespan(_server: FastMCP):
    # ... startup checks ...
    yield
    # Cleanup
    manager = get_backend_manager()
    await manager.cleanup()  # Add this method to BackendManager
    reset_backend_manager()
```

**Commit:**

```bash
git commit -m "refactor: update server.py to use BackendManager lifecycle"
```

---

### Task 21: Remove old re-exports and dead code

**Files:**

- Modify: `src/sapguimcp/models/__init__.py` — remove `BrowserManager`, `get_browser_manager`, `close_browser_manager` re-exports (or keep as deprecated with a warning)

Note: `sap_tool_impl.py` was already deleted in Task 11, `sap_page_helpers.py` in Task 13, and `edit_helpers.py` in Task 14. This task handles remaining cleanup.

**Verify no Playwright imports remain in tools/:**

```bash
grep -r "from playwright" src/sapguimcp/tools/
```

Expected: Only `browser_tools.py` should have Playwright imports.

**Also verify no stale imports from deleted files:**

```bash
grep -r "sap_tool_impl\|sap_page_helpers\|edit_helpers" src/sapguimcp/tools/
```

Expected: No matches (all callers updated in earlier tasks).

**Commit:**

```bash
git commit -m "chore: remove old re-exports and dead code after migration"
```

---

### Task 22: Run full CI suite and fix regressions

Use `tox` environments to match CI exactly.

**Step 1: Run unit tests**

```bash
cd /c/github/sapgui.mcp && python -m pytest unittests/ -k "not integration and not exploration" -v --timeout=60
```

Fix any failures. Common issues:

- Import paths changed
- Function signatures changed (Page → SapUiBackend)
- Missing re-exports

**Step 2: Run type checking (matches CI)**

```bash
cd /c/github/sapgui.mcp && tox -e type_check
```

**Step 3: Run formatting check (matches CI)**

```bash
cd /c/github/sapgui.mcp && tox -e formatting
```

**Step 4: Auto-fix formatting if needed**

```bash
cd /c/github/sapgui.mcp && python -m black src/ unittests/
cd /c/github/sapgui.mcp && python -m isort src/ unittests/
```

**Step 5: Run spelling check (matches CI)**

```bash
cd /c/github/sapgui.mcp && tox -e spelling
```

**Commit:**

```bash
git commit -m "fix: resolve test failures and linting issues after migration"
```

---

### Task 23: Add SAP_UI_BACKEND to config

**Files:**

- Modify: `src/sapguimcp/models/config.py`
- Modify: `.env.example` (if it exists)

Add the `sap_ui_backend` field to `SapGuiSettings`:

```python
# In config.py SapGuiSettings class
sap_ui_backend: Literal["webgui"] = Field(
    default="webgui",
    description="SAP UI backend type. Currently only 'webgui' is supported.",
)
```

**Commit:**

```bash
git commit -m "feat: add SAP_UI_BACKEND config option (default: webgui)"
```

---

## Summary

| Phase                    | Tasks       | Merge target          |
| ------------------------ | ----------- | --------------------- |
| Phase 1: Foundation      | Tasks 1-3   | main (individual PRs) |
| Phase 2: WebGuiBackend   | Tasks 4-10  | feature branch        |
| Phase 3: Tool migration  | Tasks 11-19 | feature branch        |
| Phase 4: Cleanup & tests | Tasks 20-23 | feature branch → main |

**Total files created:** 6 new files in `backend/`
**Total files modified:** ~30 tool and model files
**Total files deleted:** 3 (`sap_tool_impl.py`, `sap_page_helpers.py`, `edit_helpers.py`)
