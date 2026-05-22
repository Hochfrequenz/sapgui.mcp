# Desktop Backend Adapter — Design Spec

## Goal

Implement `SapUiBackend` protocol using pysapgui (COM) so that all existing MCP tools work with SAP GUI for Windows desktop — no WebGUI/browser needed.

## Non-Goals

- Modifying the existing WebGUI backend
- Modifying existing MCP tools (they call the protocol, not the backend directly)
- Adding new tools specific to desktop
- Supporting non-Windows platforms

## Architecture

```
MCP Tools → SapUiBackend protocol → DesktopBackend (new)
                                  → WebGuiBackend  (existing)
```

`DesktopBackend` implements the same `SapUiBackend` protocol as `WebGuiBackend`. Tools don't know which backend they're talking to. The `BackendManager` selects the backend based on `BACKEND_TYPE` config.

### COM Threading Model

All COM calls run on a **dedicated background thread** with its own `CoInitialize()`. The `DesktopBackend` async methods submit work to this thread via a queue and await the result. This ensures:

- All COM calls happen on the same apartment-threaded context
- No COM threading bugs from `asyncio.to_thread()` creating new threads
- Clean `CoUninitialize()` on shutdown

Uses `concurrent.futures.Future` + `asyncio.wrap_future` for clean cross-thread dispatch with proper traceback preservation:

```python
import concurrent.futures

class _ComThread:
    """Dedicated thread for all SAP GUI COM calls."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        pythoncom.CoInitialize()
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                fn, cf_future = item
                try:
                    result = fn()
                    cf_future.set_result(result)
                except Exception as e:
                    cf_future.set_exception(e)
        finally:
            pythoncom.CoUninitialize()

    async def run(self, fn: Callable[[], T]) -> T:
        cf_future = concurrent.futures.Future()
        self._queue.put((fn, cf_future))
        return await asyncio.wrap_future(cf_future)

    def shutdown(self) -> None:
        """Signal the worker thread to exit and wait for cleanup."""
        self._queue.put(None)
        self._thread.join(timeout=5)
```

## Package Location

```
src/sapguimcp/backend/desktop/
    __init__.py              # DesktopBackend class
    _com_thread.py           # _ComThread — dedicated COM worker thread
    _session_manager.py      # Multi-session tracking (bind/release/list)
    _key_mapping.py          # Map key names ("F5", "Enter", "Ctrl+S") → VKey numbers
    _element_finder.py       # Label→field resolution for SAP dynpro screens
```

Tests mirror under `unittests/desktop/`.

## Method Mapping: Protocol → COM

### SapNavigation

| Protocol Method                       | Desktop Implementation                                                             |
| ------------------------------------- | ---------------------------------------------------------------------------------- |
| `login(url, user, pwd, client, lang)` | Ignore `url`, use `SAP_CONNECTION_NAME`. Call `_login.login()`.                    |
| `enter_transaction(tcode)`            | `session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/n" + tcode; wnd.send_v_key(0)` |
| `get_session_status()`                | Read `session.info` → `SessionStatus`                                              |
| `wait_for_ready()`                    | Poll `session.busy` until False                                                    |
| `bring_to_front()`                    | `wnd.iconify(); wnd.restore()` (COM trick to bring to front)                       |
| `wait(timeout_ms)`                    | `asyncio.sleep(timeout_ms / 1000)`                                                 |
| `start_keepalive()`                   | No-op — desktop sessions don't time out like WebGUI                                |
| `stop_keepalive()`                    | No-op, return False                                                                |
| `open_new_session(tcode)`             | `session.create_session()`, wait for new session, enter tcode                      |
| `list_sessions()`                     | Iterate `connection.children`, build `SessionInfo` list                            |
| `close_session(id)`                   | Find session by ID, `connection.close_session(id)`                                 |
| `bind_session(id, agent)`             | Track in `_session_manager` dict                                                   |
| `release_session(id)`                 | Remove from `_session_manager` dict                                                |
| `has_session(id)`                     | Check if session ID exists in connection                                           |
| `is_page_closed()`                    | Try to access `session.info` — if COM error, page is closed                        |
| `close_page()`                        | `connection.close_connection()` (use pysapgui wrapper, not raw COM)                |
| `get_session_token()`                 | Return `session.id` (unique per session)                                           |

### SapUiInspection

| Protocol Method          | Desktop Implementation                                                          |
| ------------------------ | ------------------------------------------------------------------------------- |
| `get_status_bar()`       | Read `wnd[0]/sbar` text + message_type → `StatusBarInfo`                        |
| `get_screen_info()`      | Read `session.info` → `ScreenInfo`                                              |
| `get_screen_text()`      | `wnd.dump_tree(max_depth=3)` → extract text from all elements                   |
| `discover_fields()`      | Recursive walk of `usr` subtree, filter input types → `FieldInfo` list          |
| `get_form_fields()`      | Same as discover_fields but includes values → `FormFieldsResult`                |
| `discover_buttons()`     | Walk `usr` + `tbar` children, filter by type (btn) → `ButtonInfo` list          |
| `get_snapshot()`         | `wnd.dump_tree()` → serialize as YAML-like string (AriaSnapshot)                |
| `take_screenshot()`      | `wnd.hard_copy(temp_path, 2)` (2=PNG) → read temp file → bytes → delete temp    |
| `read_table()`           | Detect GuiTableControl or GuiGridView, read cells → `TableData`                 |
| `click_table_cell()`     | GuiGridView: `grid.click(row, col)` / GuiTableControl: `tbl.get_cell(row, col)` |
| `get_dropdown_options()` | Find GuiComboBox by label, read `.entries`                                      |
| `get_page_title()`       | `wnd.text`                                                                      |

### SapUiPrimitives

| Protocol Method                           | Desktop Implementation                                                                                             |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `fill_field(label, value)`                | Find field by label (see Element Finding Strategy below) → set `.text`                                             |
| `fill_main_input(value, labels)`          | Find first text field in usr matching any label → set `.text`                                                      |
| `fill_form(fields)`                       | Call `fill_field` for each entry                                                                                   |
| `fill_grid_cell(row, col, value)`         | GuiGridView: convert `int` col to column name via `column_order`, then `grid.set_cell_value(row, col_name, value)` |
| `click_button(label)`                     | Find button by text match → `.press()`                                                                             |
| `click_tab(label)`                        | Find GuiTab by text match → `.select()`                                                                            |
| `press_key(key)`                          | Map key name to VKey number → `wnd.send_v_key(vkey)`                                                               |
| `type_text(text)`                         | Set text on focused element (or use `session.send_command` patterns)                                               |
| `set_checkbox(label, checked)`            | Find checkbox by label → `.selected = checked`                                                                     |
| `set_radio_button(label)`                 | Find radio button by label → `.selected = True`                                                                    |
| `select_dropdown(label, option)`          | Find combobox by label → set `.value`                                                                              |
| `focus_and_type(name, text)`              | Find field by accessible name → `.text = text`                                                                     |
| `fill_element_by_locator(locator, value)` | Raise `NotImplementedError("CSS selectors not supported on desktop SAP GUI")`                                      |
| `click_element(selector)`                 | Raise `NotImplementedError("CSS selectors not supported on desktop SAP GUI")`                                      |
| `load_js(filename)`                       | Raise `NotImplementedError("JavaScript not supported on desktop SAP GUI")`                                         |
| `evaluate_javascript(script)`             | Raise `NotImplementedError("JavaScript not supported on desktop SAP GUI")`                                         |

### SapEditor

| Protocol Method               | Desktop Implementation                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| `read_editor_source()`        | Find GuiAbapEditor or GuiTextedit → read all lines                                               |
| `replace_editor_source(code)` | Find editor → set text content                                                                   |
| `check_and_activate()`        | `wnd.send_v_key(26)` (Ctrl+F2 = check), `wnd.send_v_key(27)` (Ctrl+F3 = activate), read messages |
| `dismiss_language_dialog()`   | Check for modal wnd[1] with language text → press Enter                                          |

### SapPopup

| Protocol Method                                 | Desktop Implementation                                                                                                                     |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `check_popup()`                                 | Check if `wnd[1]` exists → build `PopupInfo` from its text/buttons                                                                         |
| `dismiss_popup(button_label, use_close_button)` | If `use_close_button`: `wnd[1].close()`. Else: find button in `wnd[1]` by label → `.press()`, or `wnd[1].send_v_key(0)` if no label given. |

## Element Finding Strategy

The biggest difference between WebGUI and desktop: WebGUI finds elements by ARIA labels (accessible names from the DOM). Desktop COM finds elements by ID paths (`wnd[0]/usr/txtFIELD_NAME`).

For protocol methods like `fill_field(label="Material")`, the desktop backend needs a multi-strategy approach in `_element_finder.py`:

### Strategy 1: Name-prefix convention (fast, reliable)

SAP labels and their associated fields share the same suffix. Label `lblMATNR` → try `txtMATNR`, `ctxtMATNR`, `pwdMATNR`, `cmbMATNR`.

```python
def _find_field_by_name_prefix(session, label_name: str) -> GuiComponent | None:
    """Try common type prefixes to find the field associated with a label."""
    usr_id = "wnd[0]/usr/"
    for prefix in ("txt", "ctxt", "pwd", "cmb", "chk", "rad"):
        field = session.find_by_id(usr_id + prefix + label_name, raise_error=False)
        if field is not None:
            return field
    return None
```

### Strategy 2: Recursive label text match (thorough)

Walk the entire `wnd[0]/usr` subtree recursively (not just direct children — SAP screens use nested containers like `GuiSimpleContainer` and `GuiScrollContainer`). Match label `.text` to the search string, then find the associated field via the label's name suffix or positional adjacency.

Also uses `GuiLabel.is_left_label` and `is_right_label` properties to understand label-field associations.

```python
def _find_field_by_label_text(session, label: str) -> GuiComponent | None:
    """Recursively search for a label matching the text, then find its field."""
    # Use find_all_by_name_ex to search recursively for all labels (type 30)
    labels = session.find_by_id("wnd[0]/usr").find_all_by_name_ex("", 30)
    for lbl in labels:
        if label.lower() in lbl.text.lower():
            # Try name-prefix convention first
            field = _find_field_by_name_prefix(session, lbl.name)
            if field is not None:
                return field
    return None
```

### Strategy 3: find_by_name (SAP native)

Use `GuiVContainer.find_by_name(name, type)` which searches the entire subtree natively via COM.

The strategies are tried in order: name-prefix → label text match → find_by_name.

## VKey Mapping

```python
_VKEY_MAP = {
    # Standard F-keys
    "Enter": 0, "F1": 1, "F2": 2, "F3": 3, "F4": 4, "F5": 5,
    "F6": 6, "F7": 7, "F8": 8, "F9": 9, "F10": 10, "F11": 11, "F12": 12,
    # Shift+F keys
    "Shift+F1": 13, "Shift+F2": 14, "Shift+F3": 15, "Shift+F4": 16,
    "Shift+F5": 17, "Shift+F6": 18, "Shift+F7": 19, "Shift+F8": 20,
    "Shift+F9": 21, "Shift+F10": 22, "Shift+F11": 23, "Shift+F12": 24,
    # Ctrl+F keys
    "Ctrl+F1": 25, "Ctrl+F2": 26, "Ctrl+F3": 27, "Ctrl+F4": 28,
    "Ctrl+F5": 29, "Ctrl+F6": 30, "Ctrl+F7": 31, "Ctrl+F8": 32,
    "Ctrl+F9": 33, "Ctrl+F10": 34, "Ctrl+F11": 35, "Ctrl+F12": 36,
    # SAP-conventional aliases (these map to F-keys, NOT literal OS keys)
    # Documented clearly because WebGUI handles these as real keyboard events
    "Escape": 12,     # Maps to F12 (Cancel) — SAP convention, not literal Escape
    "Backspace": 3,   # Maps to F3 (Back) — SAP convention, not literal Backspace
    "Ctrl+S": 11,     # Maps to Ctrl+S (Save) = F11 in SAP VKey numbering
}
```

Note: SAP GUI `SendVKey` only supports the function key matrix (0-36+). For literal key presses (Tab, Delete, arrow keys), use `session.send_command()` or OS-level `SendKeys` — but most SAP interactions use VKeys.

## BackendManager Integration

### Session Model

WebGUI: one `WebGuiBackend` per browser page. Each page = one session.

Desktop: one `DesktopBackend` per COM session (`GuiSession`). The `_session_manager` tracks which `GuiSession` is bound to which agent.

`BackendManager.get_or_create(session_id, agent_id, tool_name)`:

- For `"desktop"`: looks up the `GuiSession` by `session_id` (e.g., `/app/con[0]/ses[0]`), creates a `DesktopBackend` wrapping that specific session. Caches by session ID.
- Cache invalidation: if the COM session object becomes invalid (COM error on access), remove from cache and re-create.

### Config

Update `BackendType` in `models/config.py`:

```python
BackendType = Literal["webgui", "desktop"]
```

Add startup validation: if `backend_type == "desktop"` and `sap_connection_name` is empty, raise a clear error.

Update `BackendManager` in `backend/manager.py` to create `DesktopBackend` when `backend_type == "desktop"`.

## What Changes in Existing Code

- `models/config.py`: Extend `BackendType` to `Literal["webgui", "desktop"]`, add validation
- `backend/manager.py`: Add `elif self.backend_type == "desktop":` branch
- Everything else is NEW code in `backend/desktop/`

## Implementation Phases

### Phase 1: Navigation + Inspection + press_key (MVP)

- `_com_thread.py` — COM worker thread with shutdown
- `_key_mapping.py` — VKey map (needed for Enter/F-keys in navigation)
- `DesktopBackend.__init__` — session tracking, COM thread setup
- `SapNavigation` methods — login, enter_transaction, session management
- `SapUiInspection` methods — status bar, screen info, field discovery, table reading
- `press_key` from SapUiPrimitives (needed for navigation flows)
- BackendManager integration
- Enough to navigate SAP, read screens, and press function keys

### Phase 2: Primitives

- Remaining `SapUiPrimitives` methods — fill fields, click buttons, checkboxes, dropdowns
- `_element_finder.py` — label→field resolution
- Enough to interact with SAP screens

### Phase 3: Editor + Popup

- `SapEditor` methods — ABAP editor read/write, check/activate
- `SapPopup` methods — popup detection and dismissal

## Dependencies

No new dependencies. Uses existing:

- `sapguimcp.sapgui` (pysapgui library)
- `sapguimcp.sapgui._login` (login/logoff helpers)
- `pywin32` (already in pyproject.toml)
