# UI Backend Abstraction — Design Document

**Date:** 2026-03-04
**Status:** Approved

## Problem

All MCP tools currently interact with SAP through Playwright/CDP browser automation (SAP WebGUI). A desktop SAP GUI backend is on the horizon. To support both, the UI layer must become exchangeable — tools should program against a protocol, not Playwright directly.

## Goals

- **Loose coupling**: tools never import or touch Playwright, CSS selectors, JS, or any backend-specific type
- **Clean separation of concerns**: no page leaking through the Playwright layer, no desktop UI quirks in the tools layer
- **Shared models**: Pydantic tool parameters and return types remain backend-agnostic
- **Single standard on main**: no coexistence of old and new patterns — full migration in one feature branch

## Non-Goals

- Implementing a desktop GUI backend (that comes later)
- Changing MCP tool signatures (internal refactoring only)
- Abstracting `browser_*` tools (they stay WebGUI-only)

## Decisions

| Decision            | Choice                                                                           | Rationale                                                |
| ------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Interface mechanism | `typing.Protocol` (structural typing)                                            | More Pythonic, no inheritance required, lighter coupling |
| Backend selection   | `SAP_UI_BACKEND=webgui` env var at startup                                       | Simple, one backend per server instance                  |
| Migration strategy  | Feature branch, incremental commits, atomic merge to main                        | No mixed approaches on main                              |
| Abstraction level   | SAP-semantic operations (label-based, not selector-based)                        | Hides implementation details completely                  |
| Snapshot typing     | `NewType("AriaSnapshot", str)` now, generify with `TypeVar` when desktop arrives | Self-documenting types, easy to evolve                   |

## Architecture

### Protocol Hierarchy

Five focused sub-protocols combined into one `SapUiBackend` type:

```python
from typing import Protocol, NewType

AriaSnapshot = NewType("AriaSnapshot", str)

class SapUiPrimitives(Protocol):
    """Low-level UI interaction — fill, click, type, press."""
    async def fill_field(self, label: str, value: str) -> None: ...  # raises on failure
    async def fill_form(self, fields: dict[str, str]) -> FillFormResult: ...
    async def fill_grid_cell(self, row: int, column: int | str, value: str) -> None: ...
    async def click_button(self, label: str) -> None: ...
    async def click_tab(self, label: str) -> None: ...
    async def press_key(self, key: str) -> KeyboardResult: ...
    async def type_text(self, text: str) -> None: ...
    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult: ...

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

class SapNavigation(Protocol):
    """Navigation and session lifecycle."""
    async def login(self, url: str, username: str, password: str,
                    client: str, language: str) -> LoginResult: ...
    async def enter_transaction(self, tcode: str) -> TransactionResult: ...
    async def get_session_status(self) -> SessionStatus: ...
    async def wait_for_ready(self, timeout_ms: int = 15000) -> None: ...
    async def bring_to_front(self) -> None: ...

class SapEditor(Protocol):
    """Source code editor operations (SE38/SE24/SE37 editors)."""
    async def read_editor_source(self) -> str | None: ...
    async def replace_editor_source(self, code: str) -> bool: ...
    async def check_and_activate(self) -> CheckActivateResult: ...  # ToolResult subclass

class SapPopup(Protocol):
    """Popup/dialog detection and handling."""
    async def check_popup(self) -> PopupInfo | None: ...
    async def dismiss_popup(self, button_label: str | None = None, use_close_button: bool = False) -> ClosePopupResult: ...

class SapUiBackend(SapUiPrimitives, SapUiInspection, SapNavigation,
                   SapEditor, SapPopup, Protocol):
    """Combined interface — what tools depend on."""
    ...
```

### Backend Lifecycle

A `BackendManager` replaces `get_browser_manager()` + page retrieval:

```python
class BackendManager:
    """Manages backend instances across sessions. Singleton."""

    def __init__(self, backend_type: str):  # from SAP_UI_BACKEND env var
        ...

    async def get_or_create(self, session: str | None,
                            agent_id: str | None,
                            tool_name: str) -> SapUiBackend:
        """Get existing or create new backend for session."""
        ...

    def list_sessions(self) -> list[SessionInfo]: ...
    async def close_session(self, session_id: str) -> None: ...
    async def bind_session(self, session_id: str, agent_id: str) -> None: ...
    async def release_session(self, session_id: str) -> None: ...


# Convenience function used by all tools
async def get_backend(session: str | None = None,
                      agent_id: str | None = None,
                      tool_name: str = "") -> SapUiBackend:
    manager = get_backend_manager()  # singleton
    return await manager.get_or_create(session, agent_id, tool_name)
```

- For WebGUI: each `SapUiBackend` instance wraps one Playwright `Page`
- For future Desktop: each instance wraps one SAP GUI scripting session
- Session management (bind/release/list/close) lives on the manager, not the backend

### Tool Migration Pattern

Tools change from direct Playwright to protocol calls:

```python
# BEFORE
async def sap_transaction(tcode, session, agent_id):
    browser_manager = await get_browser_manager()
    page = await browser_manager.get_or_create_session_page_checked(session, agent_id, "sap_transaction")
    okcode = await page.query_selector("#ToolbarOkCode")
    await page.evaluate(_load_js("set_okcode_field.js"), {"transactionInput": f"/n{tcode}"})
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("networkidle")
    ...

# AFTER
async def sap_transaction(tcode, session, agent_id):
    backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_transaction")
    result = await backend.enter_transaction(tcode)
    return result
```

Transaction-specific tools orchestrate protocol calls + parsers:

```python
async def sap_se24_lookup(class_name, session, ...):
    backend = await get_backend(session=session, ...)
    await backend.enter_transaction("SE24")
    await backend.fill_field("Class/Interface", class_name)
    await backend.press_key("F7")
    await backend.wait_for_ready()
    snapshot = await backend.get_snapshot()  # returns AriaSnapshot
    entry = parse_se24_snapshot(snapshot)    # parser accepts AriaSnapshot
    return SE24Result(entry=entry, ...)
```

### Browser-Specific Tools

`browser_*` tools (`browser_click`, `browser_fill`, `browser_evaluate`, `browser_get_html`, `browser_snapshot`, `browser_screenshot`) are inherently WebGUI-specific (CSS selectors, JavaScript execution).

They stay as direct Playwright wrappers and are conditionally registered:

- When `SAP_UI_BACKEND=webgui`: registered normally
- When a non-browser backend is active: not registered

### Parser Strategy

Parsers remain pure functions. They are backend-specific (understand one snapshot format) but return shared models:

```python
# AriaSnapshot is a named type, not raw str
AriaSnapshot = NewType("AriaSnapshot", str)

# Parsers accept the typed snapshot
def parse_se24_snapshot(snapshot: AriaSnapshot) -> SE24Entry | SE24Error: ...
def parse_se16_snapshot(snapshot: AriaSnapshot) -> list[SE16Row]: ...
```

When a desktop backend arrives, it gets its own snapshot type and parsers. The result models (`SE24Entry`, `SE16Row`, etc.) remain shared.

## Module Structure

```
src/sapguimcp/
├── backend/                    # NEW — abstraction layer
│   ├── __init__.py             # exports get_backend, SapUiBackend, AriaSnapshot
│   ├── types.py                # AriaSnapshot, other type aliases
│   ├── protocol.py             # SapUiBackend and sub-protocols
│   ├── manager.py              # BackendManager singleton, get_backend()
│   └── webgui/                 # WebGUI implementation
│       ├── __init__.py
│       ├── backend.py          # WebGuiBackend — implements SapUiBackend
│       ├── js_helpers.py       # _load_js(), JS evaluation (moved from tools)
│       └── browser.py          # BrowserManager (moved from models/browser.py)
├── js/                         # unchanged — JS files used by webgui backend
├── models/                     # unchanged — shared Pydantic models
├── parsers/                    # unchanged — use AriaSnapshot type
├── tools/                      # refactored — no Playwright imports
│   ├── sap_tools.py            # uses get_backend()
│   ├── se24_tools.py           # orchestrates protocol + parsers
│   ├── browser_tools.py        # WebGUI-only, conditional registration
│   ├── session_tools.py        # uses BackendManager for session ops
│   └── ...
└── server.py                   # wires BackendManager, conditional tool registration
```

Key moves:

- `models/browser.py` → `backend/webgui/browser.py`
- JS loading helpers → `backend/webgui/js_helpers.py`
- `get_browser_manager()` → `get_backend()` from `backend/manager.py`
- All `from playwright.async_api import Page` removed from `tools/`

## Migration Strategy

### Preparatory PRs (land on main independently, non-breaking)

These reduce the size of the final migration PR. Push to remote, developer merges to main before continuing with the main migration.

1. **Introduce `AriaSnapshot` type** — `NewType("AriaSnapshot", str)`, update parser signatures and call sites
2. **Create `backend/` package skeleton** — `types.py` and `protocol.py` only, no wiring
3. **Move JS helpers** — relocate `_load_js()` to `backend/webgui/js_helpers.py`, re-export from old location for compatibility

### Main migration PR (feature branch, atomic merge)

After preparatory PRs are merged to main:

1. Move `BrowserManager` to `backend/webgui/browser.py` (re-export from old location)
2. Implement `WebGuiBackend` (wraps Playwright `Page`, calls JS helpers)
3. Implement `BackendManager` (session registry, singleton, `get_backend()`, backend caching)
4. Refactor all `sap_*` and transaction tools to use `get_backend()` + protocol
5. Delete `sap_tool_impl.py` and `sap_page_helpers.py` — callers use backend directly
6. Move `edit_helpers.py` logic into `WebGuiBackend` (editor protocol methods)
7. Make `browser_*` tool registration conditional on backend type
8. Remove old re-exports and direct Playwright imports from tools
9. Update/add tests

## Review Findings Applied

Architecture review identified these issues (all addressed above):

1. **No CSS selectors in protocol** — `SapEditor` had `editor_selector` parameter, removed. `ClickResult` (browser model with `selector: str` field) replaced with `None` returns for `click_button`/`click_tab`.
2. **Missing protocol methods** — Added `get_screen_text()`, `get_form_fields()`, `get_session_status()`, `fill_grid_cell()` for SE16 filter handling.
3. **Consistent error handling** — `fill_field` raises on failure (ergonomic for loops), `fill_form` returns `FillFormResult` (batch needs details). Documented in protocol docstrings.
4. **`CheckActivateResult`** — Made a `ToolResult` subclass for consistency with all other result types.
5. **`dismiss_popup`** — Added `use_close_button` parameter and `ClosePopupResult` return type.
6. **`click_table_cell`** — Uses `column: int | str` and `action` parameter, returns `TableCellClickResult`.
7. **Backend caching** — `BackendManager` caches `WebGuiBackend` instances by session ID.
8. **Skip double-delegation** — `sap_tool_impl.py` functions deleted, callers use backend directly.
9. **`new_window=True`** — Session creation belongs on `BackendManager`, not the protocol.
