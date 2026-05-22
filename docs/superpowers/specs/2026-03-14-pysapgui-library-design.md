# pysapgui — Pythonic SAP GUI Scripting Library

## Goal

A standalone, spec-compliant Python wrapper for the SAP GUI Scripting API (COM). Lives as a subpackage in this repo now, extractable to its own PyPI package later. Provides typed, Pythonic access to all SAP GUI elements via `find_by_id()` — the same ID-based navigation pattern that SAP GUI Scripting uses natively.

## Non-Goals

- No ARIA snapshots or WebGUI-specific formats
- No cross-platform support (COM is Windows-only, that's OK)
- No screenshot capability
- No MCP protocol integration (that's the `backend/desktop/` layer above this)

## Reference Spec

SAP GUI Scripting API 800 (HTML docs installed at `C:\Program Files\SAP\FrontEnd\SAPGUI\SAPguihelp\ScriptingAPI\`, gitignored copy at `docs/sap_gui_scripting_api_800/`). The 2969-page Innowera PDF (v6.40) covers the base API; version 800 adds ~6 new classes but is fully backward-compatible.

## Package Location

```
src/sapguimcp/
  sapgui/                    # standalone subpackage (future PyPI extraction)
    __init__.py              # public API: SapGui.connect(), SapGui.launch()
    _com.py                  # low-level COM helpers (GetObject, polling, CoInitialize)
    _types.py                # GuiComponentType enum, type prefix mappings
    _errors.py               # SapGuiError, ElementNotFoundError, etc.
    models.py                # Pydantic models: SessionInfo, ElementInfo
    components/
      __init__.py
      base.py                # GuiComponent, GuiVComponent, GuiContainer, GuiVContainer
      application.py         # GuiApplication
      connection.py          # GuiConnection
      session.py             # GuiSession, GuiSessionInfo
      window.py              # GuiFrameWindow, GuiMainWindow, GuiModalWindow, GuiMessageWindow
      field.py               # GuiTextField, GuiCTextField, GuiPasswordField, GuiLabel, GuiBox
      button.py              # GuiButton
      checkbox.py            # GuiCheckBox, GuiRadioButton
      combobox.py            # GuiComboBox, GuiComboBoxEntry
      okcode.py              # GuiOkCodeField
      statusbar.py           # GuiStatusbar (extends GuiVComponent, NOT GuiVContainer)
      toolbar.py             # GuiToolbar, GuiMenubar, GuiMenu, GuiTitlebar
      container.py           # GuiUserArea, GuiScrollContainer, GuiSimpleContainer,
                             # GuiContainerShell, GuiDialogShell, GuiCustomControl,
                             # GuiDockShell, GuiGOSShell, GuiSplitterContainer
      tab.py                 # GuiTabStrip, GuiTab
      table.py               # GuiTableControl, GuiTableRow, GuiTableColumn
      grid.py                # GuiGridView (ALV)
      tree.py                # GuiTree
      editor.py              # GuiTextedit, GuiAbapEditor
      shell.py               # GuiShell (base), GuiHTMLViewer, GuiToolbarControl, GuiPicture,
                             # and other GuiShell subclasses
      collection.py          # GuiCollection, GuiComponentCollection
    _factory.py              # wrap_com_object() — two-level dispatch (TypeAsNumber + SubType)
```

Tests:

```
unittests/
  sapgui/                    # mirrors the library structure
    __init__.py
    test_types.py            # GuiComponentType enum
    test_factory.py          # type dispatch logic (including SubType for GuiShell)
    test_components.py       # component wrapper unit tests (mocked COM)
    test_connect.py          # SapGui.connect() / SapGui.launch() (integration, needs SAP GUI)
```

## Inheritance Hierarchy (from SAP GUI Scripting API 800)

```
GuiComponent (abstract, type 0)
├── GuiContainer (abstract, type 70) — adds Children, FindById
│   ├── GuiApplication (type 10)
│   ├── GuiConnection (type 11)
│   └── GuiSession (type 12)
├── GuiVComponent (abstract, type 1) — adds Text, Tooltip, Changeable, SetFocus, DumpState
│   ├── GuiTextField (type 31, prefix: txt)
│   ├── GuiCTextField (type 32, prefix: ctxt) — extends GuiTextField
│   ├── GuiPasswordField (type 33, prefix: pwd) — extends GuiTextField
│   ├── GuiLabel (type 30, prefix: lbl)
│   ├── GuiButton (type 40, prefix: btn)
│   ├── GuiCheckBox (type 42, prefix: chk)
│   ├── GuiRadioButton (type 41, prefix: rad)
│   ├── GuiComboBox (type 34, prefix: cmb)
│   ├── GuiOkCodeField (type 35, prefix: okcd)
│   ├── GuiBox (type 62, prefix: box) — NOTE: NOT a container per spec
│   ├── GuiStatusbar (type 103, prefix: sbar) — NOTE: extends GuiVComponent, NOT GuiVContainer
│   ├── GuiStatusPane (type 43, prefix: pane)
│   └── GuiVHViewSwitch (type 129)
└── GuiVContainer (abstract, type 2) — extends both GuiContainer + GuiVComponent
    ├── GuiFrameWindow (abstract, type 20, prefix: wnd)
    │   ├── GuiMainWindow (type 21)
    │   ├── GuiModalWindow (type 22)
    │   └── GuiMessageWindow (type 23)
    ├── GuiToolbar (type 101, prefix: tbar)
    ├── GuiMenubar (type 111, prefix: mbar)
    ├── GuiMenu (type 110, prefix: menu)
    ├── GuiTitlebar (type 102, prefix: titl)
    ├── GuiUserArea (type 74, prefix: usr) — FindByLabel
    ├── GuiTabStrip (type 90, prefix: tabs)
    ├── GuiTab (type 91, prefix: tabp)
    ├── GuiTableControl (type 80, prefix: tbl)
    ├── GuiScrollContainer (type 72, prefix: ssub)
    ├── GuiSimpleContainer (type 71, prefix: sub)
    ├── GuiCustomControl (type 50, prefix: cntl)
    ├── GuiContainerShell (type 51, prefix: shellcont)
    ├── GuiDialogShell (type 125, prefix: shellcont)
    ├── GuiDockShell (type 126, prefix: shellcont)
    ├── GuiGOSShell (type 123, prefix: shellcont)
    ├── GuiSplitterContainer (type 75)
    └── GuiShell (type 122, prefix: shell) — abstract base for complex controls
        ├── GuiGridView (SubType: "GridView") — ALV grid
        ├── GuiTree (SubType: "Tree")
        ├── GuiTextedit (SubType: "TextEdit")
        ├── GuiAbapEditor (SubType: "AbapEditor")
        ├── GuiHTMLViewer (SubType: "HTMLViewer")
        ├── GuiToolbarControl (SubType: "ToolbarControl")
        ├── GuiPicture (SubType: "Picture")
        ├── GuiCalendar (SubType: "Calendar")
        ├── GuiBarChart (SubType: "BarChart") — deferred (recording-only)
        ├── GuiChart (SubType: "Chart") — deferred (recording-only)
        ├── GuiNetChart (SubType: "NetChart") — deferred (recording-only)
        ├── GuiColorSelector (SubType: "ColorSelector")
        ├── GuiComboBoxControl (SubType: "ComboBoxControl")
        ├── GuiInputFieldControl (SubType: "InputFieldControl")
        ├── GuiMap (SubType: "Map") — deferred (recording-only)
        ├── GuiApoGrid (SubType: "ApoGrid") — deferred (SCM-specific)
        ├── GuiSplit (SubType: "Splitter")
        ├── GuiStage (SubType: "Stage") — deferred (recording-only)
        ├── GuiSapChart (SubType: "SapChart") — deferred (recording-only)
        ├── GuiGraphAdapt (SubType: "GraphAdapt") — deferred (recording-only)
        ├── GuiEAIViewer2D (SubType: "Viewer2D") — deferred
        ├── GuiEAIViewer3D (SubType: "Viewer3D") — deferred
        └── GuiOfficeIntegration (SubType: "OfficeIntegration") — deferred

Standalone objects (no inheritance):
├── GuiSessionInfo (type 121) — member of GuiSession.Info
├── GuiComboBoxEntry — member of GuiComboBox.Entries
├── GuiScrollbar (type 100) — member of GuiUserArea scrollbars
├── GuiCollection (type 120) — generic collection
├── GuiComponentCollection (type 128) — typed component collection
├── GuiUtils — utility class on GuiApplication.Utils
└── GuiEnum — enumerator
```

### Deferred Classes

The following classes are deferred from the first implementation because they are recording-only controls (the SAP spec says "most parameters cannot be determined in any other way") or domain-specific:

`GuiBarChart`, `GuiChart`, `GuiNetChart`, `GuiMap`, `GuiApoGrid`, `GuiStage`, `GuiSapChart`, `GuiGraphAdapt`, `GuiEAIViewer2D`, `GuiEAIViewer3D`, `GuiOfficeIntegration`

The factory will return a generic `GuiShell` wrapper for these types. They can be added later without breaking changes.

## Core Design Principles

### 1. Thin wrappers around COM dispatch objects

Each Python class wraps a `win32com.client.CDispatch` object. Properties delegate to COM. No caching, no state — the COM object IS the source of truth.

```python
class GuiTextField(GuiVComponent):
    """SAP GUI text field (type prefix: txt)."""

    @property
    def caret_position(self) -> int:
        return self._com.CaretPosition

    @caret_position.setter
    def caret_position(self, value: int) -> None:
        self._com.CaretPosition = value

    @property
    def max_length(self) -> int:
        return self._com.MaxLength

    @property
    def is_required(self) -> bool:
        return bool(self._com.Required)

    @property
    def is_numerical(self) -> bool:
        return bool(self._com.Numerical)

    @property
    def is_hotspot(self) -> bool:
        return bool(self._com.IsHotspot)
```

### 2. Docstrings: non-obvious info + AI agent guidance

Skip docstrings that just restate the class name. Add them when they help a human or an **AI agent** understand:

- **When to use this class** vs a similar one (agents need to pick the right element)
- COM quirks (e.g., "Pressing a button invalidates all references below window level")
- Spec-specific behavior
- Gotchas and caveats

Bad: `"""SAP GUI text field."""`
Good:

```python
class GuiCTextField(GuiTextField):
    """Text field with F4 search help button (type prefix: ctxt).

    Use this for fields that have a dropdown/search icon to the right.
    The F4 button is part of the field, not a separate GuiButton.
    Setting .text triggers server communication only after pressing Enter or Tab.
    """
```

Good:

```python
class GuiOkCodeField(GuiVComponent):
    """The transaction code / command field in the system toolbar (type prefix: okcd).

    Set .text to a transaction code (e.g., "/nSE16") then call
    session.find_by_id("wnd[0]").send_v_key(0) to execute it.
    Setting text alone does NOT trigger navigation — you must send Enter (VKey 0).
    """
```

Good:

```python
class GuiGridView(GuiShell):
    """ALV grid control — the standard SAP table for displaying/editing data.

    This is NOT the same as GuiTableControl (dynpro table). GuiGridView is the
    modern ALV grid used in most list reports. Use this for reading table data,
    selecting rows, clicking cells, and accessing column metadata.

    Common in: SE16N results, SM37 job lists, SE09 transport lists, ALV reports.
    """
```

### 3. Pythonic naming (snake_case) but spec-traceable

Every property/method maps 1:1 to the spec. The mapping is:

- `PascalCase` COM property → `snake_case` Python property
- `Byte` (0/1) → `bool` (via `@property` returning `bool(self._com.X)`)
- `Long` → `int`
- `String` → `str`
- COM collections → Python iterables (implement `__iter__`, `__len__`, `__getitem__`)
- `FindById(id, raise?)` → `find_by_id(id, raise_error=True)` → typed wrapper or `None`

### 3. Two-level type dispatch in factory

When `find_by_id()` returns a COM object, the factory dispatches in two steps:

```python
# _factory.py

# Level 1: dispatch on TypeAsNumber (covers most types)
_TYPE_MAP: dict[int, type[GuiComponent]] = {
    10: GuiApplication,
    11: GuiConnection,
    12: GuiSession,
    21: GuiMainWindow,
    22: GuiModalWindow,
    23: GuiMessageWindow,
    30: GuiLabel,
    31: GuiTextField,
    32: GuiCTextField,
    33: GuiPasswordField,
    34: GuiComboBox,
    35: GuiOkCodeField,
    40: GuiButton,
    41: GuiRadioButton,
    42: GuiCheckBox,
    43: GuiStatusPane,
    50: GuiCustomControl,
    51: GuiContainerShell,
    62: GuiBox,
    71: GuiSimpleContainer,
    72: GuiScrollContainer,
    74: GuiUserArea,
    75: GuiSplitterContainer,
    80: GuiTableControl,
    90: GuiTabStrip,
    91: GuiTab,
    101: GuiToolbar,
    102: GuiTitlebar,
    103: GuiStatusbar,
    110: GuiMenu,
    111: GuiMenubar,
    122: GuiShell,  # fallback for unrecognized shell subtypes
    123: GuiGOSShell,
    125: GuiDialogShell,
    126: GuiDockShell,
    129: GuiVHViewSwitch,
    # ... complete enum
}

# Level 2: for GuiShell (type 122), dispatch on SubType string
_SHELL_SUBTYPE_MAP: dict[str, type[GuiShell]] = {
    "GridView": GuiGridView,
    "Tree": GuiTree,
    "TextEdit": GuiTextedit,
    "AbapEditor": GuiAbapEditor,
    "HTMLViewer": GuiHTMLViewer,
    "ToolbarControl": GuiToolbarControl,
    "Picture": GuiPicture,
    "Calendar": GuiCalendar,
    "ColorSelector": GuiColorSelector,
    "ComboBoxControl": GuiComboBoxControl,
    "InputFieldControl": GuiInputFieldControl,
    "Splitter": GuiSplit,
    # Deferred types fall back to GuiShell
}

def wrap_com_object(com_obj: CDispatch) -> GuiComponent:
    """Wrap a COM dispatch object in the correct typed Python class."""
    type_num = com_obj.TypeAsNumber
    cls = _TYPE_MAP.get(type_num)
    if cls is GuiShell or (cls is None and type_num == 122):
        # Second-level dispatch for shell subtypes
        sub_type = getattr(com_obj, "SubType", "")
        cls = _SHELL_SUBTYPE_MAP.get(sub_type, GuiShell)
    elif cls is None:
        cls = GuiComponent
    return cls(com_obj)
```

### 4. Entry points: connect and launch

```python
class SapGui:
    """Entry point for SAP GUI Scripting."""

    @staticmethod
    def connect() -> GuiApplication:
        """Attach to a running SAP GUI instance via the Running Object Table."""
        return _connect_to_running_sap_gui()

    @staticmethod
    def launch(
        exe_path: str,
        connection_string: str | None = None,
        timeout: int = 30,
    ) -> GuiApplication:
        """Launch SAP GUI executable, wait for it to be available, then connect.

        Args:
            exe_path: Path to saplogon.exe or saplgpad.exe
            connection_string: Optional connection string (e.g., "/R/ALR/G/SPACE").
                If provided, opens a connection automatically after launch.
            timeout: Max seconds to wait for SAP GUI to become available.

        Raises:
            SapGuiTimeoutError: If SAP GUI doesn't become available within timeout.
            SapConnectionError: If connection_string is provided but connection fails.
        """
        ...
```

`_connect_to_running_sap_gui()` and `_wait_for_sap_gui()` live in `_com.py`:

```python
# _com.py
def _connect_to_running_sap_gui() -> "GuiApplication":
    """Get SAPGUI from the Running Object Table and return the scripting engine."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()  # ensure COM is initialized on this thread
    try:
        rot_entry = win32com.client.GetObject("SAPGUI")
    except Exception as e:
        raise SapConnectionError("SAP GUI is not running or scripting is disabled") from e
    engine = rot_entry.GetScriptingEngine
    if engine is None:
        raise ScriptingDisabledError("Scripting engine not available — check server parameter sapgui/user_scripting")
    from .components.application import GuiApplication
    return GuiApplication(engine)

def _wait_for_sap_gui(timeout: int = 30) -> "GuiApplication":
    """Poll until SAPGUI ROT entry is available, then connect."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return _connect_to_running_sap_gui()
        except SapConnectionError:
            time.sleep(1)
    raise SapGuiTimeoutError(f"SAP GUI not available after {timeout}s")
```

### 5. Collections as Python iterables

```python
class GuiComponentCollection:
    """Wraps SAP's GuiComponentCollection with Python iteration."""

    def __init__(self, com_collection: CDispatch) -> None:
        self._com = com_collection

    def __len__(self) -> int:
        return self._com.Count

    def __getitem__(self, index: int) -> GuiComponent:
        return wrap_com_object(self._com.Item(index))

    def __iter__(self) -> Iterator[GuiComponent]:
        for i in range(len(self)):
            yield self[i]

    def __repr__(self) -> str:
        return f"<GuiComponentCollection count={len(self)}>"
```

### 6. Tree dump for screen inspection

Every `GuiVComponent` has `dump_state()` from the spec. Additionally, containers provide a recursive `dump_tree()` method that walks the element hierarchy and returns Pydantic models:

```python
class GuiVContainer(GuiContainer, GuiVComponent):

    def dump_tree(self, max_depth: int = 10) -> list[ElementInfo]:
        """Recursively dump the element tree as a list of ElementInfo models.

        Each ElementInfo contains: id, type, type_as_number, name, text, changeable, children.
        This is the desktop equivalent of a screen snapshot.
        """
        return _dump_tree_recursive(self._com, depth=0, max_depth=max_depth)
```

### 7. Repr for debugging

All base classes implement `__repr__` for REPL/debugging:

```python
class GuiComponent:
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id='{self.id}'>"
```

## ID Path System

SAP GUI elements have URL-like IDs: `/app/con[0]/ses[0]/wnd[0]/usr/txtRS38L-NAME`

The library supports both absolute and relative IDs (per spec):

- Absolute: starts with `/app/...`
- Relative: starts with type prefix, e.g. `wnd[0]/usr/txtRS38L-NAME` (relative to session)

```python
# Usage — identical to VBScript/SAP scripting patterns
session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE16"
session.find_by_id("wnd[0]").send_v_key(0)  # Enter
status = session.find_by_id("wnd[0]/sbar").text
```

## Dependencies

`pywin32` and `pydantic` are already main dependencies in `pyproject.toml`. No additional dependency group needed for the sapgui subpackage within this repo.

When this library is eventually extracted to its own PyPI package, it will declare its own dependencies:

- `pywin32>=306; sys_platform == 'win32'`
- `pydantic>=2.0` (for models.py — SessionInfo, ElementInfo)

## Error Handling

```python
# _errors.py
class SapGuiError(Exception):
    """Base exception for all pysapgui errors."""

class SapConnectionError(SapGuiError):
    """Failed to connect to SAP GUI (not running, access denied)."""

class ScriptingDisabledError(SapGuiError):
    """Scripting is disabled on the SAP server (sapgui/user_scripting=FALSE)."""

class ElementNotFoundError(SapGuiError):
    """Element with given ID not found in the GUI tree."""

class SapGuiTimeoutError(SapGuiError):
    """Timed out waiting for SAP GUI to become available."""
```

## Pydantic Models (for structured data exchange)

```python
from pydantic import BaseModel

class SessionInfo(BaseModel):
    """Structured session information from GuiSessionInfo."""
    system_name: str
    client: str
    user: str
    language: str
    transaction: str
    program: str
    screen_number: int
    application_server: str
    response_time: int
    round_trips: int

class ElementInfo(BaseModel):
    """Single element in a tree dump."""
    id: str
    type: str
    type_as_number: int
    name: str
    text: str
    changeable: bool
    children: list["ElementInfo"] = []
```

## Threading / COM Apartment

COM objects are apartment-threaded. `_com.py` calls `pythoncom.CoInitialize()` before accessing the Running Object Table. If the library is used from async code (e.g., the MCP backend), COM calls must happen on the thread that initialized COM. The MCP backend adapter (`backend/desktop/`) will handle this by running COM calls in a dedicated thread via `asyncio.to_thread()` or a thread executor.

## What Stays Unchanged

- `backend/protocol.py` — `SapUiBackend` protocol unchanged
- `backend/manager.py` — already prepared with `backend_type` config
- All existing WebGUI code — untouched
- All existing tools — untouched

## What Gets Added

1. `src/sapguimcp/sapgui/` — the library (this spec)
2. `unittests/sapgui/` — library tests
3. Later: `src/sapguimcp/backend/desktop/` — MCP backend adapter (separate spec)

## Implementation Order

1. **Core types and error classes** (`_types.py`, `_errors.py`)
2. **Base classes** (`base.py` — GuiComponent, GuiVComponent, GuiContainer, GuiVContainer)
3. **Collections** (`collection.py`)
4. **Factory** (`_factory.py` — two-level dispatch)
5. **COM helpers** (`_com.py` — connect, launch, wait)
6. **Entry points** (`__init__.py` — `SapGui.connect()`, `SapGui.launch()`)
7. **Session + Connection + Application** (`session.py`, `connection.py`, `application.py`)
8. **Window classes** (`window.py`)
9. **Input controls** (`field.py`, `button.py`, `checkbox.py`, `combobox.py`, `okcode.py`)
10. **Display controls** (`statusbar.py`, `toolbar.py`)
11. **Container controls** (`container.py`, `tab.py`)
12. **Table + Grid** (`table.py`, `grid.py`)
13. **Tree + Editor + Shell** (`tree.py`, `editor.py`, `shell.py`)
14. **Pydantic models** (`models.py`)
15. **Integration tests** against live SAP GUI
