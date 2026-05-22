# pysapgui Library Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, spec-compliant Python wrapper for the SAP GUI Scripting API (COM) as a subpackage at `src/sapguimcp/sapgui/`.

**Architecture:** Thin wrappers around `win32com.client.CDispatch` objects. Each Python class delegates property access to COM — no caching, no state. Two-level type dispatch factory resolves `TypeAsNumber` → class, with a second level for `GuiShell` subtypes via `SubType` string. Entry points connect to running SAP GUI via the Running Object Table (ROT).

**Tech Stack:** Python 3.11+, pywin32 (COM), pydantic (models), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-03-14-pysapgui-library-design.md`
**API Reference:** `docs/sap_gui_scripting_api_800/` (HTML), SAP GUI Scripting API 800

---

## File Structure

```
src/sapguimcp/sapgui/
  __init__.py              # public API: SapGui.connect(), SapGui.launch()
  _com.py                  # low-level COM helpers (GetObject, polling, CoInitialize)
  _types.py                # GuiComponentType enum, type prefix mappings
  _errors.py               # SapGuiError, ElementNotFoundError, etc.
  models.py                # Pydantic models: SessionInfo, ElementInfo
  components/
    __init__.py             # re-exports all component classes
    base.py                 # GuiComponent, GuiVComponent, GuiContainer, GuiVContainer
    application.py          # GuiApplication
    connection.py           # GuiConnection
    session.py              # GuiSession, GuiSessionInfo
    window.py               # GuiFrameWindow, GuiMainWindow, GuiModalWindow, GuiMessageWindow
    field.py                # GuiTextField, GuiCTextField, GuiPasswordField, GuiLabel, GuiBox
    button.py               # GuiButton
    checkbox.py             # GuiCheckBox, GuiRadioButton
    combobox.py             # GuiComboBox, GuiComboBoxEntry
    okcode.py               # GuiOkCodeField
    statusbar.py            # GuiStatusbar, GuiStatusPane
    toolbar.py              # GuiToolbar, GuiMenubar, GuiMenu, GuiTitlebar
    container.py            # GuiUserArea, GuiScrollContainer, GuiSimpleContainer,
                            # GuiContainerShell, GuiDialogShell, GuiCustomControl,
                            # GuiDockShell, GuiGOSShell, GuiSplitterContainer
    tab.py                  # GuiTabStrip, GuiTab
    table.py                # GuiTableControl, GuiTableRow, GuiTableColumn
    grid.py                 # GuiGridView (ALV)
    tree.py                 # GuiTree
    editor.py               # GuiTextedit, GuiAbapEditor
    shell.py                # GuiShell (base), GuiHTMLViewer, GuiToolbarControl, GuiPicture,
                            # GuiCalendar, GuiColorSelector, GuiComboBoxControl,
                            # GuiInputFieldControl, GuiSplit
    collection.py           # GuiCollection, GuiComponentCollection
  _factory.py               # wrap_com_object() — two-level dispatch (TypeAsNumber + SubType)

unittests/sapgui/
  __init__.py
  conftest.py               # shared fixtures (mock COM objects)
  test_types.py             # GuiComponentType enum tests
  test_errors.py            # error class tests
  test_base.py              # base class tests (mocked COM)
  test_collection.py        # collection tests
  test_factory.py           # type dispatch logic
  test_com.py               # COM helper tests (mocked)
  test_init.py              # SapGui entry point tests
  test_session.py           # GuiSession tests
  test_connection.py        # GuiConnection tests
  test_application.py       # GuiApplication tests
  test_window.py            # window class tests
  test_field.py             # text field tests
  test_button.py            # button tests
  test_checkbox.py          # checkbox/radio tests
  test_combobox.py          # combobox tests
  test_okcode.py            # okcode field tests
  test_statusbar.py         # statusbar tests
  test_toolbar.py           # toolbar/menubar tests
  test_container.py         # container tests
  test_tab.py               # tab tests
  test_table.py             # table control tests
  test_grid.py              # ALV grid tests
  test_tree.py              # tree tests
  test_editor.py            # text editor tests
  test_shell.py             # shell subclass tests
  test_models.py            # Pydantic model tests
  test_integration.py       # integration tests (live SAP GUI, skipped unless SAP available)
```

---

## Chunk 1: Foundation — Types, Errors, Base Classes, Collections

### Task 1: Error Classes

**Files:**

- Create: `src/sapguimcp/sapgui/_errors.py`
- Test: `unittests/sapgui/test_errors.py`

- [ ] **Step 1: Write error class tests**

```python
# unittests/sapgui/test_errors.py
"""Tests for pysapgui error hierarchy."""
from sapguimcp.sapgui._errors import (
    ElementNotFoundError,
    SapConnectionError,
    SapGuiError,
    SapGuiTimeoutError,
    ScriptingDisabledError,
)


def test_all_errors_extend_sap_gui_error():
    for cls in (SapConnectionError, ScriptingDisabledError, ElementNotFoundError, SapGuiTimeoutError):
        assert issubclass(cls, SapGuiError)


def test_sap_gui_error_extends_exception():
    assert issubclass(SapGuiError, Exception)


def test_element_not_found_stores_element_id():
    err = ElementNotFoundError("wnd[0]/usr/txtFOO")
    assert "wnd[0]/usr/txtFOO" in str(err)
```

- [ ] **Step 2: Run test — expect FAIL (module not found)**

Run: `python -m pytest unittests/sapgui/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sapguimcp.sapgui'`

- [ ] **Step 3: Create package structure and implement error classes**

Create `src/sapguimcp/sapgui/__init__.py` (empty for now), then:

```python
# src/sapguimcp/sapgui/_errors.py
"""Exception hierarchy for pysapgui."""


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

- [ ] **Step 4: Run test — expect PASS**

Run: `python -m pytest unittests/sapgui/test_errors.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/sapgui/__init__.py src/sapguimcp/sapgui/_errors.py unittests/sapgui/__init__.py unittests/sapgui/test_errors.py
git commit -m "feat(sapgui): add error class hierarchy"
```

---

### Task 2: GuiComponentType Enum

**Files:**

- Create: `src/sapguimcp/sapgui/_types.py`
- Test: `unittests/sapgui/test_types.py`

- [ ] **Step 1: Write enum tests**

```python
# unittests/sapgui/test_types.py
"""Tests for GuiComponentType enum and prefix mappings."""
from sapguimcp.sapgui._types import GuiComponentType, PREFIX_TO_TYPE_NAME


def test_enum_values_match_sap_spec():
    assert GuiComponentType.GuiApplication == 10
    assert GuiComponentType.GuiConnection == 11
    assert GuiComponentType.GuiSession == 12
    assert GuiComponentType.GuiMainWindow == 21
    assert GuiComponentType.GuiModalWindow == 22
    assert GuiComponentType.GuiMessageWindow == 23
    assert GuiComponentType.GuiTextField == 31
    assert GuiComponentType.GuiCTextField == 32
    assert GuiComponentType.GuiPasswordField == 33
    assert GuiComponentType.GuiComboBox == 34
    assert GuiComponentType.GuiOkCodeField == 35
    assert GuiComponentType.GuiButton == 40
    assert GuiComponentType.GuiRadioButton == 41
    assert GuiComponentType.GuiCheckBox == 42
    assert GuiComponentType.GuiShell == 122  # GuiGridView is NOT in enum — resolved by SubType
    assert GuiComponentType.GuiStatusbar == 103
    assert GuiComponentType.GuiTableControl == 80
    assert GuiComponentType.GuiLabel == 30


def test_prefix_mappings():
    assert PREFIX_TO_TYPE_NAME["txt"] == "GuiTextField"
    assert PREFIX_TO_TYPE_NAME["btn"] == "GuiButton"
    assert PREFIX_TO_TYPE_NAME["chk"] == "GuiCheckBox"
    assert PREFIX_TO_TYPE_NAME["cmb"] == "GuiComboBox"
    assert PREFIX_TO_TYPE_NAME["shell"] == "GuiShell"
    assert PREFIX_TO_TYPE_NAME["tbl"] == "GuiTableControl"


def test_enum_has_all_non_abstract_types():
    """Ensure the enum covers all concrete types from the spec."""
    # At minimum, these must exist (non-exhaustive spot check)
    required = [
        "GuiApplication", "GuiConnection", "GuiSession",
        "GuiMainWindow", "GuiModalWindow", "GuiTextField",
        "GuiButton", "GuiShell", "GuiTableControl", "GuiUserArea",
    ]
    member_names = [m.name for m in GuiComponentType]
    for name in required:
        assert name in member_names, f"{name} missing from GuiComponentType"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `python -m pytest unittests/sapgui/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement \_types.py**

```python
# src/sapguimcp/sapgui/_types.py
"""SAP GUI component type constants and prefix mappings.

Maps the numeric TypeAsNumber values from the SAP GUI Scripting API spec
to human-readable names. Used by the factory for type dispatch.
"""
from enum import IntEnum


class GuiComponentType(IntEnum):
    """Numeric type identifiers from the SAP GUI Scripting API.

    Values match COM object's TypeAsNumber property exactly.
    Abstract types (GuiComponent=0, GuiVComponent=1, GuiVContainer=2,
    GuiContainer=70, GuiFrameWindow=20) are included for completeness
    but never appear in practice.
    """

    # Abstract base types (never instantiated directly)
    GuiComponent = 0
    GuiVComponent = 1
    GuiVContainer = 2
    GuiFrameWindow = 20
    GuiContainer = 70

    # Top-level objects
    GuiApplication = 10
    GuiConnection = 11
    GuiSession = 12

    # Windows
    GuiMainWindow = 21
    GuiModalWindow = 22
    GuiMessageWindow = 23

    # Input fields
    GuiLabel = 30
    GuiTextField = 31
    GuiCTextField = 32
    GuiPasswordField = 33
    GuiComboBox = 34
    GuiOkCodeField = 35

    # Buttons and selection
    GuiButton = 40
    GuiRadioButton = 41
    GuiCheckBox = 42
    GuiStatusPane = 43

    # Custom/shell containers
    GuiCustomControl = 50
    GuiContainerShell = 51

    # Display
    GuiBox = 62

    # Containers
    GuiSimpleContainer = 71
    GuiScrollContainer = 72
    GuiUserArea = 74
    GuiSplitterContainer = 75

    # Table
    GuiTableControl = 80

    # Tabs
    GuiTabStrip = 90
    GuiTab = 91

    # Scrollbar
    GuiScrollbar = 100

    # Toolbar / status
    GuiToolbar = 101
    GuiTitlebar = 102
    GuiStatusbar = 103

    # Menu
    GuiMenu = 110
    GuiMenubar = 111

    # Collections and info
    GuiCollection = 120
    GuiSessionInfo = 121
    GuiShell = 122  # base for all shell subtypes (GridView, Tree, etc.)
    GuiGOSShell = 123
    GuiDialogShell = 125
    GuiDockShell = 126
    GuiComponentCollection = 128
    GuiVHViewSwitch = 129


# Type prefix → class name (used for ID parsing and debugging)
PREFIX_TO_TYPE_NAME: dict[str, str] = {
    "txt": "GuiTextField",
    "ctxt": "GuiCTextField",
    "pwd": "GuiPasswordField",
    "lbl": "GuiLabel",
    "btn": "GuiButton",
    "chk": "GuiCheckBox",
    "rad": "GuiRadioButton",
    "cmb": "GuiComboBox",
    "okcd": "GuiOkCodeField",
    "box": "GuiBox",
    "pane": "GuiStatusPane",
    "wnd": "GuiFrameWindow",
    "usr": "GuiUserArea",
    "sub": "GuiSimpleContainer",
    "ssub": "GuiScrollContainer",
    "cntl": "GuiCustomControl",
    "shellcont": "GuiContainerShell",
    "tbar": "GuiToolbar",
    "titl": "GuiTitlebar",
    "sbar": "GuiStatusbar",
    "menu": "GuiMenu",
    "mbar": "GuiMenubar",
    "tabs": "GuiTabStrip",
    "tabp": "GuiTab",
    "tbl": "GuiTableControl",
    "shell": "GuiShell",
}

# GuiShell SubType string → class name (for second-level dispatch)
SHELL_SUBTYPE_NAMES: dict[str, str] = {
    "GridView": "GuiGridView",
    "Tree": "GuiTree",
    "TextEdit": "GuiTextedit",
    "AbapEditor": "GuiAbapEditor",
    "HTMLViewer": "GuiHTMLViewer",
    "ToolbarControl": "GuiToolbarControl",
    "Picture": "GuiPicture",
    "Calendar": "GuiCalendar",
    "ColorSelector": "GuiColorSelector",
    "ComboBoxControl": "GuiComboBoxControl",
    "InputFieldControl": "GuiInputFieldControl",
    "Splitter": "GuiSplit",
}
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python -m pytest unittests/sapgui/test_types.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/sapgui/_types.py unittests/sapgui/test_types.py
git commit -m "feat(sapgui): add GuiComponentType enum and prefix mappings"
```

---

### Task 3: Test Fixtures (Mock COM Objects)

**Files:**

- Create: `unittests/sapgui/conftest.py`

- [ ] **Step 1: Create shared mock COM fixture**

```python
# unittests/sapgui/conftest.py
"""Shared fixtures for pysapgui unit tests.

Provides mock COM dispatch objects that simulate SAP GUI Scripting API
behavior without requiring a running SAP GUI instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest


def make_mock_com(
    *,
    type_as_number: int = 0,
    type_name: str = "GuiComponent",
    id: str = "/app/con[0]/ses[0]/wnd[0]",
    name: str = "wnd",
    container_type: bool = False,
    text: str = "",
    tooltip: str = "",
    changeable: bool = True,
    children: list | None = None,
    **extra_props: object,
) -> MagicMock:
    """Create a mock COM dispatch object with standard SAP GUI properties.

    Args:
        type_as_number: The TypeAsNumber value (maps to GuiComponentType).
        type_name: The Type string (class name like "GuiMainWindow").
        id: The element's full ID path.
        name: The element's Name property.
        container_type: Whether this is a container (has Children).
        text: The Text property value.
        tooltip: The Tooltip property value.
        changeable: The Changeable property (1=True, 0=False).
        children: List of child mock COM objects (for containers).
        **extra_props: Additional COM properties to set.
    """
    mock = MagicMock()
    mock.TypeAsNumber = type_as_number
    mock.Type = type_name
    mock.Id = id
    mock.Name = name
    mock.ContainerType = 1 if container_type else 0
    mock.Text = text
    mock.Tooltip = tooltip
    mock.Changeable = 1 if changeable else 0
    mock.Parent = MagicMock()
    mock.Height = 24
    mock.Width = 200
    mock.Left = 0
    mock.Top = 0
    mock.ScreenLeft = 100
    mock.ScreenTop = 100
    mock.Modified = 0
    mock.IconName = ""
    mock.IsSymbolFont = 0
    mock.AccText = ""
    mock.AccTooltip = ""
    mock.AccTextOnRequest = ""
    mock.DefaultTooltip = ""

    if container_type and children is not None:
        child_collection = MagicMock()
        child_collection.Count = len(children)
        child_collection.Item = lambda i: children[i]
        child_collection.__iter__ = lambda self: iter(children)
        mock.Children = child_collection
    elif container_type:
        child_collection = MagicMock()
        child_collection.Count = 0
        mock.Children = child_collection

    for prop_name, prop_value in extra_props.items():
        setattr(mock, prop_name, prop_value)

    return mock


@pytest.fixture
def mock_com():
    """Factory fixture — call with keyword args to create a mock COM object."""
    return make_mock_com
```

- [ ] **Step 2: Commit**

```bash
git add unittests/sapgui/conftest.py
git commit -m "test(sapgui): add shared mock COM fixtures"
```

---

### Task 4: Base Classes — GuiComponent, GuiVComponent, GuiContainer, GuiVContainer

**Files:**

- Create: `src/sapguimcp/sapgui/components/__init__.py`
- Create: `src/sapguimcp/sapgui/components/base.py`
- Test: `unittests/sapgui/test_base.py`

- [ ] **Step 1: Write base class tests**

```python
# unittests/sapgui/test_base.py
"""Tests for base component classes (mocked COM)."""
from __future__ import annotations

from unittest.mock import MagicMock

from sapguimcp.sapgui.components.base import (
    GuiComponent,
    GuiContainer,
    GuiVComponent,
    GuiVContainer,
)


class TestGuiComponent:
    def test_id_property(self, mock_com):
        com = mock_com(id="/app/con[0]/ses[0]/wnd[0]")
        comp = GuiComponent(com)
        assert comp.id == "/app/con[0]/ses[0]/wnd[0]"

    def test_name_property(self, mock_com):
        com = mock_com(name="wnd")
        comp = GuiComponent(com)
        assert comp.name == "wnd"

    def test_type_property(self, mock_com):
        com = mock_com(type_name="GuiMainWindow")
        comp = GuiComponent(com)
        assert comp.type == "GuiMainWindow"

    def test_type_as_number(self, mock_com):
        com = mock_com(type_as_number=21)
        comp = GuiComponent(com)
        assert comp.type_as_number == 21

    def test_container_type(self, mock_com):
        com = mock_com(container_type=True)
        comp = GuiComponent(com)
        assert comp.container_type is True

    def test_parent_returns_raw_com(self, mock_com):
        com = mock_com()
        comp = GuiComponent(com)
        # parent returns raw COM — wrapping is the factory's job
        assert comp.parent is com.Parent

    def test_repr(self, mock_com):
        com = mock_com(id="/app/con[0]/ses[0]/wnd[0]")
        comp = GuiComponent(com)
        assert repr(comp) == "<GuiComponent id='/app/con[0]/ses[0]/wnd[0]'>"

    def test_com_property_exposes_underlying_object(self, mock_com):
        com = mock_com()
        comp = GuiComponent(com)
        assert comp.com is com


class TestGuiVComponent:
    def test_text_property(self, mock_com):
        com = mock_com(text="Hello")
        vc = GuiVComponent(com)
        assert vc.text == "Hello"

    def test_text_setter(self, mock_com):
        com = mock_com(text="")
        vc = GuiVComponent(com)
        vc.text = "New Value"
        assert com.Text == "New Value"

    def test_changeable(self, mock_com):
        com = mock_com(changeable=True)
        vc = GuiVComponent(com)
        assert vc.changeable is True

    def test_not_changeable(self, mock_com):
        com = mock_com(changeable=False)
        vc = GuiVComponent(com)
        assert vc.changeable is False

    def test_tooltip(self, mock_com):
        com = mock_com(tooltip="Enter value")
        vc = GuiVComponent(com)
        assert vc.tooltip == "Enter value"

    def test_set_focus_delegates(self, mock_com):
        com = mock_com()
        vc = GuiVComponent(com)
        vc.set_focus()
        com.SetFocus.assert_called_once()

    def test_dimensions(self, mock_com):
        com = mock_com()
        com.Height = 24
        com.Width = 200
        com.Left = 10
        com.Top = 20
        vc = GuiVComponent(com)
        assert vc.height == 24
        assert vc.width == 200
        assert vc.left == 10
        assert vc.top == 20

    def test_screen_coordinates(self, mock_com):
        com = mock_com()
        com.ScreenLeft = 150
        com.ScreenTop = 300
        vc = GuiVComponent(com)
        assert vc.screen_left == 150
        assert vc.screen_top == 300

    def test_modified(self, mock_com):
        com = mock_com()
        com.Modified = 1
        vc = GuiVComponent(com)
        assert vc.modified is True

    def test_icon_name(self, mock_com):
        com = mock_com()
        com.IconName = "@01@"
        vc = GuiVComponent(com)
        assert vc.icon_name == "@01@"


class TestGuiContainer:
    def test_children_count(self, mock_com):
        child1 = mock_com(id="child1", type_as_number=31)
        child2 = mock_com(id="child2", type_as_number=40)
        com = mock_com(container_type=True, children=[child1, child2])
        container = GuiContainer(com)
        assert container.children.Count == 2

    def test_find_by_id_delegates(self, mock_com):
        com = mock_com(container_type=True, children=[])
        found = mock_com(id="wnd[0]/usr/txtFOO", type_as_number=31, type_name="GuiTextField")
        com.FindById.return_value = found
        container = GuiContainer(com)
        result = container.find_by_id("wnd[0]/usr/txtFOO")
        com.FindById.assert_called_once_with("wnd[0]/usr/txtFOO", False)
        # Returns a typed wrapper via wrap_com_object
        from sapguimcp.sapgui.components.field import GuiTextField

        assert isinstance(result, GuiTextField)
        assert result._com is found

    def test_find_by_id_returns_none_when_not_found(self, mock_com):
        com = mock_com(container_type=True, children=[])
        com.FindById.return_value = None
        container = GuiContainer(com)
        result = container.find_by_id("wnd[0]/usr/txtNOPE", raise_error=False)
        assert result is None

    def test_find_by_id_raises_when_not_found(self, mock_com):
        import pytest
        from sapguimcp.sapgui._errors import ElementNotFoundError

        com = mock_com(container_type=True, children=[])
        com.FindById.return_value = None
        container = GuiContainer(com)
        with pytest.raises(ElementNotFoundError):
            container.find_by_id("wnd[0]/usr/txtNOPE", raise_error=True)


class TestGuiVContainer:
    def test_inherits_both_interfaces(self):
        assert issubclass(GuiVContainer, GuiContainer)
        assert issubclass(GuiVContainer, GuiVComponent)

    def test_find_by_name_delegates(self, mock_com):
        com = mock_com(container_type=True, children=[])
        found = mock_com(id="wnd[0]/usr/txtFOO", type_as_number=31)
        com.FindByName.return_value = found
        vc = GuiVContainer(com)
        result = vc.find_by_name("FOO", "GuiTextField")
        com.FindByName.assert_called_once_with("FOO", "GuiTextField")

    def test_find_by_name_ex_delegates(self, mock_com):
        com = mock_com(container_type=True, children=[])
        com.FindByNameEx.return_value = MagicMock()
        vc = GuiVContainer(com)
        vc.find_by_name_ex("FOO", 31)
        com.FindByNameEx.assert_called_once_with("FOO", 31)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest unittests/sapgui/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement base classes**

```python
# src/sapguimcp/sapgui/components/__init__.py
"""SAP GUI component wrappers."""
```

```python
# src/sapguimcp/sapgui/components/base.py
"""Base classes for SAP GUI component wrappers.

Inheritance hierarchy (mirrors SAP GUI Scripting API):
  GuiComponent — base for all objects
  ├── GuiContainer — administrative containers (FindById, Children)
  ├── GuiVComponent — visual objects (Text, SetFocus, dimensions)
  └── GuiVContainer(GuiContainer, GuiVComponent) — visual containers
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sapguimcp.sapgui._errors import ElementNotFoundError

if TYPE_CHECKING:
    pass


class GuiComponent:
    """Base class for all SAP GUI Scripting objects.

    Wraps a win32com.client.CDispatch COM object. All property access
    delegates directly to the COM object — no caching, no state.
    """

    def __init__(self, com_object: Any) -> None:
        self._com = com_object

    @property
    def com(self) -> Any:
        """The underlying COM dispatch object."""
        return self._com

    @property
    def id(self) -> str:
        return self._com.Id

    @property
    def name(self) -> str:
        return self._com.Name

    @property
    def type(self) -> str:
        return self._com.Type

    @property
    def type_as_number(self) -> int:
        return self._com.TypeAsNumber

    @property
    def container_type(self) -> bool:
        return bool(self._com.ContainerType)

    @property
    def parent(self) -> Any:
        """Parent object (raw COM). Use the factory to wrap if needed."""
        return self._com.Parent

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id='{self.id}'>"


class GuiVComponent(GuiComponent):
    """Visual component — extends GuiComponent with UI properties.

    All visible SAP GUI elements (fields, buttons, labels, windows)
    inherit from this. Provides Text, Tooltip, Changeable, dimensions,
    SetFocus, and DumpState.
    """

    @property
    def text(self) -> str:
        return self._com.Text

    @text.setter
    def text(self, value: str) -> None:
        self._com.Text = value

    @property
    def tooltip(self) -> str:
        return self._com.Tooltip

    @property
    def default_tooltip(self) -> str:
        return self._com.DefaultTooltip

    @property
    def changeable(self) -> bool:
        return bool(self._com.Changeable)

    @property
    def modified(self) -> bool:
        return bool(self._com.Modified)

    @property
    def height(self) -> int:
        return self._com.Height

    @property
    def width(self) -> int:
        return self._com.Width

    @property
    def left(self) -> int:
        return self._com.Left

    @property
    def top(self) -> int:
        return self._com.Top

    @property
    def screen_left(self) -> int:
        return self._com.ScreenLeft

    @property
    def screen_top(self) -> int:
        return self._com.ScreenTop

    @property
    def icon_name(self) -> str:
        return self._com.IconName

    @property
    def is_symbol_font(self) -> bool:
        return bool(self._com.IsSymbolFont)

    @property
    def acc_text(self) -> str:
        return self._com.AccText

    @property
    def acc_tooltip(self) -> str:
        return self._com.AccTooltip

    @property
    def acc_text_on_request(self) -> str:
        return self._com.AccTextOnRequest

    def set_focus(self) -> None:
        """Set input focus to this component."""
        self._com.SetFocus()

    def visualize(self, on: bool = True) -> bool:
        """Display a red frame around this component for debugging."""
        return bool(self._com.Visualize(on))

    def dump_state(self, inner_object: str = "") -> Any:
        """Dump component state as a GuiCollection of key-value pairs."""
        return self._com.DumpState(inner_object)


class GuiContainer(GuiComponent):
    """Administrative container — objects that have children (FindById).

    Used for non-visual containers like GuiApplication, GuiConnection,
    GuiSession. Visual containers use GuiVContainer instead.
    """

    @property
    def children(self) -> Any:
        """Direct children as a COM collection. Use GuiComponentCollection to wrap."""
        return self._com.Children

    def find_by_id(self, id: str, raise_error: bool = True) -> GuiComponent | None:
        """Find a descendant by its ID path, returning a typed wrapper.

        Args:
            id: Element ID (absolute or relative to this container).
            raise_error: If True, raise ElementNotFoundError when not found.
                If False, return None.

        Returns:
            A typed wrapper (e.g., GuiTextField, GuiButton), or None if
            not found and raise_error=False.
        """
        from sapguimcp.sapgui._factory import wrap_com_object

        result = self._com.FindById(id, False)
        if result is None:
            if raise_error:
                raise ElementNotFoundError(f"Element not found: {id}")
            return None
        return wrap_com_object(result)


class GuiVContainer(GuiContainer, GuiVComponent):
    """Visual container — combines GuiContainer + GuiVComponent.

    Windows, toolbars, user areas, tab strips, and other visible
    containers that can have children. Adds FindByName/FindAllByName.
    """

    def find_by_name(self, name: str, type_name: str) -> Any:
        """Find first descendant matching name and type string."""
        return self._com.FindByName(name, type_name)

    def find_by_name_ex(self, name: str, type_number: int) -> Any:
        """Find first descendant matching name and numeric type."""
        return self._com.FindByNameEx(name, type_number)

    def find_all_by_name(self, name: str, type_name: str) -> Any:
        """Find all descendants matching name and type string."""
        return self._com.FindAllByName(name, type_name)

    def find_all_by_name_ex(self, name: str, type_number: int) -> Any:
        """Find all descendants matching name and numeric type."""
        return self._com.FindAllByNameEx(name, type_number)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_base.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/sapgui/components/__init__.py src/sapguimcp/sapgui/components/base.py unittests/sapgui/test_base.py
git commit -m "feat(sapgui): add base component classes (GuiComponent, GuiVComponent, GuiContainer, GuiVContainer)"
```

---

### Task 5: Collection Wrappers

**Files:**

- Create: `src/sapguimcp/sapgui/components/collection.py`
- Test: `unittests/sapgui/test_collection.py`

- [ ] **Step 1: Write collection tests**

```python
# unittests/sapgui/test_collection.py
"""Tests for collection wrappers."""
from __future__ import annotations

from unittest.mock import MagicMock

from sapguimcp.sapgui.components.collection import GuiCollection, GuiComponentCollection


class TestGuiComponentCollection:
    def test_len(self):
        com = MagicMock()
        com.Count = 3
        coll = GuiComponentCollection(com)
        assert len(coll) == 3

    def test_getitem(self):
        items = [MagicMock(), MagicMock()]
        com = MagicMock()
        com.Count = 2
        com.Item = lambda i: items[i]
        coll = GuiComponentCollection(com)
        assert coll[0] is items[0]
        assert coll[1] is items[1]

    def test_iter(self):
        items = [MagicMock(), MagicMock(), MagicMock()]
        com = MagicMock()
        com.Count = 3
        com.Item = lambda i: items[i]
        coll = GuiComponentCollection(com)
        assert list(coll) == items

    def test_repr(self):
        com = MagicMock()
        com.Count = 5
        coll = GuiComponentCollection(com)
        assert repr(coll) == "<GuiComponentCollection count=5>"

    def test_empty_collection(self):
        com = MagicMock()
        com.Count = 0
        coll = GuiComponentCollection(com)
        assert len(coll) == 0
        assert list(coll) == []


class TestGuiCollection:
    def test_len(self):
        com = MagicMock()
        com.Count = 2
        coll = GuiCollection(com)
        assert len(coll) == 2

    def test_getitem(self):
        items = [MagicMock()]
        com = MagicMock()
        com.Count = 1
        com.Item = lambda i: items[i]
        coll = GuiCollection(com)
        assert coll[0] is items[0]

    def test_repr(self):
        com = MagicMock()
        com.Count = 7
        coll = GuiCollection(com)
        assert repr(coll) == "<GuiCollection count=7>"
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest unittests/sapgui/test_collection.py -v`

- [ ] **Step 3: Implement collections**

```python
# src/sapguimcp/sapgui/components/collection.py
"""SAP GUI collection wrappers with Python iteration support."""
from __future__ import annotations

from typing import Any, Iterator


class GuiComponentCollection:
    """Wraps SAP's GuiComponentCollection with Python iteration.

    Items are raw COM objects. Use the factory to wrap them in typed classes.
    """

    def __init__(self, com_collection: Any) -> None:
        self._com = com_collection

    def __len__(self) -> int:
        return self._com.Count

    def __getitem__(self, index: int) -> Any:
        return self._com.Item(index)

    def __iter__(self) -> Iterator[Any]:
        for i in range(len(self)):
            yield self[i]

    def __repr__(self) -> str:
        return f"<GuiComponentCollection count={len(self)}>"


class GuiCollection:
    """Wraps SAP's GuiCollection (generic, non-typed collection).

    Used for DumpState results and CreateGuiCollection returns.
    """

    def __init__(self, com_collection: Any) -> None:
        self._com = com_collection

    def __len__(self) -> int:
        return self._com.Count

    def __getitem__(self, index: int) -> Any:
        return self._com.Item(index)

    def __iter__(self) -> Iterator[Any]:
        for i in range(len(self)):
            yield self[i]

    def __repr__(self) -> str:
        return f"<GuiCollection count={len(self)}>"
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_collection.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/sapgui/components/collection.py unittests/sapgui/test_collection.py
git commit -m "feat(sapgui): add GuiCollection and GuiComponentCollection wrappers"
```

---

## Chunk 2: Factory, COM Helpers, Entry Points

### Task 6: Two-Level Type Dispatch Factory

**Files:**

- Create: `src/sapguimcp/sapgui/_factory.py`
- Test: `unittests/sapgui/test_factory.py`

- [ ] **Step 1: Write factory tests**

```python
# unittests/sapgui/test_factory.py
"""Tests for two-level type dispatch factory."""
from __future__ import annotations

from unittest.mock import MagicMock

from conftest import make_mock_com

from sapguimcp.sapgui._factory import wrap_com_object
from sapguimcp.sapgui._types import GuiComponentType
from sapguimcp.sapgui.components.base import GuiComponent, GuiVComponent, GuiVContainer


def test_wrap_main_window():
    from sapguimcp.sapgui.components.window import GuiMainWindow

    com = make_mock_com(type_as_number=21, type_name="GuiMainWindow", container_type=True)
    result = wrap_com_object(com)
    assert isinstance(result, GuiMainWindow)


def test_wrap_text_field():
    from sapguimcp.sapgui.components.field import GuiTextField

    com = make_mock_com(type_as_number=31, type_name="GuiTextField")
    result = wrap_com_object(com)
    assert isinstance(result, GuiTextField)


def test_wrap_button():
    from sapguimcp.sapgui.components.button import GuiButton

    com = make_mock_com(type_as_number=40, type_name="GuiButton")
    result = wrap_com_object(com)
    assert isinstance(result, GuiButton)


def test_wrap_shell_dispatches_to_grid_view():
    from sapguimcp.sapgui.components.grid import GuiGridView

    com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType="GridView")
    result = wrap_com_object(com)
    assert isinstance(result, GuiGridView)


def test_wrap_shell_dispatches_to_tree():
    from sapguimcp.sapgui.components.tree import GuiTree

    com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType="Tree")
    result = wrap_com_object(com)
    assert isinstance(result, GuiTree)


def test_wrap_shell_unknown_subtype_falls_back_to_gui_shell():
    from sapguimcp.sapgui.components.shell import GuiShell

    com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType="SomeUnknownControl")
    result = wrap_com_object(com)
    assert type(result) is GuiShell


def test_wrap_unknown_type_falls_back_to_gui_component():
    com = make_mock_com(type_as_number=9999, type_name="GuiUnknown")
    result = wrap_com_object(com)
    assert type(result) is GuiComponent


def test_wrap_all_type_map_entries_resolve():
    """Every entry in _TYPE_MAP should produce a valid class instance."""
    from sapguimcp.sapgui._factory import _TYPE_MAP

    for type_num, cls in _TYPE_MAP.items():
        com = make_mock_com(type_as_number=type_num, container_type=True)
        result = wrap_com_object(com)
        assert isinstance(result, cls), f"Type {type_num} should produce {cls.__name__}"


def test_wrap_all_shell_subtypes_resolve():
    """Every entry in _SHELL_SUBTYPE_MAP should produce a valid class instance."""
    from sapguimcp.sapgui._factory import _SHELL_SUBTYPE_MAP

    for sub_type, cls in _SHELL_SUBTYPE_MAP.items():
        com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType=sub_type)
        result = wrap_com_object(com)
        assert isinstance(result, cls), f"SubType '{sub_type}' should produce {cls.__name__}"
```

- [ ] **Step 2: Run tests — expect FAIL (missing component modules)**

Run: `python -m pytest unittests/sapgui/test_factory.py -v`
Expected: FAIL — component modules don't exist yet

- [ ] **Step 3: Create stub component files**

Before implementing the factory, we need minimal stubs for all component classes so the factory imports work. Each stub file will have the class inheriting from the correct base.

Create all component stubs (these will be fleshed out in later tasks).

**Important:** application.py, connection.py, and session.py are also created as
stubs here so the factory can import them. They get their full implementations
in Tasks 8-10, but the stubs must exist now for the factory's \_TYPE_MAP.

```python
# src/sapguimcp/sapgui/components/application.py
"""GuiApplication — stub (full implementation in Task 8)."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiContainer


class GuiApplication(GuiContainer):
    """Represents the SAP GUI process (type 10). Full impl in Task 8."""
```

```python
# src/sapguimcp/sapgui/components/connection.py
"""GuiConnection — stub (full implementation in Task 9)."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiContainer


class GuiConnection(GuiContainer):
    """Represents a SAP connection (type 11). Full impl in Task 9."""
```

```python
# src/sapguimcp/sapgui/components/session.py
"""GuiSession — stub (full implementation in Task 10)."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiContainer


class GuiSession(GuiContainer):
    """Represents a SAP session (type 12). Full impl in Task 10."""
```

```python
# src/sapguimcp/sapgui/components/shell.py
"""GuiShell base and shell subclasses."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVContainer


class GuiShell(GuiVContainer):
    """Base class for all shell-hosted controls (type 122).

    Shell controls are complex embedded controls identified by their SubType
    property. If the SubType is unrecognized, you get a plain GuiShell.
    """

    @property
    def sub_type(self) -> str:
        return self._com.SubType

    @property
    def handle(self) -> int:
        return self._com.Handle

    @property
    def acc_description(self) -> str:
        return self._com.AccDescription

    @property
    def drag_drop_supported(self) -> bool:
        return bool(self._com.DragDropSupported)

    @property
    def ocx_events(self) -> bool:
        return bool(self._com.OcxEvents)

    def select_context_menu_item(self, item_id: str) -> None:
        self._com.SelectContextMenuItem(item_id)

    def select_context_menu_item_by_position(self, position: str) -> None:
        self._com.SelectContextMenuItemByPosition(position)

    def select_context_menu_item_by_text(self, text: str) -> None:
        self._com.SelectContextMenuItemByText(text)


class GuiHTMLViewer(GuiShell):
    """Embedded HTML viewer (SubType: HTMLViewer)."""

    @property
    def browser_handle(self) -> object:
        return self._com.BrowserHandle

    @property
    def document_complete(self) -> int:
        return self._com.DocumentComplete

    def sap_event(self, frame_name: str, post_data: str, url: str) -> None:
        self._com.SapEvent(frame_name, post_data, url)

    def get_browser_control_type(self) -> int:
        return self._com.GetBrowerControlType()


class GuiToolbarControl(GuiShell):
    """Shell-hosted toolbar control (SubType: ToolbarControl).

    Not the same as GuiToolbar (dynpro toolbar). This is an embedded
    toolbar inside a shell container, common in ALV grid headers.
    """

    @property
    def button_count(self) -> int:
        return self._com.ButtonCount

    @property
    def focused_button(self) -> int:
        return self._com.FocusedButton

    def get_button_id(self, pos: int) -> str:
        return self._com.GetButtonId(pos)

    def get_button_text(self, pos: int) -> str:
        return self._com.GetButtonText(pos)

    def get_button_tooltip(self, pos: int) -> str:
        return self._com.GetButtonTooltip(pos)

    def get_button_type(self, pos: int) -> str:
        return self._com.GetButtonType(pos)

    def get_button_enabled(self, pos: int) -> bool:
        return bool(self._com.GetButtonEnabled(pos))

    def get_button_checked(self, pos: int) -> bool:
        return bool(self._com.GetButtonChecked(pos))

    def get_button_icon(self, pos: int) -> str:
        return self._com.GetButtonIcon(pos)

    def press_button(self, button_id: str) -> None:
        self._com.PressButton(button_id)

    def press_context_button(self, button_id: str) -> None:
        self._com.PressContextButton(button_id)

    def select_menu_item(self, item_id: str) -> None:
        self._com.SelectMenuItem(item_id)

    def select_menu_item_by_text(self, text: str) -> None:
        self._com.SelectMenuItemByText(text)


class GuiPicture(GuiShell):
    """Image display control (SubType: Picture)."""


class GuiCalendar(GuiShell):
    """Date picker calendar control (SubType: Calendar)."""


class GuiColorSelector(GuiShell):
    """Color selection control (SubType: ColorSelector)."""

    def change_selection(self, index: int) -> None:
        self._com.ChangeSelection(index)


class GuiComboBoxControl(GuiShell):
    """Shell-hosted combo box (SubType: ComboBoxControl).

    Not the same as GuiComboBox (dynpro combo). This is an embedded
    combo box inside a shell container.
    """


class GuiInputFieldControl(GuiShell):
    """Shell-hosted input field (SubType: InputFieldControl).

    Not the same as GuiTextField (dynpro field). This is an embedded
    input field inside a shell container.
    """


class GuiSplit(GuiShell):
    """Splitter control (SubType: Splitter)."""
```

```python
# src/sapguimcp/sapgui/components/window.py
"""Window classes."""
from __future__ import annotations
from typing import Any
from sapguimcp.sapgui.components.base import GuiVContainer


class GuiFrameWindow(GuiVContainer):
    """Abstract base for all SAP GUI windows (type 20).

    Pressing a button or sending a VKey may invalidate all element
    references below the window level — re-find elements after
    any server round trip.
    """

    @property
    def handle(self) -> int:
        return self._com.Handle

    @property
    def iconic(self) -> bool:
        return bool(self._com.Iconic)

    @property
    def gui_focus(self) -> Any:
        return self._com.GuiFocus

    @property
    def system_focus(self) -> Any:
        return self._com.SystemFocus

    @property
    def working_pane_height(self) -> int:
        return self._com.WorkingPaneHeight

    @property
    def working_pane_width(self) -> int:
        return self._com.WorkingPaneWidth

    @property
    def element_visualization_mode(self) -> bool:
        return bool(self._com.ElementVisualizationMode)

    def close(self) -> None:
        self._com.Close()

    def iconify(self) -> None:
        self._com.Iconify()

    def maximize(self) -> None:
        self._com.Maximize()

    def restore(self) -> None:
        self._com.Restore()

    def send_v_key(self, v_key: int) -> None:
        """Send a virtual key (e.g., 0=Enter, 2=F2, 8=F8, 12=F12/Cancel)."""
        self._com.SendVKey(v_key)

    def is_v_key_allowed(self, v_key: int) -> bool:
        return bool(self._com.IsVKeyAllowed(v_key))

    def hard_copy(self, filename: str, image_type: int) -> str:
        return self._com.HardCopy(filename, image_type)

    def tab_forward(self) -> None:
        self._com.TabForward()

    def tab_backward(self) -> None:
        self._com.TabBackward()

    def jump_forward(self) -> None:
        self._com.JumpForward()

    def jump_backward(self) -> None:
        self._com.JumpBackward()


class GuiMainWindow(GuiFrameWindow):
    """Primary SAP GUI application window (type 21).

    Each session has exactly one main window. Access via
    session.find_by_id("wnd[0]").
    """

    @property
    def buttonbar_visible(self) -> bool:
        return bool(self._com.ButtonbarVisible)

    @buttonbar_visible.setter
    def buttonbar_visible(self, value: bool) -> None:
        self._com.ButtonbarVisible = 1 if value else 0

    @property
    def toolbar_visible(self) -> bool:
        return bool(self._com.ToolbarVisible)

    @toolbar_visible.setter
    def toolbar_visible(self, value: bool) -> None:
        self._com.ToolbarVisible = 1 if value else 0

    @property
    def statusbar_visible(self) -> bool:
        return bool(self._com.StatusbarVisible)

    @statusbar_visible.setter
    def statusbar_visible(self, value: bool) -> None:
        self._com.StatusbarVisible = 1 if value else 0

    @property
    def titlebar_visible(self) -> bool:
        return bool(self._com.TitlebarVisible)

    @titlebar_visible.setter
    def titlebar_visible(self, value: bool) -> None:
        self._com.TitlebarVisible = 1 if value else 0

    def resize_working_pane(self, width: int, height: int, throw_on_fail: bool = True) -> None:
        self._com.ResizeWorkingPane(width, height, throw_on_fail)

    def resize_working_pane_ex(self, width: int, height: int, throw_on_fail: bool = True) -> None:
        self._com.ResizeWorkingPaneEx(width, height, throw_on_fail)


class GuiModalWindow(GuiFrameWindow):
    """Modal dialog window (type 22).

    Popups, confirmation dialogs, search helps. Usually accessed via
    session.find_by_id("wnd[1]") or higher indices.
    """

    @property
    def is_popup(self) -> bool:
        return bool(self._com.IsPopup) if hasattr(self._com, "IsPopup") else True


class GuiMessageWindow(GuiVComponent):
    """Notification message window (type 23) for success/warning/error messages.

    Appears when SAP GUI notification options are enabled. Extends GuiVComponent
    (NOT GuiFrameWindow) — it's a simple notification, not a full window.
    """

    @property
    def message_text(self) -> str:
        return self._com.MessageText

    @property
    def message_type(self) -> int:
        """Message type: 2=Warning, 3=Error, 5=Success."""
        return self._com.MessageType

    @property
    def ok_button_text(self) -> str:
        return self._com.OKButtonText

    @property
    def help_button_text(self) -> str:
        return self._com.HelpButtonText

    @property
    def focused_button(self) -> int:
        return self._com.FocusedButton

    @property
    def visible(self) -> bool:
        return bool(self._com.Visible)
```

```python
# src/sapguimcp/sapgui/components/field.py
"""Text field and label classes."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVComponent


class GuiTextField(GuiVComponent):
    """Standard text input field (type 31, prefix: txt)."""

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

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)


class GuiCTextField(GuiTextField):
    """Text field with F4 search help button (type 32, prefix: ctxt).

    Use this for fields that have a dropdown/search icon to the right.
    The F4 button is part of the field, not a separate GuiButton.
    Setting .text triggers server communication only after pressing Enter or Tab.
    """


class GuiPasswordField(GuiTextField):
    """Password input field (type 33, prefix: pwd).

    Text is masked. Reading .text returns empty string for security.
    """


class GuiLabel(GuiVComponent):
    """Static text label (type 30, prefix: lbl).

    Labels are often clickable hotspots in SAP lists. Check is_hotspot.
    """

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
    def is_numerical(self) -> bool:
        return bool(self._com.Numerical)

    @property
    def is_hotspot(self) -> bool:
        return bool(self._com.IsHotspot)

    @property
    def is_left_label(self) -> bool:
        return bool(self._com.IsLeftLabel)

    @property
    def is_right_label(self) -> bool:
        return bool(self._com.IsRightLabel)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def displayed_text(self) -> str:
        return self._com.DisplayedText

    @property
    def color_index(self) -> int:
        return self._com.ColorIndex

    @property
    def color_intensified(self) -> bool:
        return bool(self._com.ColorIntensified)

    @property
    def color_inverse(self) -> bool:
        return bool(self._com.ColorInverse)

    @property
    def char_height(self) -> int:
        return self._com.CharHeight

    @property
    def char_width(self) -> int:
        return self._com.CharWidth

    @property
    def char_left(self) -> int:
        return self._com.CharLeft

    @property
    def char_top(self) -> int:
        return self._com.CharTop

    @property
    def row_text(self) -> str:
        return self._com.RowText


class GuiBox(GuiVComponent):
    """Group box frame (type 62, prefix: box).

    A visual frame around a group of fields. NOT a container per spec —
    children are siblings in the parent container, not inside the box.
    """
```

```python
# src/sapguimcp/sapgui/components/button.py
"""Button class."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVComponent


class GuiButton(GuiVComponent):
    """Pushbutton (type 40, prefix: btn).

    Pressing a button triggers a server round trip. All element
    references below the window level may become invalid after press().
    """

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)

    def press(self) -> None:
        """Press the button, triggering a server round trip."""
        self._com.Press()
```

```python
# src/sapguimcp/sapgui/components/checkbox.py
"""Checkbox and radio button classes."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVComponent


class GuiCheckBox(GuiVComponent):
    """Checkbox (type 42, prefix: chk)."""

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)

    @property
    def color_index(self) -> int:
        return self._com.ColorIndex

    @property
    def color_intensified(self) -> bool:
        return bool(self._com.ColorIntensified)

    @property
    def color_inverse(self) -> bool:
        return bool(self._com.ColorInverse)


class GuiRadioButton(GuiVComponent):
    """Radio button (type 41, prefix: rad).

    Radio buttons in the same group are mutually exclusive. Setting
    .selected = True on one automatically deselects the others.
    """

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)

    @property
    def group_count(self) -> int:
        return self._com.GroupCount

    @property
    def group_pos(self) -> int:
        return self._com.GroupPos
```

```python
# src/sapguimcp/sapgui/components/combobox.py
"""ComboBox and ComboBoxEntry classes."""
from __future__ import annotations
from typing import Any, Iterator
from sapguimcp.sapgui.components.base import GuiVComponent


class GuiComboBoxEntry:
    """Single entry in a combo box dropdown list.

    Read-only. Access via GuiComboBox.entries.
    """

    def __init__(self, com_entry: Any) -> None:
        self._com = com_entry

    @property
    def key(self) -> str:
        return self._com.Key

    @property
    def value(self) -> str:
        return self._com.Value

    @property
    def pos(self) -> int:
        return self._com.Pos

    def __repr__(self) -> str:
        return f"<GuiComboBoxEntry key='{self.key}' value='{self.value}'>"


class GuiComboBox(GuiVComponent):
    """Dropdown combo box (type 34, prefix: cmb).

    Use .value to get/set the selected key. Use .entries to iterate
    available options.
    """

    @property
    def value(self) -> str:
        return self._com.Value

    @value.setter
    def value(self, key: str) -> None:
        self._com.Value = key

    @property
    def entries(self) -> list[GuiComboBoxEntry]:
        com_entries = self._com.Entries
        return [GuiComboBoxEntry(com_entries.Item(i)) for i in range(com_entries.Count)]

    @property
    def item_count(self) -> int:
        return self._com.Entries.Count

    @property
    def is_required(self) -> bool:
        return bool(self._com.Required)

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)
```

```python
# src/sapguimcp/sapgui/components/okcode.py
"""OkCode field class."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVComponent


class GuiOkCodeField(GuiVComponent):
    """The transaction code / command field in the system toolbar (type 35, prefix: okcd).

    Set .text to a transaction code (e.g., "/nSE16") then call
    session.find_by_id("wnd[0]").send_v_key(0) to execute it.
    Setting text alone does NOT trigger navigation — you must send Enter (VKey 0).
    """

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)
```

```python
# src/sapguimcp/sapgui/components/statusbar.py
"""Statusbar and StatusPane classes."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVComponent


class GuiStatusbar(GuiVComponent):
    """Status bar at the bottom of the SAP GUI window (type 103, prefix: sbar).

    Shows the current message (success/warning/error/info). Check .message_type
    to determine the kind. Extends GuiVComponent, NOT GuiVContainer — the status
    bar is not a container in the scripting API despite visually containing panes.
    """

    @property
    def message_type(self) -> str:
        return self._com.MessageType

    @property
    def message_id(self) -> str:
        return self._com.MessageId if hasattr(self._com, "MessageId") else ""

    @property
    def message_number(self) -> str:
        return self._com.MessageNumber if hasattr(self._com, "MessageNumber") else ""


class GuiStatusPane(GuiVComponent):
    """Individual pane in the status bar (type 43, prefix: pane)."""
```

```python
# src/sapguimcp/sapgui/components/toolbar.py
"""Toolbar, Menubar, Menu, and Titlebar classes."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVContainer, GuiVComponent


class GuiToolbar(GuiVContainer):
    """System or application toolbar (type 101, prefix: tbar).

    tbar[0] is the system toolbar (with OK code field).
    tbar[1] is the application toolbar (function keys).
    """


class GuiMenubar(GuiVContainer):
    """Menu bar at the top of the window (type 111, prefix: mbar)."""


class GuiMenu(GuiVContainer):
    """A menu or submenu item (type 110, prefix: menu).

    Menus can contain child menus (submenus).
    """

    def select(self) -> None:
        """Select/click this menu item."""
        self._com.Select()


class GuiTitlebar(GuiVContainer):
    """Window title bar (type 102, prefix: titl)."""
```

```python
# src/sapguimcp/sapgui/components/container.py
"""Container classes for subscreens, shells, and custom controls."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVContainer


class GuiUserArea(GuiVContainer):
    """Main content area of a window (type 74, prefix: usr).

    The usr area contains all dynpro fields, labels, buttons, tables.
    Access it via session.find_by_id("wnd[0]/usr").
    """

    @property
    def vertical_scrollbar(self) -> object:
        return self._com.VerticalScrollbar

    @property
    def horizontal_scrollbar(self) -> object:
        return self._com.HorizontalScrollbar


class GuiScrollContainer(GuiVContainer):
    """Scrollable subscreen container (type 72, prefix: ssub)."""


class GuiSimpleContainer(GuiVContainer):
    """Non-scrollable subscreen container (type 71, prefix: sub)."""


class GuiCustomControl(GuiVContainer):
    """Custom control container (type 50, prefix: cntl).

    Hosts ActiveX/shell controls. The actual control is a child shell.
    """


class GuiContainerShell(GuiVContainer):
    """Shell container that holds shell controls (type 51, prefix: shellcont)."""


class GuiDialogShell(GuiVContainer):
    """Dialog-hosted shell container (type 125, prefix: shellcont)."""


class GuiDockShell(GuiVContainer):
    """Dockable shell container (type 126, prefix: shellcont)."""


class GuiGOSShell(GuiVContainer):
    """Generic Object Services shell (type 123, prefix: shellcont)."""


class GuiSplitterContainer(GuiVContainer):
    """Splitter container dividing area into panes (type 75)."""
```

```python
# src/sapguimcp/sapgui/components/tab.py
"""Tab strip and tab page classes."""
from __future__ import annotations
from sapguimcp.sapgui.components.base import GuiVContainer


class GuiTabStrip(GuiVContainer):
    """Tab strip container (type 90, prefix: tabs).

    Contains GuiTab children. Use tab.select() to switch tabs.
    """


class GuiTab(GuiVContainer):
    """Single tab page (type 91, prefix: tabp).

    Children are the controls on this tab page. Call .select() to
    make this the active tab.
    """

    def select(self) -> None:
        """Switch to this tab."""
        self._com.Select()
```

```python
# src/sapguimcp/sapgui/components/table.py
"""Table control classes (dynpro tables, NOT ALV grid)."""
from __future__ import annotations
from typing import Any
from sapguimcp.sapgui.components.base import GuiVContainer, GuiVComponent, GuiComponent


class GuiTableControl(GuiVContainer):
    """Classic dynpro table control (type 80, prefix: tbl).

    NOT the same as GuiGridView (ALV). This is the older table type.
    Rows are direct children, columns describe the structure.
    """

    @property
    def row_count(self) -> int:
        return self._com.RowCount

    @property
    def visible_row_count(self) -> int:
        return self._com.VisibleRowCount

    @property
    def current_row(self) -> int:
        return self._com.CurrentRow

    @current_row.setter
    def current_row(self, value: int) -> None:
        self._com.CurrentRow = value

    @property
    def current_col(self) -> int:
        return self._com.CurrentCol

    @current_col.setter
    def current_col(self, value: int) -> None:
        self._com.CurrentCol = value

    @property
    def columns(self) -> Any:
        return self._com.Columns

    @property
    def rows(self) -> Any:
        return self._com.Rows

    def get_cell(self, row: int, col: int) -> Any:
        return self._com.GetCell(row, col)

    @property
    def table_field_name(self) -> str:
        return self._com.TableFieldName if hasattr(self._com, "TableFieldName") else ""


class GuiTableRow(GuiComponent):
    """A single row in a GuiTableControl."""

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def selectable(self) -> bool:
        return bool(self._com.Selectable)


class GuiTableColumn(GuiComponent):
    """Column metadata for a GuiTableControl."""

    @property
    def title(self) -> str:
        return self._com.Title

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0
```

```python
# src/sapguimcp/sapgui/components/grid.py
"""GuiGridView (ALV grid) class."""
from __future__ import annotations
from typing import Any
from sapguimcp.sapgui.components.shell import GuiShell


class GuiGridView(GuiShell):
    """ALV grid control — the standard SAP table for displaying/editing data.

    This is NOT the same as GuiTableControl (dynpro table). GuiGridView is the
    modern ALV grid used in most list reports. Use this for reading table data,
    selecting rows, clicking cells, and accessing column metadata.

    Common in: SE16N results, SM37 job lists, SE09 transport lists, ALV reports.
    """

    @property
    def row_count(self) -> int:
        return self._com.RowCount

    @property
    def column_count(self) -> int:
        return self._com.ColumnCount

    @property
    def current_cell_row(self) -> int:
        return self._com.CurrentCellRow

    @current_cell_row.setter
    def current_cell_row(self, value: int) -> None:
        self._com.CurrentCellRow = value

    @property
    def current_cell_column(self) -> str:
        return self._com.CurrentCellColumn

    @current_cell_column.setter
    def current_cell_column(self, value: str) -> None:
        self._com.CurrentCellColumn = value

    @property
    def selected_rows(self) -> str:
        return self._com.SelectedRows

    @selected_rows.setter
    def selected_rows(self, value: str) -> None:
        self._com.SelectedRows = value

    @property
    def first_visible_row(self) -> int:
        return self._com.FirstVisibleRow

    @first_visible_row.setter
    def first_visible_row(self, value: int) -> None:
        self._com.FirstVisibleRow = value

    @property
    def column_order(self) -> Any:
        return self._com.ColumnOrder

    @property
    def toolbar_button_count(self) -> int:
        return self._com.ToolbarButtonCount

    def get_cell_value(self, row: int, column: str) -> str:
        return self._com.GetCellValue(row, column)

    def set_cell_value(self, row: int, column: str, value: str) -> None:
        self._com.ModifyCell(row, column, value)

    def get_column_titles(self) -> list[str]:
        """Return all column titles in order."""
        col_order = self._com.ColumnOrder
        return [self._com.GetColumnTitle(col_order(i)) for i in range(col_order.Count)]

    def get_column_tooltip(self, column: str) -> str:
        return self._com.GetColumnTooltip(column)

    def click(self, row: int, column: str) -> None:
        self._com.Click(row, column)

    def double_click(self, row: int, column: str) -> None:
        self._com.DoubleClick(row, column)

    def click_current_cell(self) -> None:
        self._com.ClickCurrentCell()

    def double_click_current_cell(self) -> None:
        self._com.DoubleClickCurrentCell()

    def select_all(self) -> None:
        self._com.SelectAll()

    def clear_selection(self) -> None:
        self._com.ClearSelection()

    def select_column(self, column: str) -> None:
        self._com.SelectColumn(column)

    def deselect_column(self, column: str) -> None:
        self._com.DeselectColumn(column)

    def current_cell_moved(self) -> None:
        self._com.CurrentCellMoved()

    def press_button(self, button_id: str) -> None:
        self._com.PressButton(button_id)

    def press_toolbar_button(self, button_id: str) -> None:
        self._com.PressToolbarButton(button_id)

    def press_enter(self) -> None:
        self._com.PressEnter()

    def press_toolbar_context_button(self, button_id: str) -> None:
        self._com.PressToolbarContextButton(button_id)

    def context_menu(self) -> None:
        self._com.ContextMenu()

    def delete_rows(self, rows: str) -> None:
        self._com.DeleteRows(rows)

    def duplicate_rows(self, rows: str) -> None:
        self._com.DuplicateRows(rows)

    def insert_rows(self, rows: str) -> None:
        self._com.InsertRows(rows)

    def get_toolbar_button_id(self, pos: int) -> str:
        return self._com.GetToolbarButtonId(pos)

    def get_toolbar_button_text(self, pos: int) -> str:
        return self._com.GetToolbarButtonText(pos)

    def get_toolbar_button_type(self, pos: int) -> str:
        return self._com.GetToolbarButtonType(pos)

    def get_toolbar_button_enabled(self, pos: int) -> bool:
        return bool(self._com.GetToolbarButtonEnabled(pos))

    def get_toolbar_button_tooltip(self, pos: int) -> str:
        return self._com.GetToolbarButtonTooltip(pos)

    def get_cell_changeable(self, row: int, column: str) -> bool:
        return bool(self._com.GetCellChangeable(row, column))

    def get_cell_type(self, row: int, column: str) -> str:
        return self._com.GetCellType(row, column)

    def get_display_grid_column_value(self, row: int, column: str) -> str:
        """Like GetCellValue but returns the displayed (formatted) string."""
        return self._com.GetDisplayedColumnValue(row, column)
```

```python
# src/sapguimcp/sapgui/components/tree.py
"""GuiTree class."""
from __future__ import annotations
from typing import Any
from sapguimcp.sapgui.components.shell import GuiShell


class GuiTree(GuiShell):
    """Hierarchical tree control (SubType: Tree).

    Trees come in three flavors determined by .tree_type:
    - Simple tree: just nodes
    - List tree: nodes with columns
    - Column tree: full column headers + data
    """

    @property
    def tree_type(self) -> str:
        return self._com.GetTreeType()

    def get_node_text_by_key(self, key: str) -> str:
        return self._com.GetNodeTextByKey(key)

    def get_node_text_by_path(self, path: str) -> str:
        return self._com.GetNodeTextByPath(path)

    def get_item_text(self, key: str, column: str) -> str:
        return self._com.GetItemText(key, column)

    def get_node_children_count(self, key: str) -> int:
        return self._com.GetNodeChildrenCount(key)

    def get_all_node_keys(self) -> Any:
        return self._com.GetAllNodeKeys()

    def get_column_names(self) -> Any:
        return self._com.GetColumnNames()

    def get_column_headers(self) -> Any:
        return self._com.GetColumnHeaders()

    def select_node(self, key: str) -> None:
        self._com.SelectNode(key)

    def expand_node(self, key: str) -> None:
        self._com.ExpandNode(key)

    def collapse_node(self, key: str) -> None:
        self._com.CollapseNode(key)

    def double_click_node(self, key: str) -> None:
        self._com.DoubleClickNode(key)

    def click_node(self, key: str) -> None:
        self._com.ClickNode(key)

    def press_button(self, key: str, column: str) -> None:
        self._com.PressButton(key, column)

    def click_link(self, key: str, column: str) -> None:
        self._com.ClickLink(key, column)

    def get_node_key_by_path(self, path: str) -> str:
        return self._com.GetNodeKeyByPath(path)

    @property
    def selected_node(self) -> str:
        return self._com.SelectedNode

    @selected_node.setter
    def selected_node(self, key: str) -> None:
        self._com.SelectedNode = key

    @property
    def top_node(self) -> str:
        return self._com.TopNode

    @top_node.setter
    def top_node(self, key: str) -> None:
        self._com.TopNode = key
```

```python
# src/sapguimcp/sapgui/components/editor.py
"""Text editor classes."""
from __future__ import annotations
from sapguimcp.sapgui.components.shell import GuiShell


class GuiTextedit(GuiShell):
    """Multi-line text editor control (SubType: TextEdit).

    Used for long text fields, notes, descriptions. Not the same as
    GuiAbapEditor which is specifically for ABAP source code.
    """

    @property
    def number_of_lines(self) -> int:
        return self._com.NumberOfLines

    @property
    def current_line(self) -> int:
        return self._com.CurrentLine

    @property
    def current_column(self) -> int:
        return self._com.CurrentColumn

    @property
    def selection_text(self) -> str:
        return self._com.SelectionText

    @property
    def is_read_only(self) -> bool:
        return bool(self._com.IsReadOnly) if hasattr(self._com, "IsReadOnly") else not self.changeable

    def get_line_text(self, line: int) -> str:
        return self._com.GetLineText(line)

    def set_selection_indexes(self, start: int, end: int) -> None:
        self._com.SetSelectionIndexes(start, end)

    def press_f1(self) -> None:
        self._com.PressF1()

    def press_f4(self) -> None:
        self._com.PressF4()


class GuiAbapEditor(GuiShell):
    """ABAP source code editor (SubType: AbapEditor).

    The editor used in SE38, SE24 method editor, etc. Can get/set
    the entire source code as a string.
    """

    @property
    def number_of_lines(self) -> int:
        return self._com.NumberOfLines

    @property
    def current_line(self) -> int:
        return self._com.CurrentLine

    @property
    def current_column(self) -> int:
        return self._com.CurrentColumn

    @property
    def selection_text(self) -> str:
        return self._com.SelectionText

    def get_line_text(self, line: int) -> str:
        return self._com.GetLineText(line)

    def set_selection_indexes(self, start: int, end: int) -> None:
        self._com.SetSelectionIndexes(start, end)

    def press_f1(self) -> None:
        self._com.PressF1()
```

- [ ] **Step 4: Implement the factory**

```python
# src/sapguimcp/sapgui/_factory.py
"""Two-level type dispatch factory for wrapping COM objects.

Level 1: TypeAsNumber → Python class (covers most types)
Level 2: For GuiShell (type 122), SubType string → specific shell class

Unknown types fall back to GuiComponent. Unknown shell subtypes fall
back to GuiShell.
"""
from __future__ import annotations

from typing import Any

from sapguimcp.sapgui.components.application import GuiApplication
from sapguimcp.sapgui.components.base import GuiComponent, GuiVComponent
from sapguimcp.sapgui.components.button import GuiButton
from sapguimcp.sapgui.components.checkbox import GuiCheckBox, GuiRadioButton
from sapguimcp.sapgui.components.combobox import GuiComboBox
from sapguimcp.sapgui.components.connection import GuiConnection
from sapguimcp.sapgui.components.container import (
    GuiContainerShell,
    GuiCustomControl,
    GuiDialogShell,
    GuiDockShell,
    GuiGOSShell,
    GuiScrollContainer,
    GuiSimpleContainer,
    GuiSplitterContainer,
    GuiUserArea,
)
from sapguimcp.sapgui.components.editor import GuiAbapEditor, GuiTextedit
from sapguimcp.sapgui.components.field import GuiBox, GuiCTextField, GuiLabel, GuiPasswordField, GuiTextField
from sapguimcp.sapgui.components.grid import GuiGridView
from sapguimcp.sapgui.components.okcode import GuiOkCodeField
from sapguimcp.sapgui.components.session import GuiSession
from sapguimcp.sapgui.components.shell import (
    GuiCalendar,
    GuiColorSelector,
    GuiComboBoxControl,
    GuiHTMLViewer,
    GuiInputFieldControl,
    GuiPicture,
    GuiShell,
    GuiSplit,
    GuiToolbarControl,
)
from sapguimcp.sapgui.components.statusbar import GuiStatusbar, GuiStatusPane
from sapguimcp.sapgui.components.tab import GuiTab, GuiTabStrip
from sapguimcp.sapgui.components.table import GuiTableControl
from sapguimcp.sapgui.components.toolbar import GuiMenu, GuiMenubar, GuiTitlebar, GuiToolbar
from sapguimcp.sapgui.components.tree import GuiTree
from sapguimcp.sapgui.components.window import GuiFrameWindow, GuiMainWindow, GuiMessageWindow, GuiModalWindow

# Level 1: TypeAsNumber → class
_TYPE_MAP: dict[int, type[GuiComponent]] = {
    10: GuiApplication,
    11: GuiConnection,
    12: GuiSession,
    20: GuiFrameWindow,
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
    122: GuiShell,
    123: GuiGOSShell,
    125: GuiDialogShell,
    126: GuiDockShell,
    129: GuiVComponent,  # GuiVHViewSwitch — extends GuiVComponent per spec
}

# Level 2: GuiShell SubType → specific shell class
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
}


def wrap_com_object(com_obj: Any) -> GuiComponent:
    """Wrap a COM dispatch object in the correct typed Python class.

    Two-level dispatch:
    1. Look up TypeAsNumber in _TYPE_MAP
    2. For GuiShell (type 122), look up SubType in _SHELL_SUBTYPE_MAP
    3. Unknown types fall back to GuiComponent
    4. Unknown shell subtypes fall back to GuiShell
    """
    type_num = com_obj.TypeAsNumber
    cls = _TYPE_MAP.get(type_num)

    if cls is GuiShell:
        sub_type = getattr(com_obj, "SubType", "")
        cls = _SHELL_SUBTYPE_MAP.get(sub_type, GuiShell)
    elif cls is None:
        cls = GuiComponent

    return cls(com_obj)
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_factory.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/sapgui/components/ src/sapguimcp/sapgui/_factory.py unittests/sapgui/test_factory.py
git commit -m "feat(sapgui): add two-level type dispatch factory and all component stubs"
```

---

### Task 7: COM Helpers and Entry Points

**Files:**

- Create: `src/sapguimcp/sapgui/_com.py`
- Modify: `src/sapguimcp/sapgui/__init__.py`
- Test: `unittests/sapgui/test_com.py`
- Test: `unittests/sapgui/test_init.py`

- [ ] **Step 1: Write COM helper tests (mocked)**

```python
# unittests/sapgui/test_com.py
"""Tests for COM connection helpers (mocked — no real SAP GUI needed)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.sapgui._errors import SapConnectionError, ScriptingDisabledError


def test_connect_raises_when_sap_not_running():
    with patch("sapguimcp.sapgui._com.win32com.client") as mock_client:
        mock_client.GetObject.side_effect = Exception("not running")
        from sapguimcp.sapgui._com import _connect_to_running_sap_gui

        with pytest.raises(SapConnectionError, match="not running"):
            _connect_to_running_sap_gui()


def test_connect_raises_when_scripting_disabled():
    with patch("sapguimcp.sapgui._com.win32com.client") as mock_client, patch(
        "sapguimcp.sapgui._com.pythoncom"
    ):
        rot_entry = MagicMock()
        rot_entry.GetScriptingEngine = None
        mock_client.GetObject.return_value = rot_entry
        from sapguimcp.sapgui._com import _connect_to_running_sap_gui

        with pytest.raises(ScriptingDisabledError):
            _connect_to_running_sap_gui()


def test_connect_returns_gui_application():
    with patch("sapguimcp.sapgui._com.win32com.client") as mock_client, patch(
        "sapguimcp.sapgui._com.pythoncom"
    ):
        engine = MagicMock()
        engine.TypeAsNumber = 10
        engine.Type = "GuiApplication"
        engine.Id = "/app"
        engine.Name = "app"
        engine.ContainerType = 1
        rot_entry = MagicMock()
        rot_entry.GetScriptingEngine = engine
        mock_client.GetObject.return_value = rot_entry
        from sapguimcp.sapgui._com import _connect_to_running_sap_gui

        result = _connect_to_running_sap_gui()
        assert result._com is engine
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest unittests/sapgui/test_com.py -v`

- [ ] **Step 3: Implement COM helpers**

```python
# src/sapguimcp/sapgui/_com.py
"""Low-level COM helpers for connecting to SAP GUI.

Handles CoInitialize, Running Object Table (ROT) access, and polling.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from sapguimcp.sapgui._errors import SapConnectionError, SapGuiTimeoutError, ScriptingDisabledError

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from sapguimcp.sapgui.components.application import GuiApplication


def _connect_to_running_sap_gui() -> GuiApplication:
    """Get SAPGUI from the Running Object Table and return the scripting engine."""
    if pythoncom is not None:
        pythoncom.CoInitialize()
    try:
        rot_entry = win32com.client.GetObject("SAPGUI")
    except Exception as e:
        raise SapConnectionError("SAP GUI is not running or scripting is disabled") from e

    engine = rot_entry.GetScriptingEngine
    if engine is None:
        raise ScriptingDisabledError(
            "Scripting engine not available — check server parameter sapgui/user_scripting"
        )

    from sapguimcp.sapgui.components.application import GuiApplication

    return GuiApplication(engine)


def _wait_for_sap_gui(timeout: int = 30) -> GuiApplication:
    """Poll until SAPGUI ROT entry is available, then connect."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return _connect_to_running_sap_gui()
        except SapConnectionError as e:
            last_err = e
            time.sleep(1)
    raise SapGuiTimeoutError(f"SAP GUI not available after {timeout}s") from last_err
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_com.py -v`
Expected: All tests PASS

- [ ] **Step 5: Write entry point tests**

```python
# unittests/sapgui/test_init.py
"""Tests for SapGui entry point class."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from sapguimcp.sapgui import SapGui


def test_sap_gui_connect_delegates():
    with patch("sapguimcp.sapgui._com._connect_to_running_sap_gui") as mock:
        mock.return_value = MagicMock()
        result = SapGui.connect()
        mock.assert_called_once()
        assert result is mock.return_value


def test_sap_gui_launch_delegates():
    with patch("sapguimcp.sapgui._com._wait_for_sap_gui") as mock_wait, patch(
        "subprocess.Popen"
    ):
        mock_wait.return_value = MagicMock()
        result = SapGui.launch(exe_path="C:\\SAP\\saplogon.exe", timeout=10)
        assert result is mock_wait.return_value
```

- [ ] **Step 6: Implement **init**.py entry points**

```python
# src/sapguimcp/sapgui/__init__.py
"""pysapgui — Pythonic SAP GUI Scripting Library.

Entry points:
    SapGui.connect()  — attach to a running SAP GUI instance
    SapGui.launch()   — start SAP GUI and connect
"""
from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sapguimcp.sapgui.components.application import GuiApplication


class SapGui:
    """Entry point for SAP GUI Scripting."""

    @staticmethod
    def connect() -> GuiApplication:
        """Attach to a running SAP GUI instance via the Running Object Table."""
        from sapguimcp.sapgui._com import _connect_to_running_sap_gui

        return _connect_to_running_sap_gui()

    @staticmethod
    def launch(
        exe_path: str,
        connection_string: str | None = None,
        timeout: int = 30,
    ) -> GuiApplication:
        """Launch SAP GUI executable, wait for it to be available, then connect.

        Args:
            exe_path: Path to saplogon.exe or saplgpad.exe.
            connection_string: Optional SAP connection string.
            timeout: Max seconds to wait for SAP GUI to become available.

        Raises:
            SapGuiTimeoutError: If SAP GUI doesn't become available within timeout.
        """
        from sapguimcp.sapgui._com import _wait_for_sap_gui

        cmd = [exe_path]
        if connection_string:
            cmd.extend(["-command", connection_string])
        subprocess.Popen(cmd)
        return _wait_for_sap_gui(timeout=timeout)
```

- [ ] **Step 7: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_init.py -v`

- [ ] **Step 8: Commit**

```bash
git add src/sapguimcp/sapgui/_com.py src/sapguimcp/sapgui/__init__.py unittests/sapgui/test_com.py unittests/sapgui/test_init.py
git commit -m "feat(sapgui): add COM helpers and SapGui.connect()/launch() entry points"
```

---

## Chunk 3: Session, Connection, Application

### Task 8: GuiApplication

**Files:**

- Create: `src/sapguimcp/sapgui/components/application.py`
- Test: `unittests/sapgui/test_application.py`

- [ ] **Step 1: Write tests**

```python
# unittests/sapgui/test_application.py
"""Tests for GuiApplication wrapper."""
from __future__ import annotations
from unittest.mock import MagicMock
from conftest import make_mock_com
from sapguimcp.sapgui.components.application import GuiApplication
from sapguimcp.sapgui.components.base import GuiContainer


def test_extends_gui_container():
    assert issubclass(GuiApplication, GuiContainer)


def test_connections_property():
    child = make_mock_com(type_as_number=11)
    com = make_mock_com(type_as_number=10, container_type=True, children=[child])
    app = GuiApplication(com)
    assert app.connections.Count == 1


def test_active_session():
    com = make_mock_com(type_as_number=10, container_type=True, children=[])
    com.ActiveSession = MagicMock()
    app = GuiApplication(com)
    assert app.active_session is com.ActiveSession


def test_open_connection():
    com = make_mock_com(type_as_number=10, container_type=True, children=[])
    conn_com = make_mock_com(type_as_number=11)
    com.OpenConnection.return_value = conn_com
    app = GuiApplication(com)
    result = app.open_connection("My SAP System")
    com.OpenConnection.assert_called_once_with("My SAP System", True, False)


def test_open_connection_by_string():
    com = make_mock_com(type_as_number=10, container_type=True, children=[])
    conn_com = make_mock_com(type_as_number=11)
    com.OpenConnectionByConnectionString.return_value = conn_com
    app = GuiApplication(com)
    result = app.open_connection_by_connection_string("/H/sapserver/S/3200")
    com.OpenConnectionByConnectionString.assert_called_once_with("/H/sapserver/S/3200", True, False)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest unittests/sapgui/test_application.py -v`

- [ ] **Step 3: Implement GuiApplication**

```python
# src/sapguimcp/sapgui/components/application.py
"""GuiApplication — top-level SAP GUI process wrapper."""
from __future__ import annotations
from typing import Any
from sapguimcp.sapgui.components.base import GuiContainer


class GuiApplication(GuiContainer):
    """Represents the SAP GUI process (type 10).

    The root of the scripting object hierarchy. Obtained via SapGui.connect()
    or SapGui.launch(). Children are GuiConnection objects.
    """

    @property
    def connections(self) -> Any:
        """All open connections (alias for children)."""
        return self._com.Children

    @property
    def active_session(self) -> Any:
        """The currently active session across all connections."""
        return self._com.ActiveSession

    @property
    def connection_error_text(self) -> str:
        return self._com.ConnectionErrorText

    @property
    def history_enabled(self) -> bool:
        return bool(self._com.HistoryEnabled)

    @history_enabled.setter
    def history_enabled(self, value: bool) -> None:
        self._com.HistoryEnabled = 1 if value else 0

    @property
    def buttonbar_visible(self) -> bool:
        return bool(self._com.ButtonbarVisible)

    @buttonbar_visible.setter
    def buttonbar_visible(self, value: bool) -> None:
        self._com.ButtonbarVisible = 1 if value else 0

    @property
    def allow_system_messages(self) -> bool:
        return bool(self._com.AllowSystemMessages)

    @allow_system_messages.setter
    def allow_system_messages(self, value: bool) -> None:
        self._com.AllowSystemMessages = 1 if value else 0

    def open_connection(self, description: str, sync: bool = True, raise_error: bool = False) -> Any:
        """Open connection from SAP Logon by description name."""
        return self._com.OpenConnection(description, sync, raise_error)

    def open_connection_by_connection_string(
        self, connect_string: str, sync: bool = True, raise_error: bool = False
    ) -> Any:
        """Open connection by technical connection string (e.g., /H/host/S/port)."""
        return self._com.OpenConnectionByConnectionString(connect_string, sync, raise_error)

    def create_gui_collection(self) -> Any:
        return self._com.CreateGuiCollection()
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_application.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/sapgui/components/application.py unittests/sapgui/test_application.py
git commit -m "feat(sapgui): add GuiApplication wrapper"
```

---

### Task 9: GuiConnection

**Files:**

- Create: `src/sapguimcp/sapgui/components/connection.py`
- Test: `unittests/sapgui/test_connection.py`

- [ ] **Step 1: Write tests**

```python
# unittests/sapgui/test_connection.py
"""Tests for GuiConnection wrapper."""
from __future__ import annotations
from conftest import make_mock_com
from sapguimcp.sapgui.components.connection import GuiConnection
from sapguimcp.sapgui.components.base import GuiContainer


def test_extends_gui_container():
    assert issubclass(GuiConnection, GuiContainer)


def test_sessions_property():
    child = make_mock_com(type_as_number=12)
    com = make_mock_com(type_as_number=11, container_type=True, children=[child])
    conn = GuiConnection(com)
    assert conn.sessions.Count == 1


def test_connection_string():
    com = make_mock_com(type_as_number=11, container_type=True, children=[], ConnectionString="/H/sap/S/3200")
    conn = GuiConnection(com)
    assert conn.connection_string == "/H/sap/S/3200"


def test_description():
    com = make_mock_com(type_as_number=11, container_type=True, children=[], Description="My System")
    conn = GuiConnection(com)
    assert conn.description == "My System"


def test_close_connection():
    com = make_mock_com(type_as_number=11, container_type=True, children=[])
    conn = GuiConnection(com)
    conn.close_connection()
    com.CloseConnection.assert_called_once()


def test_close_session():
    com = make_mock_com(type_as_number=11, container_type=True, children=[])
    conn = GuiConnection(com)
    conn.close_session("/app/con[0]/ses[0]")
    com.CloseSession.assert_called_once_with("/app/con[0]/ses[0]")
```

- [ ] **Step 2: Implement GuiConnection**

```python
# src/sapguimcp/sapgui/components/connection.py
"""GuiConnection — SAP connection wrapper."""
from __future__ import annotations
from typing import Any
from sapguimcp.sapgui.components.base import GuiContainer


class GuiConnection(GuiContainer):
    """Represents a connection between SAP GUI and an application server (type 11).

    Children are GuiSession objects. One connection can have multiple sessions
    (opened via /o command or session.create_session()).
    """

    @property
    def sessions(self) -> Any:
        """All sessions in this connection (alias for children)."""
        return self._com.Children

    @property
    def connection_string(self) -> str:
        return self._com.ConnectionString

    @property
    def description(self) -> str:
        return self._com.Description

    @property
    def disabled_by_server(self) -> bool:
        return bool(self._com.DisabledByServer)

    def close_connection(self) -> None:
        """Close this connection and all its sessions."""
        self._com.CloseConnection()

    def close_session(self, session_id: str) -> None:
        """Close a specific session by ID."""
        self._com.CloseSession(session_id)
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_connection.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/sapgui/components/connection.py unittests/sapgui/test_connection.py
git commit -m "feat(sapgui): add GuiConnection wrapper"
```

---

### Task 10: GuiSession and GuiSessionInfo

**Files:**

- Create: `src/sapguimcp/sapgui/components/session.py`
- Test: `unittests/sapgui/test_session.py`

- [ ] **Step 1: Write tests**

```python
# unittests/sapgui/test_session.py
"""Tests for GuiSession and GuiSessionInfo wrappers."""
from __future__ import annotations
from unittest.mock import MagicMock
from conftest import make_mock_com
from sapguimcp.sapgui.components.session import GuiSession, GuiSessionInfo
from sapguimcp.sapgui.components.base import GuiContainer


def test_extends_gui_container():
    assert issubclass(GuiSession, GuiContainer)


def test_info_property():
    info_com = MagicMock()
    info_com.SystemName = "S4H"
    info_com.Client = "100"
    info_com.User = "TESTUSER"
    info_com.Language = "EN"
    info_com.Transaction = "SE16"
    info_com.Program = "SAPLSETB"
    info_com.ScreenNumber = 230
    info_com.ApplicationServer = "sapserver01"
    info_com.ResponseTime = 42
    info_com.RoundTrips = 3
    com = make_mock_com(type_as_number=12, container_type=True, children=[], Info=info_com)
    session = GuiSession(com)
    info = session.info
    assert isinstance(info, GuiSessionInfo)
    assert info.system_name == "S4H"
    assert info.client == "100"
    assert info.user == "TESTUSER"
    assert info.language == "EN"
    assert info.transaction == "SE16"
    assert info.screen_number == 230


def test_busy_property():
    com = make_mock_com(type_as_number=12, container_type=True, children=[], Busy=0)
    session = GuiSession(com)
    assert session.busy is False


def test_create_session():
    com = make_mock_com(type_as_number=12, container_type=True, children=[])
    session = GuiSession(com)
    session.create_session()
    com.CreateSession.assert_called_once()


def test_end_transaction():
    com = make_mock_com(type_as_number=12, container_type=True, children=[])
    session = GuiSession(com)
    session.end_transaction()
    com.EndTransaction.assert_called_once()


def test_send_command():
    com = make_mock_com(type_as_number=12, container_type=True, children=[])
    session = GuiSession(com)
    session.send_command("/nSE16")
    com.SendCommand.assert_called_once_with("/nSE16")


def test_session_info_properties():
    info_com = MagicMock()
    info_com.SystemName = "S4H"
    info_com.Client = "100"
    info_com.User = "TESTUSER"
    info_com.Language = "EN"
    info_com.Transaction = "SE16"
    info_com.Program = "SAPLSETB"
    info_com.ScreenNumber = 230
    info_com.ApplicationServer = "sapserver01"
    info_com.ResponseTime = 42
    info_com.RoundTrips = 3
    info_com.SessionNumber = 0
    info_com.SystemNumber = 0
    info_com.Codepage = 4103
    info_com.Flushes = 5
    info = GuiSessionInfo(info_com)
    assert info.response_time == 42
    assert info.round_trips == 3
    assert info.application_server == "sapserver01"
    assert info.program == "SAPLSETB"
    assert info.session_number == 0
    assert info.codepage == 4103
    assert info.flushes == 5
```

- [ ] **Step 2: Implement GuiSession and GuiSessionInfo**

```python
# src/sapguimcp/sapgui/components/session.py
"""GuiSession and GuiSessionInfo — session management wrappers."""
from __future__ import annotations
from typing import Any
from sapguimcp.sapgui.components.base import GuiContainer


class GuiSessionInfo:
    """Technical information about a session (type 121).

    Accessed via session.info. All properties are read-only.
    """

    def __init__(self, com_info: Any) -> None:
        self._com = com_info

    @property
    def system_name(self) -> str:
        return self._com.SystemName

    @property
    def client(self) -> str:
        return self._com.Client

    @property
    def user(self) -> str:
        return self._com.User

    @property
    def language(self) -> str:
        return self._com.Language

    @property
    def transaction(self) -> str:
        return self._com.Transaction

    @property
    def program(self) -> str:
        return self._com.Program

    @property
    def screen_number(self) -> int:
        return self._com.ScreenNumber

    @property
    def application_server(self) -> str:
        return self._com.ApplicationServer

    @property
    def response_time(self) -> int:
        return self._com.ResponseTime

    @property
    def round_trips(self) -> int:
        return self._com.RoundTrips

    @property
    def session_number(self) -> int:
        return self._com.SessionNumber

    @property
    def system_number(self) -> int:
        return self._com.SystemNumber

    @property
    def codepage(self) -> int:
        return self._com.Codepage

    @property
    def flushes(self) -> int:
        return self._com.Flushes

    @property
    def group(self) -> str:
        return self._com.Group

    @property
    def message_server(self) -> str:
        return self._com.MessageServer

    @property
    def system_session_id(self) -> str:
        return self._com.SystemSessionId

    @property
    def is_low_speed_connection(self) -> bool:
        return bool(self._com.IsLowSpeedConnection)

    @property
    def scripting_mode_read_only(self) -> bool:
        return bool(self._com.ScriptingModeReadOnly)

    @property
    def scripting_mode_recording_disabled(self) -> bool:
        return bool(self._com.ScriptingModeRecordingDisabled)

    def __repr__(self) -> str:
        return f"<GuiSessionInfo system='{self.system_name}' user='{self.user}' tcode='{self.transaction}'>"


class GuiSession(GuiContainer):
    """User task context and main script entry point (type 12).

    Each session represents one SAP GUI window. Access screen elements
    via find_by_id(), starting from "wnd[0]" for the main window.
    """

    @property
    def info(self) -> GuiSessionInfo:
        return GuiSessionInfo(self._com.Info)

    @property
    def busy(self) -> bool:
        return bool(self._com.Busy)

    @property
    def active_window(self) -> Any:
        return self._com.ActiveWindow

    def create_session(self) -> None:
        """Open a new session (like /o command)."""
        self._com.CreateSession()

    def end_transaction(self) -> None:
        """End current transaction (like /n command)."""
        self._com.EndTransaction()

    def send_command(self, command: str) -> None:
        """Execute a command string synchronously (e.g., '/nSE16')."""
        self._com.SendCommand(command)

    def send_command_async(self, command: str) -> None:
        """Execute a command string asynchronously."""
        self._com.SendCommandAsync(command)

    def lock_session_ui(self) -> None:
        self._com.LockSessionUI()

    def unlock_session_ui(self) -> None:
        self._com.UnlockSessionUI()

    def get_v_key_description(self, v_key: int) -> str:
        return self._com.GetVKeyDescription(v_key)

    def get_object_tree(self, element_id: str) -> str:
        """Export object tree as JSON string."""
        return self._com.GetObjectTree(element_id)
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_session.py -v`

- [ ] **Step 4: Run all tests** (factory already maps types 10/11/12 to concrete classes from Task 6)

Run: `python -m pytest unittests/sapgui/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/sapgui/components/session.py src/sapguimcp/sapgui/components/application.py src/sapguimcp/sapgui/components/connection.py src/sapguimcp/sapgui/_factory.py unittests/sapgui/test_session.py unittests/sapgui/test_application.py unittests/sapgui/test_connection.py
git commit -m "feat(sapgui): add GuiSession, GuiConnection, GuiApplication with factory wiring"
```

---

## Chunk 4: Pydantic Models, dump_tree, Public API, and Integration Tests

### Task 11: Pydantic Models

**Files:**

- Create: `src/sapguimcp/sapgui/models.py`
- Test: `unittests/sapgui/test_models.py`

- [ ] **Step 1: Write tests**

```python
# unittests/sapgui/test_models.py
"""Tests for pysapgui Pydantic models."""
from __future__ import annotations
from sapguimcp.sapgui.models import SessionInfo, ElementInfo


def test_session_info_from_dict():
    info = SessionInfo(
        system_name="S4H",
        client="100",
        user="TESTUSER",
        language="EN",
        transaction="SE16",
        program="SAPLSETB",
        screen_number=230,
        application_server="sapserver01",
        response_time=42,
        round_trips=3,
    )
    assert info.system_name == "S4H"
    assert info.screen_number == 230


def test_session_info_serialization():
    info = SessionInfo(
        system_name="S4H", client="100", user="TESTUSER",
        language="EN", transaction="SE16", program="SAPLSETB",
        screen_number=230, application_server="sapserver01",
        response_time=42, round_trips=3,
    )
    d = info.model_dump()
    assert d["system_name"] == "S4H"
    assert d["round_trips"] == 3


def test_element_info_nested():
    child = ElementInfo(
        id="wnd[0]/usr/txtFOO",
        type="GuiTextField",
        type_as_number=31,
        name="FOO",
        text="hello",
        changeable=True,
    )
    parent = ElementInfo(
        id="wnd[0]/usr",
        type="GuiUserArea",
        type_as_number=74,
        name="usr",
        text="",
        changeable=True,
        children=[child],
    )
    assert len(parent.children) == 1
    assert parent.children[0].id == "wnd[0]/usr/txtFOO"


def test_element_info_default_no_children():
    elem = ElementInfo(
        id="wnd[0]/sbar",
        type="GuiStatusbar",
        type_as_number=103,
        name="sbar",
        text="Record displayed",
        changeable=False,
    )
    assert elem.children == []
```

- [ ] **Step 2: Implement models**

```python
# src/sapguimcp/sapgui/models.py
"""Pydantic models for structured data exchange."""
from __future__ import annotations
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
    children: list[ElementInfo] = []
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_models.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/sapgui/models.py unittests/sapgui/test_models.py
git commit -m "feat(sapgui): add SessionInfo and ElementInfo Pydantic models"
```

---

### Task 12: dump_tree on GuiVContainer

**Files:**

- Modify: `src/sapguimcp/sapgui/components/base.py`
- Test: `unittests/sapgui/test_base.py` (add dump_tree tests)

- [ ] **Step 1: Write dump_tree tests**

Add to `unittests/sapgui/test_base.py`:

```python
class TestDumpTree:
    def test_dump_tree_single_level(self, mock_com):
        child1 = mock_com(
            id="wnd[0]/usr/txtFOO", type_as_number=31, type_name="GuiTextField",
            name="FOO", text="hello", changeable=True, container_type=False,
        )
        child1.ContainerType = 0
        parent = mock_com(
            id="wnd[0]/usr", type_as_number=74, type_name="GuiUserArea",
            name="usr", text="", changeable=True, container_type=True,
            children=[child1],
        )
        vc = GuiVContainer(parent)
        tree = vc.dump_tree(max_depth=1)
        assert len(tree) == 1  # one child
        assert tree[0].id == "wnd[0]/usr/txtFOO"
        assert tree[0].type == "GuiTextField"
        assert tree[0].children == []

    def test_dump_tree_respects_max_depth(self, mock_com):
        grandchild = mock_com(
            id="wnd[0]/usr/sub/txtBAR", type_as_number=31,
            type_name="GuiTextField", name="BAR", text="",
            changeable=True, container_type=False,
        )
        grandchild.ContainerType = 0
        child = mock_com(
            id="wnd[0]/usr/sub", type_as_number=71,
            type_name="GuiSimpleContainer", name="sub", text="",
            changeable=True, container_type=True, children=[grandchild],
        )
        parent = mock_com(
            id="wnd[0]/usr", type_as_number=74, type_name="GuiUserArea",
            name="usr", text="", changeable=True, container_type=True,
            children=[child],
        )
        vc = GuiVContainer(parent)
        tree = vc.dump_tree(max_depth=1)
        assert len(tree) == 1
        assert tree[0].children == []  # grandchild not included at depth 1

    def test_dump_tree_recurses(self, mock_com):
        grandchild = mock_com(
            id="wnd[0]/usr/sub/txtBAR", type_as_number=31,
            type_name="GuiTextField", name="BAR", text="deep",
            changeable=True, container_type=False,
        )
        grandchild.ContainerType = 0
        child = mock_com(
            id="wnd[0]/usr/sub", type_as_number=71,
            type_name="GuiSimpleContainer", name="sub", text="",
            changeable=True, container_type=True, children=[grandchild],
        )
        parent = mock_com(
            id="wnd[0]/usr", type_as_number=74, type_name="GuiUserArea",
            name="usr", text="", changeable=True, container_type=True,
            children=[child],
        )
        vc = GuiVContainer(parent)
        tree = vc.dump_tree(max_depth=10)
        assert len(tree) == 1
        assert len(tree[0].children) == 1
        assert tree[0].children[0].text == "deep"
```

- [ ] **Step 2: Implement dump_tree**

Add to `GuiVContainer` in `src/sapguimcp/sapgui/components/base.py`:

```python
    def dump_tree(self, max_depth: int = 10) -> list[ElementInfo]:
        """Recursively dump the element tree as a list of ElementInfo models.

        This is the desktop equivalent of a screen snapshot.
        """
        from sapguimcp.sapgui.models import ElementInfo

        return _dump_tree_recursive(self._com, depth=0, max_depth=max_depth)
```

Add the helper function at module level in `base.py`:

```python
def _dump_tree_recursive(com_obj: Any, depth: int, max_depth: int) -> list[ElementInfo]:
    """Walk the COM element tree and build ElementInfo models."""
    from sapguimcp.sapgui.models import ElementInfo

    result: list[ElementInfo] = []
    try:
        children_com = com_obj.Children
        count = children_com.Count
    except Exception:
        return result

    for i in range(count):
        try:
            child = children_com.Item(i)
        except Exception:
            continue

        child_info = ElementInfo(
            id=str(getattr(child, "Id", "")),
            type=str(getattr(child, "Type", "")),
            type_as_number=int(getattr(child, "TypeAsNumber", 0)),
            name=str(getattr(child, "Name", "")),
            text=str(getattr(child, "Text", "")),
            changeable=bool(getattr(child, "Changeable", False)),
            children=(
                _dump_tree_recursive(child, depth + 1, max_depth)
                if depth + 1 < max_depth and getattr(child, "ContainerType", False)
                else []
            ),
        )
        result.append(child_info)
    return result
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest unittests/sapgui/test_base.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/sapgui/components/base.py unittests/sapgui/test_base.py
git commit -m "feat(sapgui): add dump_tree() for recursive screen inspection"
```

---

### Task 13: Public API Re-exports

**Files:**

- Modify: `src/sapguimcp/sapgui/components/__init__.py`

- [ ] **Step 1: Add re-exports for all component classes**

```python
# src/sapguimcp/sapgui/components/__init__.py
"""SAP GUI component wrappers — re-exports all public classes."""
from sapguimcp.sapgui.components.application import GuiApplication
from sapguimcp.sapgui.components.base import GuiComponent, GuiContainer, GuiVComponent, GuiVContainer
from sapguimcp.sapgui.components.button import GuiButton
from sapguimcp.sapgui.components.checkbox import GuiCheckBox, GuiRadioButton
from sapguimcp.sapgui.components.collection import GuiCollection, GuiComponentCollection
from sapguimcp.sapgui.components.combobox import GuiComboBox, GuiComboBoxEntry
from sapguimcp.sapgui.components.connection import GuiConnection
from sapguimcp.sapgui.components.container import (
    GuiContainerShell,
    GuiCustomControl,
    GuiDialogShell,
    GuiDockShell,
    GuiGOSShell,
    GuiScrollContainer,
    GuiSimpleContainer,
    GuiSplitterContainer,
    GuiUserArea,
)
from sapguimcp.sapgui.components.editor import GuiAbapEditor, GuiTextedit
from sapguimcp.sapgui.components.field import GuiBox, GuiCTextField, GuiLabel, GuiPasswordField, GuiTextField
from sapguimcp.sapgui.components.grid import GuiGridView
from sapguimcp.sapgui.components.okcode import GuiOkCodeField
from sapguimcp.sapgui.components.session import GuiSession, GuiSessionInfo
from sapguimcp.sapgui.components.shell import (
    GuiCalendar,
    GuiColorSelector,
    GuiComboBoxControl,
    GuiHTMLViewer,
    GuiInputFieldControl,
    GuiPicture,
    GuiShell,
    GuiSplit,
    GuiToolbarControl,
)
from sapguimcp.sapgui.components.statusbar import GuiStatusbar, GuiStatusPane
from sapguimcp.sapgui.components.tab import GuiTab, GuiTabStrip
from sapguimcp.sapgui.components.table import GuiTableColumn, GuiTableControl, GuiTableRow
from sapguimcp.sapgui.components.toolbar import GuiMenu, GuiMenubar, GuiTitlebar, GuiToolbar
from sapguimcp.sapgui.components.tree import GuiTree
from sapguimcp.sapgui.components.window import GuiFrameWindow, GuiMainWindow, GuiMessageWindow, GuiModalWindow

__all__ = [
    "GuiAbapEditor", "GuiApplication", "GuiBox", "GuiButton",
    "GuiCTextField", "GuiCalendar", "GuiCheckBox", "GuiCollection",
    "GuiColorSelector", "GuiComboBox", "GuiComboBoxControl", "GuiComboBoxEntry",
    "GuiComponent", "GuiComponentCollection", "GuiConnection", "GuiContainer",
    "GuiContainerShell", "GuiCustomControl", "GuiDialogShell", "GuiDockShell",
    "GuiFrameWindow", "GuiGOSShell", "GuiGridView", "GuiHTMLViewer",
    "GuiInputFieldControl", "GuiLabel", "GuiMainWindow", "GuiMenu",
    "GuiMenubar", "GuiMessageWindow", "GuiModalWindow", "GuiOkCodeField",
    "GuiPasswordField", "GuiPicture", "GuiRadioButton", "GuiScrollContainer",
    "GuiSession", "GuiSessionInfo", "GuiShell", "GuiSimpleContainer",
    "GuiSplit", "GuiSplitterContainer", "GuiStatusPane", "GuiStatusbar",
    "GuiTab", "GuiTabStrip", "GuiTableColumn", "GuiTableControl",
    "GuiTableRow", "GuiTextedit", "GuiTextField", "GuiTitlebar",
    "GuiToolbar", "GuiToolbarControl", "GuiTree", "GuiUserArea",
    "GuiVComponent", "GuiVContainer",
]
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest unittests/sapgui/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/sapguimcp/sapgui/components/__init__.py
git commit -m "feat(sapgui): add public API re-exports in components/__init__"
```

---

### Task 14: Integration Tests (Live SAP GUI)

**Files:**

- Create: `unittests/sapgui/test_integration.py`

- [ ] **Step 1: Write integration tests**

These tests only run when SAP GUI is available on the machine. They use the same guard pattern as the existing WebGUI integration tests.

```python
# unittests/sapgui/test_integration.py
"""Integration tests for pysapgui against a live SAP GUI instance.

These tests require:
- SAP GUI for Windows installed and running
- At least one active connection with a logged-in session
- Scripting enabled on the SAP server (sapgui/user_scripting=TRUE)

Skipped automatically when SAP GUI is not available.
"""
from __future__ import annotations

import sys

import pytest

# Skip entire module on non-Windows or when SAP GUI isn't available
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only")


def _sap_gui_available() -> bool:
    """Check if SAP GUI is running and scripting is enabled."""
    try:
        from sapguimcp.sapgui import SapGui

        app = SapGui.connect()
        return app is not None
    except Exception:
        return False


skip_no_sap = pytest.mark.skipif(not _sap_gui_available(), reason="SAP GUI not running")


@skip_no_sap
class TestSapGuiConnect:
    """Tests that connect to a running SAP GUI instance."""

    def test_connect_returns_gui_application(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.application import GuiApplication

        app = SapGui.connect()
        assert isinstance(app, GuiApplication)
        assert app.id == "/app"

    def test_application_has_connections(self):
        from sapguimcp.sapgui import SapGui

        app = SapGui.connect()
        connections = app.connections
        assert connections.Count >= 1

    def test_connection_has_sessions(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.connection import GuiConnection

        app = SapGui.connect()
        conn_com = app.connections.Item(0)
        conn = GuiConnection(conn_com)
        assert conn.sessions.Count >= 1

    def test_session_info(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.session import GuiSession

        app = SapGui.connect()
        conn = app.connections.Item(0)
        ses_com = conn.Children.Item(0)
        session = GuiSession(ses_com)
        info = session.info
        assert info.system_name != ""
        assert info.user != ""
        assert info.language != ""

    def test_find_main_window(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.session import GuiSession
        from sapguimcp.sapgui.components.window import GuiMainWindow

        app = SapGui.connect()
        ses_com = app.connections.Item(0).Children.Item(0)
        session = GuiSession(ses_com)
        wnd = session.find_by_id("wnd[0]")
        assert wnd is not None
        assert isinstance(wnd, GuiMainWindow)

    def test_find_statusbar(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.session import GuiSession
        from sapguimcp.sapgui.components.statusbar import GuiStatusbar

        app = SapGui.connect()
        ses_com = app.connections.Item(0).Children.Item(0)
        session = GuiSession(ses_com)
        sbar = session.find_by_id("wnd[0]/sbar")
        assert sbar is not None
        assert isinstance(sbar, GuiStatusbar)

    def test_find_okcode_field(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.okcode import GuiOkCodeField
        from sapguimcp.sapgui.components.session import GuiSession

        app = SapGui.connect()
        ses_com = app.connections.Item(0).Children.Item(0)
        session = GuiSession(ses_com)
        okcd = session.find_by_id("wnd[0]/tbar[0]/okcd")
        assert okcd is not None
        assert isinstance(okcd, GuiOkCodeField)

    def test_find_by_id_returns_typed_wrappers(self):
        """find_by_id returns typed wrappers, not raw COM — no need for manual wrap_com_object."""
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.session import GuiSession
        from sapguimcp.sapgui.components.window import GuiMainWindow

        app = SapGui.connect()
        ses_com = app.connections.Item(0).Children.Item(0)
        session = GuiSession(ses_com)
        wnd = session.find_by_id("wnd[0]")
        assert isinstance(wnd, GuiMainWindow)

    def test_dump_tree_on_main_window(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.session import GuiSession
        from sapguimcp.sapgui.models import ElementInfo

        app = SapGui.connect()
        ses_com = app.connections.Item(0).Children.Item(0)
        session = GuiSession(ses_com)
        wnd = session.find_by_id("wnd[0]")
        tree = wnd.dump_tree(max_depth=2)
        assert len(tree) > 0
        assert all(isinstance(e, ElementInfo) for e in tree)

    def test_read_statusbar_text(self):
        from sapguimcp.sapgui import SapGui
        from sapguimcp.sapgui.components.session import GuiSession
        from sapguimcp.sapgui.components.statusbar import GuiStatusbar

        app = SapGui.connect()
        ses_com = app.connections.Item(0).Children.Item(0)
        session = GuiSession(ses_com)
        sbar = session.find_by_id("wnd[0]/sbar")
        assert isinstance(sbar, GuiStatusbar)
        # text might be empty but should not raise
        _ = sbar.text
```

- [ ] **Step 2: Run integration tests (will skip if no SAP GUI)**

Run: `python -m pytest unittests/sapgui/test_integration.py -v`
Expected: All tests SKIP (unless SAP GUI is running)

- [ ] **Step 3: Commit**

```bash
git add unittests/sapgui/test_integration.py
git commit -m "test(sapgui): add integration tests for live SAP GUI"
```

---

### Task 15: Final Validation — Run All Tests + Formatting

- [ ] **Step 1: Run isort + black**

```bash
python -m isort src/sapguimcp/sapgui/ unittests/sapgui/ --profile black
python -m black src/sapguimcp/sapgui/ unittests/sapgui/ --line-length 120
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest unittests/sapgui/ -v --tb=short`
Expected: All unit tests PASS, integration tests SKIP (or PASS if SAP GUI available)

- [ ] **Step 3: Run mypy**

```bash
python -m mypy src/sapguimcp/sapgui/ --ignore-missing-imports
```

- [ ] **Step 4: Fix any issues from formatting or type checking**

- [ ] **Step 5: Final commit**

```bash
git add -A src/sapguimcp/sapgui/ unittests/sapgui/
git commit -m "chore(sapgui): format with isort+black, fix type annotations"
```

---
