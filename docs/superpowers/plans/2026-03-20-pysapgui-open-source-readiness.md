# pysapgui Open-Source Readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the pysapgui library for open-source release by filling API gaps, improving design, adding documentation/tests, and finally extracting to its own repo.

**Architecture:** pysapgui is a typed Python wrapper around the SAP GUI Scripting COM API. It lives at `src/sapguimcp/sapgui/` with 28 source files and 15 test files. Zero coupling to the MCP server. Work happens in-place; extraction is the final step.

**Tech Stack:** Python 3.10+, pywin32 (COM), Pydantic v2 (models), pytest

**Spec:** `docs/superpowers/specs/2026-03-20-pysapgui-open-source-readiness-design.md`

**Branch:** Create `feat/pysapgui-open-source` from `main` before starting. All work goes on this branch. Create PR when done — never merge directly.

---

## ⚠ PDF Verification Errata (2026-03-22)

**All Phase 1 COM method names were cross-checked against the SAP GUI Scripting API 6.40 PDF (`docs/sap_gui_scripting_api_reference.pdf`).** The plan's code samples below contain errors in method names, signatures, and non-existent methods. Apply these corrections when implementing:

### Task 1 (GuiGridView #473) — 2 errors — fix PR: #506
1. **Remove** ~~`get_display_cell_value()` / `GetDisplayCellValue`~~ — does not exist in API 6.40. **Add instead:** `get_cell_state()` / `GetCellState(Row, Column) -> String` — returns `'Normal'`/`'Error'`/`'Warning'`/`'Info'`. Note: this is NOT a functional replacement — it serves a different purpose (cell status vs formatted value).
2. ~~`get_column_title_by_name()` / `GetColumnTitleByName`~~ → **`get_displayed_column_title()` / `GetDisplayedColumnTitle(Column) -> String`** — `GetColumnTitleByName` does not exist.
3. All return values must be wrapped with type casts: `int()` for `get_cell_color`, `str()` for `get_cell_icon`, `get_cell_state`, `get_cell_tooltip`, `get_displayed_column_title`, `get_column_tooltip`, `get_column_data_type`, `bool()` for `is_cell_hotspot`. The code samples below omit these.

### Task 2 (GuiTree #474) — 5 errors — fixed in PR: #505
1. ~~`get_node_item_type()` / `GetNodeItemType`~~ → **`get_item_type()` / `GetItemType`** — wrong COM method name. Also: enum is 0-5 (not 0-2): 0=Hierarchy, 1=Image, 2=Text, 3=Bool, 4=Button, 5=Link.
2. ~~`GetItemTooltip`~~ → **`GetItemToolTip`** — capital T in "ToolTip" (contrast with GuiGridView's `GetCellTooltip` lowercase).
3. ~~`is_changeable()` / `IsChangeable()`~~ → **remove entirely** — `Changeable` is a read-only property inherited from `GuiComponent` base class. No `IsChangeable()` method exists.
4. ~~`get_list_tree_item_text()` / `GetListTreeItemText`~~ → **remove entirely** — does not exist in API. `get_item_text()` (COM: `GetItemText`) already exists and works for all tree types.
5. ~~`get_column_tree_item_text()` / `GetColumnTreeItemText`~~ → **remove entirely** — same as above.

### Task 3 (GuiTextedit/GuiAbapEditor #475) — 1 error, 2 notes
1. `set_unprotected_text_part()` should return **`bool`** (not `None`) — COM: `SetUnprotectedTextPart` returns `Boolean` (True on success).
2. Note: `LastVisibleLine` is not in PDF 6.40 but likely works in practice (newer SAP GUI version).
3. Note: `GuiAbapEditor` class is entirely absent from PDF 6.40 — cannot verify its properties. Implement based on observed behavior.

### Task 4 (GuiTableControl #476) — no errors
All three planned additions (`GetAbsoluteRow`, `Columns`, `Rows`) confirmed in PDF. Note: `GetAbsoluteRow` raises an exception if the row is not currently visible (unlike `Rows` collection which resets index 0 after scrolling).

### Task 5 (GuiContextMenu #477) — 1 error
1. ~~`class GuiContextMenu(GuiVContainer)`~~ → **`class GuiContextMenu(GuiMenu)`** — PDF says GuiContextMenu extends GuiMenu, not GuiVContainer. Since `GuiMenu` already implements `select()`, the class body can be just a docstring — `select()` is inherited for free.

### Task 6 (GuiScrollbar #478) — no errors
All 4 properties (`Minimum`, `Maximum`, `Position`, `PageSize`) confirmed with correct names and access modes. Standalone (non-GuiComponent) design confirmed.

---

## Phase 1: API Completeness

All Phase 1 tasks are independent and can be parallelized.

### Task 1: GuiGridView — fill missing methods (#473)

**Files:**
- Modify: `src/sapguimcp/sapgui/components/grid.py` (189 lines, append after line 189)
- Modify: `unittests/sapgui/test_grid.py` (create if not exists, or append)

- [ ] **Step 1: Write failing tests for missing grid methods**

Add to `unittests/sapgui/test_grid.py`:

```python
"""Tests for GuiGridView missing methods — issue #473."""
from unittest.mock import MagicMock
from sapguimcp.sapgui.components.grid import GuiGridView


def _make_grid():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "GridView"
    return GuiGridView(com)


class TestGuiGridViewCellInfo:
    def test_get_cell_color(self):
        grid = _make_grid()
        grid._com.GetCellColor.return_value = 3
        assert grid.get_cell_color(0, "COL") == 3
        grid._com.GetCellColor.assert_called_once_with(0, "COL")

    def test_get_cell_icon(self):
        grid = _make_grid()
        grid._com.GetCellIcon.return_value = "@01@"
        assert grid.get_cell_icon(0, "COL") == "@01@"

    def test_get_cell_state(self):
        grid = _make_grid()
        grid._com.GetCellState.return_value = "Normal"
        assert grid.get_cell_state(0, "COL") == "Normal"

    def test_modify_cell(self):
        grid = _make_grid()
        grid.modify_cell(0, "COL", "new")
        grid._com.ModifyCell.assert_called_once_with(0, "COL", "new")

    def test_is_cell_hotspot(self):
        grid = _make_grid()
        grid._com.IsCellHotspot.return_value = True
        assert grid.is_cell_hotspot(0, "COL") is True

    def test_get_cell_tooltip(self):
        grid = _make_grid()
        grid._com.GetCellTooltip.return_value = "hint"
        assert grid.get_cell_tooltip(0, "COL") == "hint"


class TestGuiGridViewColumnInfo:
    def test_get_displayed_column_title(self):
        grid = _make_grid()
        grid._com.GetDisplayedColumnTitle.return_value = "Material"
        assert grid.get_displayed_column_title("MATNR") == "Material"

    def test_get_column_tooltip(self):
        grid = _make_grid()
        grid._com.GetColumnTooltip.return_value = "tip"
        assert grid.get_column_tooltip("COL") == "tip"

    def test_get_column_data_type(self):
        grid = _make_grid()
        grid._com.GetColumnDataType.return_value = "CHAR"
        assert grid.get_column_data_type("COL") == "CHAR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/sapgui/test_grid.py -v`
Expected: FAIL — methods not defined on GuiGridView

- [ ] **Step 3: Implement missing methods**

Append to `src/sapguimcp/sapgui/components/grid.py` inside the `GuiGridView` class (before the final line):

```python
    # --- Cell info methods ---

    def get_cell_color(self, row: int, column: str) -> int:
        """Return the color index of a cell."""
        return int(self._com.GetCellColor(row, column))

    def get_cell_icon(self, row: int, column: str) -> str:
        """Return the icon string (e.g. '@01@') displayed in a cell."""
        return str(self._com.GetCellIcon(row, column))

    def get_cell_state(self, row: int, column: str) -> str:
        """Return the state of a cell ('Normal', 'Error', 'Warning', 'Info')."""
        return str(self._com.GetCellState(row, column))

    def modify_cell(self, row: int, column: str, value: str) -> None:
        """Modify a cell value. SAP spec alias for set_cell_value."""
        self._com.ModifyCell(row, column, value)

    def is_cell_hotspot(self, row: int, column: str) -> bool:
        """Return whether a cell is a clickable hotspot."""
        return bool(self._com.IsCellHotspot(row, column))

    def get_cell_tooltip(self, row: int, column: str) -> str:
        """Return the tooltip text for a cell."""
        return str(self._com.GetCellTooltip(row, column))

    # --- Column info methods ---

    def get_displayed_column_title(self, column: str) -> str:
        """Return the currently displayed title for a column."""
        return str(self._com.GetDisplayedColumnTitle(column))

    def get_column_tooltip(self, column: str) -> str:
        """Return the tooltip text for a column header."""
        return str(self._com.GetColumnTooltip(column))

    def get_column_data_type(self, column: str) -> str:
        """Return the ABAP data type of a column (e.g. 'CHAR', 'NUMC')."""
        return str(self._com.GetColumnDataType(column))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/sapgui/test_grid.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/components/grid.py unittests/sapgui/test_grid.py
python -m black src/sapguimcp/sapgui/components/grid.py unittests/sapgui/test_grid.py
git add src/sapguimcp/sapgui/components/grid.py unittests/sapgui/test_grid.py
git commit -m "feat(pysapgui): add missing GuiGridView methods (#473)"
```

---

### Task 2: GuiTree — fill missing methods (#474)

**Files:**
- Modify: `src/sapguimcp/sapgui/components/tree.py` (98 lines, append)
- Modify: `unittests/sapgui/test_tree.py` (create if not exists, or append)

- [ ] **Step 1: Write failing tests**

```python
"""Tests for GuiTree missing methods — issue #474."""
from unittest.mock import MagicMock
from sapguimcp.sapgui.components.tree import GuiTree


def _make_tree():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "Tree"
    return GuiTree(com)


class TestGuiTreeCheckbox:
    def test_change_checkbox(self):
        tree = _make_tree()
        tree.change_checkbox("KEY1", "COL1", True)
        tree._com.ChangeCheckbox.assert_called_once_with("KEY1", "COL1", True)

    def test_get_checkbox_state(self):
        tree = _make_tree()
        tree._com.GetCheckBoxState.return_value = True
        assert tree.get_checkbox_state("KEY1", "COL1") is True


class TestGuiTreeNodeInfo:
    def test_get_item_type(self):
        tree = _make_tree()
        tree._com.GetItemType.return_value = 1
        assert tree.get_item_type("KEY1", "COL1") == 1

    def test_get_item_tooltip(self):
        tree = _make_tree()
        tree._com.GetItemToolTip.return_value = "tip"
        assert tree.get_item_tooltip("KEY1", "COL1") == "tip"

    def test_get_node_style(self):
        tree = _make_tree()
        tree._com.GetNodeStyle.return_value = 2
        assert tree.get_node_style("KEY1") == 2

    def test_is_folder(self):
        tree = _make_tree()
        tree._com.IsFolder.return_value = True
        assert tree.is_folder("KEY1") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/sapgui/test_tree.py -v`
Expected: FAIL

- [ ] **Step 3: Implement missing methods**

Append to `GuiTree` class in `src/sapguimcp/sapgui/components/tree.py`:

```python
    # --- Checkbox methods ---

    def change_checkbox(self, node_key: str, item_name: str, checked: bool) -> None:
        """Set the checkbox state of a tree item."""
        self._com.ChangeCheckbox(node_key, item_name, checked)

    def get_checkbox_state(self, node_key: str, item_name: str) -> bool:
        """Return the checkbox state of a tree item."""
        return bool(self._com.GetCheckBoxState(node_key, item_name))

    # --- Node info methods ---

    def get_item_type(self, node_key: str, item_name: str) -> int:
        """Return the type of a tree item.

        Values: 0=Hierarchy, 1=Image, 2=Text, 3=Bool, 4=Button, 5=Link.
        """
        return int(self._com.GetItemType(node_key, item_name))

    def get_item_tooltip(self, node_key: str, item_name: str) -> str:
        """Return the tooltip text of a tree item."""
        return str(self._com.GetItemToolTip(node_key, item_name))

    def get_node_style(self, node_key: str) -> int:
        """Return the style of a tree node."""
        return int(self._com.GetNodeStyle(node_key))

    def is_folder(self, node_key: str) -> bool:
        """Return whether a tree node is a folder (expandable)."""
        return bool(self._com.IsFolder(node_key))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/sapgui/test_tree.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/components/tree.py unittests/sapgui/test_tree.py
python -m black src/sapguimcp/sapgui/components/tree.py unittests/sapgui/test_tree.py
git add src/sapguimcp/sapgui/components/tree.py unittests/sapgui/test_tree.py
git commit -m "feat(pysapgui): add missing GuiTree methods (#474)"
```

---

### Task 3: GuiTextedit/GuiAbapEditor — fill missing methods (#475)

**Files:**
- Modify: `src/sapguimcp/sapgui/components/editor.py` (93 lines)
- Modify: `unittests/sapgui/test_editor.py` (create if not exists)

- [ ] **Step 1: Write failing tests**

```python
"""Tests for editor missing methods — issue #475."""
from unittest.mock import MagicMock
from sapguimcp.sapgui.components.editor import GuiAbapEditor, GuiTextedit


def _make_textedit():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "TextEdit"
    return GuiTextedit(com)


def _make_abap_editor():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "AbapEditor"
    return GuiAbapEditor(com)


class TestGuiTexteditMissing:
    def test_first_visible_line_get(self):
        te = _make_textedit()
        te._com.FirstVisibleLine = 5
        assert te.first_visible_line == 5

    def test_first_visible_line_set(self):
        te = _make_textedit()
        te.first_visible_line = 10
        assert te._com.FirstVisibleLine == 10

    def test_last_visible_line(self):
        te = _make_textedit()
        te._com.LastVisibleLine = 25
        assert te.last_visible_line == 25

    def test_set_unprotected_text_part(self):
        te = _make_textedit()
        te._com.SetUnprotectedTextPart.return_value = True
        result = te.set_unprotected_text_part(0, "new text")
        te._com.SetUnprotectedTextPart.assert_called_once_with(0, "new text")
        assert result is True

    def test_get_unprotected_text_part(self):
        te = _make_textedit()
        te._com.GetUnprotectedTextPart.return_value = "text"
        assert te.get_unprotected_text_part(0) == "text"


class TestGuiAbapEditorMissing:
    def test_first_visible_line_get(self):
        ed = _make_abap_editor()
        ed._com.FirstVisibleLine = 5
        assert ed.first_visible_line == 5

    def test_first_visible_line_set(self):
        ed = _make_abap_editor()
        ed.first_visible_line = 10
        assert ed._com.FirstVisibleLine == 10

    def test_last_visible_line(self):
        ed = _make_abap_editor()
        ed._com.LastVisibleLine = 25
        assert ed.last_visible_line == 25

    def test_is_read_only(self):
        ed = _make_abap_editor()
        ed._com.IsReadOnly = True
        assert ed.is_read_only is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/sapgui/test_editor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement missing methods**

In `src/sapguimcp/sapgui/components/editor.py`, add to `GuiTextedit` class:

```python
    @property
    def first_visible_line(self) -> int:
        """First visible line in the editor viewport."""
        return self._com.FirstVisibleLine

    @first_visible_line.setter
    def first_visible_line(self, value: int) -> None:
        self._com.FirstVisibleLine = value

    @property
    def last_visible_line(self) -> int:
        """Last visible line in the editor viewport (read-only)."""
        return self._com.LastVisibleLine

    def set_unprotected_text_part(self, part: int, text: str) -> bool:
        """Set the text of an unprotected text part by index.

        Returns True on success, False on failure.
        """
        return bool(self._com.SetUnprotectedTextPart(part, text))

    def get_unprotected_text_part(self, part: int) -> str:
        """Get the text of an unprotected text part by index."""
        return str(self._com.GetUnprotectedTextPart(part))
```

Add to `GuiAbapEditor` class:

```python
    @property
    def first_visible_line(self) -> int:
        """First visible line in the editor viewport."""
        return self._com.FirstVisibleLine

    @first_visible_line.setter
    def first_visible_line(self, value: int) -> None:
        self._com.FirstVisibleLine = value

    @property
    def last_visible_line(self) -> int:
        """Last visible line in the editor viewport (read-only)."""
        return self._com.LastVisibleLine

    @property
    def is_read_only(self) -> bool:
        """Whether the editor is in read-only mode."""
        return bool(self._com.IsReadOnly)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/sapgui/test_editor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/components/editor.py unittests/sapgui/test_editor.py
python -m black src/sapguimcp/sapgui/components/editor.py unittests/sapgui/test_editor.py
git add src/sapguimcp/sapgui/components/editor.py unittests/sapgui/test_editor.py
git commit -m "feat(pysapgui): add missing editor methods (#475)"
```

---

### Task 4: GuiTableControl — fill missing methods (#476)

**Files:**
- Modify: `src/sapguimcp/sapgui/components/table.py` (93 lines)
- Modify: `unittests/sapgui/test_table.py` (create if not exists)

- [ ] **Step 1: Write failing tests**

```python
"""Tests for GuiTableControl missing methods — issue #476."""
from unittest.mock import MagicMock
from sapguimcp.sapgui.components.table import GuiTableControl, GuiTableRow, GuiTableColumn


def _make_table():
    com = MagicMock()
    com.TypeAsNumber = 80
    return GuiTableControl(com)


class TestGuiTableControlMissing:
    def test_get_absolute_row(self):
        tbl = _make_table()
        row_com = MagicMock()
        tbl._com.GetAbsoluteRow.return_value = row_com
        result = tbl.get_absolute_row(5)
        tbl._com.GetAbsoluteRow.assert_called_once_with(5)
        assert isinstance(result, GuiTableRow)

    def test_columns_returns_typed_collection(self):
        """Verify columns property returns objects we can work with."""
        tbl = _make_table()
        col_com = MagicMock()
        col_com.TypeAsNumber = 81  # GuiTableColumn if typed
        tbl._com.Columns.Count = 1
        tbl._com.Columns.Item.return_value = col_com
        # Verify we can access columns
        assert tbl.columns is not None

    def test_rows_returns_typed_collection(self):
        """Verify rows property returns objects we can work with."""
        tbl = _make_table()
        row_com = MagicMock()
        tbl._com.Rows.Count = 1
        tbl._com.Rows.Item.return_value = row_com
        assert tbl.rows is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/sapgui/test_table.py -v`
Expected: FAIL

- [ ] **Step 3: Implement missing methods**

Add to `GuiTableControl` class in `src/sapguimcp/sapgui/components/table.py`:

```python
    def get_absolute_row(self, row: int) -> "GuiTableRow":
        """Return a row by absolute index (works with scrolled tables).

        Unlike indexing via rows[i], this accounts for the scroll position
        and returns the row at the given absolute position in the data.
        """
        from sapguimcp.sapgui.components.table import GuiTableRow

        return GuiTableRow(self._com.GetAbsoluteRow(row))
```

Also verify `columns` and `rows` properties return typed collections. Check existing code — if they return raw COM, wrap them. If already typed, just add a test confirming the type.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/sapgui/test_table.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/components/table.py unittests/sapgui/test_table.py
python -m black src/sapguimcp/sapgui/components/table.py unittests/sapgui/test_table.py
git add src/sapguimcp/sapgui/components/table.py unittests/sapgui/test_table.py
git commit -m "feat(pysapgui): add missing GuiTableControl methods (#476)"
```

---

### Task 5: GuiContextMenu wrapper (#477)

**Files:**
- Create: new class in `src/sapguimcp/sapgui/components/toolbar.py` (natural home — menus/context menus)
- Modify: `src/sapguimcp/sapgui/components/__init__.py` (add export)
- Modify: `src/sapguimcp/sapgui/_factory.py` (register type 127)
- Modify: `src/sapguimcp/sapgui/_types.py` (verify enum entry exists)
- Create: test in `unittests/sapgui/test_toolbar.py`

- [ ] **Step 1: Add type 127 to the enum**

The enum in `src/sapguimcp/sapgui/_types.py` does NOT have `GuiContextMenu = 127` (jumps from 126 to 128). Add it:

```python
    GuiContextMenu = 127
```

Insert between `GuiDockShell = 126` and `GuiComponentCollection = 128`.

- [ ] **Step 2: Write failing tests**

```python
"""Tests for GuiContextMenu — issue #477."""
from unittest.mock import MagicMock
from sapguimcp.sapgui.components.toolbar import GuiContextMenu


def _make_context_menu():
    com = MagicMock()
    com.TypeAsNumber = 127
    return GuiContextMenu(com)


class TestGuiContextMenu:
    def test_select(self):
        menu = _make_context_menu()
        menu.select()
        menu._com.Select.assert_called_once()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest unittests/sapgui/test_toolbar.py -v`
Expected: FAIL — GuiContextMenu not defined

- [ ] **Step 4: Implement GuiContextMenu**

Add to `src/sapguimcp/sapgui/components/toolbar.py`:

```python
class GuiContextMenu(GuiMenu):
    """Context menu item (type 127).

    Extends GuiMenu — inherits select() and other menu methods.
    Appears when a context menu is open. Each item in the menu is a
    GuiContextMenu object. Call select() to click the menu item.
    """
```

- [ ] **Step 5: Register in factory**

Add to `_TYPE_MAP` in `src/sapguimcp/sapgui/_factory.py`:

```python
    127: GuiContextMenu,
```

Add the import at the top of the factory file's import block.

- [ ] **Step 6: Add to component exports**

Add `GuiContextMenu` to `__all__` in `src/sapguimcp/sapgui/components/__init__.py` and add the import.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest unittests/sapgui/test_toolbar.py -v`
Expected: ALL PASS

- [ ] **Step 8: Run full test suite to check nothing broke**

Run: `python -m pytest unittests/sapgui/ -v`
Expected: ALL PASS

- [ ] **Step 9: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/components/toolbar.py src/sapguimcp/sapgui/components/__init__.py src/sapguimcp/sapgui/_factory.py unittests/sapgui/test_toolbar.py
python -m black src/sapguimcp/sapgui/components/toolbar.py src/sapguimcp/sapgui/components/__init__.py src/sapguimcp/sapgui/_factory.py unittests/sapgui/test_toolbar.py
git add src/sapguimcp/sapgui/components/toolbar.py src/sapguimcp/sapgui/components/__init__.py src/sapguimcp/sapgui/_factory.py unittests/sapgui/test_toolbar.py
git commit -m "feat(pysapgui): add GuiContextMenu wrapper (type 127) (#477)"
```

---

### Task 6: GuiScrollbar wrapper (#478)

**Files:**
- Create: new class in `src/sapguimcp/sapgui/components/container.py` (lives alongside GuiUserArea which exposes it)
- Modify: `src/sapguimcp/sapgui/components/__init__.py` (add export)
- Modify: `src/sapguimcp/sapgui/components/container.py` (update GuiUserArea scrollbar properties)
- Create: test in `unittests/sapgui/test_container.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for GuiScrollbar — issue #478."""
from unittest.mock import MagicMock, PropertyMock
from sapguimcp.sapgui.components.container import GuiScrollbar, GuiUserArea


def _make_scrollbar():
    com = MagicMock()
    return GuiScrollbar(com)


def _make_user_area():
    com = MagicMock()
    com.TypeAsNumber = 74
    return GuiUserArea(com)


class TestGuiScrollbar:
    def test_minimum(self):
        sb = _make_scrollbar()
        sb._com.Minimum = 0
        assert sb.minimum == 0

    def test_maximum(self):
        sb = _make_scrollbar()
        sb._com.Maximum = 100
        assert sb.maximum == 100

    def test_position_get(self):
        sb = _make_scrollbar()
        sb._com.Position = 42
        assert sb.position == 42

    def test_position_set(self):
        sb = _make_scrollbar()
        sb.position = 10
        assert sb._com.Position == 10

    def test_page_size(self):
        sb = _make_scrollbar()
        sb._com.PageSize = 20
        assert sb.page_size == 20


class TestGuiUserAreaScrollbars:
    def test_vertical_scrollbar_returns_typed(self):
        ua = _make_user_area()
        ua._com.VerticalScrollbar = MagicMock()
        result = ua.vertical_scrollbar
        assert isinstance(result, GuiScrollbar)

    def test_horizontal_scrollbar_returns_typed(self):
        ua = _make_user_area()
        ua._com.HorizontalScrollbar = MagicMock()
        result = ua.horizontal_scrollbar
        assert isinstance(result, GuiScrollbar)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/sapgui/test_container.py -v`
Expected: FAIL

- [ ] **Step 3: Implement GuiScrollbar and update GuiUserArea**

Add to `src/sapguimcp/sapgui/components/container.py` (before GuiUserArea):

```python
class GuiScrollbar:
    """Scrollbar object exposed by GuiUserArea (type 100).

    Not a GuiComponent subclass — it's a standalone helper object
    accessible via GuiUserArea.vertical_scrollbar / horizontal_scrollbar.
    """

    def __init__(self, com_obj: "CDispatch") -> None:
        self._com = com_obj

    @property
    def minimum(self) -> int:
        """Minimum scroll position."""
        return self._com.Minimum

    @property
    def maximum(self) -> int:
        """Maximum scroll position."""
        return self._com.Maximum

    @property
    def position(self) -> int:
        """Current scroll position."""
        return self._com.Position

    @position.setter
    def position(self, value: int) -> None:
        self._com.Position = value

    @property
    def page_size(self) -> int:
        """Number of visible rows/columns (page size for scrolling)."""
        return self._com.PageSize

    def __repr__(self) -> str:
        return f"<GuiScrollbar pos={self.position} range={self.minimum}-{self.maximum}>"
```

Update `GuiUserArea` properties to return typed `GuiScrollbar`:

```python
class GuiUserArea(GuiVContainer):
    """Main working area of a window (type 74, prefix: usr)."""

    @property
    def vertical_scrollbar(self) -> GuiScrollbar:
        """Vertical scrollbar of the user area."""
        return GuiScrollbar(self._com.VerticalScrollbar)

    @property
    def horizontal_scrollbar(self) -> GuiScrollbar:
        """Horizontal scrollbar of the user area."""
        return GuiScrollbar(self._com.HorizontalScrollbar)
```

- [ ] **Step 4: Add GuiScrollbar to component exports**

Add `GuiScrollbar` to `__all__` and imports in `components/__init__.py`.

**Note:** GuiScrollbar is NOT registered in `_factory.py` because it's not discovered via `wrap_com_object()` — it's accessed as a property of `GuiUserArea`, not found via `find_by_id()`. This is intentional.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest unittests/sapgui/test_container.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/components/container.py src/sapguimcp/sapgui/components/__init__.py unittests/sapgui/test_container.py
python -m black src/sapguimcp/sapgui/components/container.py src/sapguimcp/sapgui/components/__init__.py unittests/sapgui/test_container.py
git add src/sapguimcp/sapgui/components/container.py src/sapguimcp/sapgui/components/__init__.py unittests/sapgui/test_container.py
git commit -m "feat(pysapgui): add GuiScrollbar wrapper and typed UserArea scrollbars (#478)"
```

---

## Phase 2: Design Improvements

All Phase 2 tasks are independent and can be parallelized.

### Task 7: Extract _login.py to login submodule (#479)

**Files:**
- Rename: `src/sapguimcp/sapgui/_login.py` → `src/sapguimcp/sapgui/login.py`
- Modify: `src/sapguimcp/backend/desktop/__init__.py` (update import)
- Modify: any other files importing `_login`
- Modify: `unittests/sapgui/test_login.py` (update imports)

- [ ] **Step 1: Search for all _login imports**

Run: `grep -rn "_login" src/sapguimcp/ unittests/sapgui/` to find all references.

- [ ] **Step 2: Rename the file**

```bash
git mv src/sapguimcp/sapgui/_login.py src/sapguimcp/sapgui/login.py
```

- [ ] **Step 3: Update all imports**

In `src/sapguimcp/backend/desktop/__init__.py`, change:
```python
import sapguimcp.sapgui._login as _login_mod
```
to:
```python
import sapguimcp.sapgui.login as _login_mod
```

Update any test imports similarly.

- [ ] **Step 4: Run full test suite (not just sapgui)**

Run: `python -m pytest unittests/ -v`
Expected: ALL PASS — desktop backend imports must also work

- [ ] **Step 5: Run isort + black on changed files, then commit**

```bash
python -m isort src/sapguimcp/sapgui/login.py src/sapguimcp/backend/desktop/__init__.py
python -m black src/sapguimcp/sapgui/login.py src/sapguimcp/backend/desktop/__init__.py
git add src/sapguimcp/sapgui/login.py src/sapguimcp/backend/desktop/__init__.py unittests/sapgui/test_login.py
git commit -m "refactor(pysapgui): rename _login.py to login.py for public API (#479)"
```

---

### Task 8: Add context manager to GuiApplication (#480)

**Files:**
- Modify: `src/sapguimcp/sapgui/components/application.py` (111 lines)
- Modify: `unittests/sapgui/test_application.py` (98 lines)

- [ ] **Step 1: Write failing test**

Add to `unittests/sapgui/test_application.py`:

```python
class TestGuiApplicationContextManager:
    def test_enter_returns_self(self):
        com = MagicMock()
        com.TypeAsNumber = 10
        app = GuiApplication(com)
        assert app.__enter__() is app

    def test_exit_closes_connections_best_effort(self):
        com = MagicMock()
        com.TypeAsNumber = 10
        conn_com = MagicMock()
        com.Children.Count = 1
        com.Children.Item.return_value = conn_com
        conn_com.TypeAsNumber = 11
        app = GuiApplication(com)
        app.__exit__(None, None, None)
        conn_com.CloseConnection.assert_called_once()

    def test_exit_suppresses_connection_close_errors(self):
        com = MagicMock()
        com.TypeAsNumber = 10
        conn_com = MagicMock()
        conn_com.CloseConnection.side_effect = Exception("COM error")
        com.Children.Count = 1
        com.Children.Item.return_value = conn_com
        conn_com.TypeAsNumber = 11
        app = GuiApplication(com)
        # Should not raise
        app.__exit__(None, None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/sapgui/test_application.py::TestGuiApplicationContextManager -v`
Expected: FAIL

- [ ] **Step 3: Implement context manager**

Add to `GuiApplication` class in `application.py`:

```python
    def __enter__(self) -> "GuiApplication":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close all connections on exit. Best-effort — errors are suppressed."""
        try:
            for i in range(self._com.Children.Count):
                try:
                    self._com.Children.Item(i).CloseConnection()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/sapgui/test_application.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/components/application.py unittests/sapgui/test_application.py
python -m black src/sapguimcp/sapgui/components/application.py unittests/sapgui/test_application.py
git add src/sapguimcp/sapgui/components/application.py unittests/sapgui/test_application.py
git commit -m "feat(pysapgui): add context manager protocol to GuiApplication (#480)"
```

- [ ] **Step 6: Update `SapGui.connect()` docstring to advertise context manager**

In `src/sapguimcp/sapgui/__init__.py`, update the `connect()` docstring:

```python
    @staticmethod
    def connect() -> "GuiApplication":
        """Attach to a running SAP GUI instance via the Running Object Table.

        Returns a GuiApplication that supports the context manager protocol::

            with SapGui.connect() as app:
                session = app.connections[0].sessions[0]
                # ... work with session
            # all connections closed on exit
        """
```

```bash
git add src/sapguimcp/sapgui/__init__.py
git commit --amend --no-edit
```

---

### Task 9: Log non-COM exceptions in _safe_com_attr (#481)

**Files:**
- Modify: `src/sapguimcp/sapgui/components/base.py` (lines 191-200)
- Modify: `unittests/sapgui/test_base.py`

- [ ] **Step 1: Read current _safe_com_attr implementation**

Read `src/sapguimcp/sapgui/components/base.py` lines 191-200 to see exact current code.

- [ ] **Step 2: Write test for narrowed exception**

```python
class TestSafeComAttrExceptionNarrowing:
    def test_catches_com_error(self):
        """Should catch pywintypes.com_error and return default."""
        import pywintypes
        com = MagicMock()
        com.SomeAttr = property(lambda self: (_ for _ in ()).throw(pywintypes.com_error(-2147352567, 'err', None, None)))
        result = _safe_com_attr(com, "SomeAttr", "default")
        assert result == "default"

    def test_non_com_exception_still_caught_with_warning(self):
        """Non-COM exceptions should still be caught but logged."""
        com = MagicMock()
        type(com).SomeAttr = PropertyMock(side_effect=RuntimeError("unexpected"))
        result = _safe_com_attr(com, "SomeAttr", "default")
        assert result == "default"
```

- [ ] **Step 3: Update _safe_com_attr**

```python
def _safe_com_attr(com_obj: "CDispatch", attr: str, default: Any = None) -> Any:
    """Safely get a COM attribute, returning default on COM errors."""
    try:
        return getattr(com_obj, attr)
    except Exception as exc:  # noqa: BLE001
        # Log non-COM exceptions as warnings — they may indicate real bugs
        try:
            import pywintypes
            if not isinstance(exc, pywintypes.com_error):
                logger.warning("Unexpected non-COM error accessing %s: %s", attr, exc)
        except ImportError:
            pass
        return default
```

- [ ] **Step 4: Run tests, then isort + black, then commit**

```bash
python -m pytest unittests/sapgui/test_base.py -v
git add src/sapguimcp/sapgui/components/base.py unittests/sapgui/test_base.py
git commit -m "fix(pysapgui): log non-COM exceptions in _safe_com_attr (#481)"
```

---

### ~~Task 10: Replace Pydantic with dataclasses (#482) — CANCELLED~~

**Decision:** Keeping Pydantic. Better usability (`.model_dump()`, validation, JSON serialization) outweighs the dependency cost. `pydantic>=2.0` will be a dependency of the standalone package.

---

### Task 11: Add __all__ to all component modules (#483)

**Files:**
- Modify: all 21 files in `src/sapguimcp/sapgui/components/` plus core modules

- [ ] **Step 1: Add __all__ to each component file**

For each file, add `__all__` listing only the public classes. Example for `button.py`:

```python
__all__ = ["GuiButton"]
```

For `field.py`:
```python
__all__ = ["GuiTextField", "GuiCTextField", "GuiPasswordField", "GuiLabel", "GuiBox"]
```

Also add to core modules:
- `_errors.py`: `__all__ = ["SapGuiError", "SapConnectionError", "ScriptingDisabledError", "ElementNotFoundError", "SapGuiTimeoutError"]`
- `models.py`: `__all__ = ["SessionInfo", "ElementInfo"]`
- `__init__.py`: `__all__ = ["SapGui"]`

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest unittests/sapgui/ -v`
Expected: ALL PASS

- [ ] **Step 3: Run isort + black on all modified files, then commit**

```bash
python -m isort src/sapguimcp/sapgui/
python -m black src/sapguimcp/sapgui/
git add src/sapguimcp/sapgui/
git commit -m "chore(pysapgui): add __all__ to all modules (#483)"
```

---

### Task 12: Document thread safety (#484)

**Files:**
- Modify: `src/sapguimcp/sapgui/_com.py` (add module docstring about threading)

- [ ] **Step 1: Add threading docstring to _com.py**

Add or update the module docstring at the top of `_com.py`:

```python
"""Low-level COM helpers for connecting to SAP GUI.

Thread Safety
-------------
COM objects use Single-Threaded Apartment (STA) model. All calls to a given
SAP GUI session must happen from the same thread that called
``pythoncom.CoInitialize()``. Creating COM objects on one thread and using
them on another will raise ``pywintypes.com_error`` or cause silent corruption.

If you use pysapgui from async code, run all COM calls in a dedicated thread
via ``asyncio.to_thread()`` or a ``ThreadPoolExecutor``.
"""
```

- [ ] **Step 2: Commit**

```bash
git add src/sapguimcp/sapgui/_com.py
git commit -m "docs(pysapgui): add thread safety documentation to _com.py (#484)"
```

---

## Phase 3: Documentation

### Task 13: Write README (#485)

**Files:**
- Create: `docs/pysapgui-README.md`

- [ ] **Step 1: Write the README**

The README should include:
1. **Title and one-liner** — "pysapgui — Typed Python wrapper for SAP GUI Scripting"
2. **Installation** — `pip install pysapgui` (future), currently: install from this repo
3. **Prerequisites** — SAP GUI for Windows, scripting enabled (brief, link to setup guide)
4. **Quickstart** — 10-line example: connect → open transaction → read field → press button
5. **Why pysapgui?** — comparison table vs pysapscript, raw COM, RF SapGuiLibrary
6. **Architecture** — class hierarchy diagram (text-based), factory pattern explanation
7. **Thread safety** — one paragraph warning + link to _com.py docs
8. **API overview** — table of key classes with one-line descriptions
9. **Contributing** — brief, link to CONTRIBUTING.md

- [ ] **Step 2: Commit**

```bash
git add docs/pysapgui-README.md
git commit -m "docs(pysapgui): add README for standalone library (#485)"
```

---

### Task 14: Docstring audit (#486)

**Files:**
- Modify: all files in `src/sapguimcp/sapgui/` and `src/sapguimcp/sapgui/components/`

- [ ] **Step 1: Audit each file for missing docstrings**

Go through every public class and method. Add docstrings where missing. Follow the conventions from the original design spec:
- Skip trivial restating (`"""SAP GUI text field."""`)
- Focus on "when to use this vs alternatives" and "gotchas"
- Document COM quirks and spec-specific behavior

- [ ] **Step 2: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/
python -m black src/sapguimcp/sapgui/
git add src/sapguimcp/sapgui/
git commit -m "docs(pysapgui): complete docstring audit (#486)"
```

---

### Task 15: Create examples directory (#487)

**Files:**
- Create: `examples/pysapgui/basic_navigation.py`
- Create: `examples/pysapgui/alv_grid_export.py`
- Create: `examples/pysapgui/form_filling.py`
- Create: `examples/pysapgui/tree_navigation.py`

- [ ] **Step 1: Write basic_navigation.py**

```python
"""Connect to SAP GUI, open SE16, and read the status bar."""
from sapguimcp.sapgui import SapGui

app = SapGui.connect()
session = app.connections[0].sessions[0]

# Navigate to transaction SE16
session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE16"
session.find_by_id("wnd[0]").send_v_key(0)  # Enter

# Read current transaction from session info
print(f"Transaction: {session.info.transaction}")
print(f"Status bar: {session.find_by_id('wnd[0]/sbar').text}")
```

- [ ] **Step 2: Write alv_grid_export.py**

```python
"""Read data from an ALV grid (e.g., SE16N result)."""
from sapguimcp.sapgui import SapGui
from sapguimcp.sapgui.components.grid import GuiGridView

app = SapGui.connect()
session = app.connections[0].sessions[0]

# Find the grid on the current screen
grid = session.find_by_id("wnd[0]/usr/cntlGRID1/shellcont/shell")
assert isinstance(grid, GuiGridView)

# Read all rows
for row in range(grid.row_count):
    values = {col: grid.get_cell_value(row, col) for col in grid.column_order.split(",")}
    print(values)
```

- [ ] **Step 3: Write form_filling.py**

```python
"""Fill a selection screen and execute a report."""
from sapguimcp.sapgui import SapGui

app = SapGui.connect()
session = app.connections[0].sessions[0]

# Open a report
session.find_by_id("wnd[0]/tbar[0]/okcd").text = "/nSE38"
session.find_by_id("wnd[0]").send_v_key(0)

# Fill the program name
session.find_by_id("wnd[0]/usr/ctxtRS38M-PROGRAMM").text = "RSPARAM"

# Press F8 (Execute)
session.find_by_id("wnd[0]").send_v_key(8)

print(f"Now on screen: {session.info.screen_number}")
```

- [ ] **Step 4: Write tree_navigation.py**

```python
"""Navigate a tree control (e.g., in SPRO or SM30)."""
from sapguimcp.sapgui import SapGui
from sapguimcp.sapgui.components.tree import GuiTree

app = SapGui.connect()
session = app.connections[0].sessions[0]

# Find the tree
tree = session.find_by_id("wnd[0]/usr/cntlTREE/shellcont/shell")
assert isinstance(tree, GuiTree)

# List all top-level nodes
keys = tree.get_all_node_keys()
for key in keys[:10]:  # first 10
    text = tree.get_node_text_by_key(key)
    children = tree.get_node_children_count(key)
    print(f"  {key}: {text} ({children} children)")
```

- [ ] **Step 5: Commit**

```bash
git add examples/pysapgui/
git commit -m "docs(pysapgui): add example scripts (#487)"
```

### Task 15a: Add doctests to public API methods (#497)

**Files:**
- Modify: key files in `src/sapguimcp/sapgui/components/`

- [ ] **Step 1: Add doctests to high-value methods**

Add usage examples as doctests to at least 10 methods. Use `# doctest: +SKIP` for methods requiring COM. Example:

```python
class GuiGridView(GuiShell):
    def get_cell_value(self, row: int, column: str) -> str:
        """Return the raw value of a cell.

        Example::

            >>> grid = session.find_by_id("wnd[0]/usr/cntlGRID/shellcont/shell")  # doctest: +SKIP
            >>> grid.get_cell_value(0, "MATNR")  # doctest: +SKIP
            '000000001234'
        """
        return self._com.GetCellValue(row, column)
```

Target methods: `SapGui.connect()`, `GuiSession.find_by_id()`, `GuiSession.send_command()`, `GuiGridView.get_cell_value()`, `GuiTree.select_node()`, `GuiComboBox.entries`, `GuiVContainer.dump_tree()`, `GuiTextField.text`, `GuiButton.press()`, `GuiFrameWindow.send_v_key()`.

- [ ] **Step 2: Run isort + black, then commit**

```bash
python -m isort src/sapguimcp/sapgui/
python -m black src/sapguimcp/sapgui/
git add src/sapguimcp/sapgui/
git commit -m "docs(pysapgui): add doctests to public API methods (#497)"
```

---

### Task 15b: Set up documentation site (#498)

**Files:**
- Create: docs config (e.g., `mkdocs.yml` or use pdoc)
- Create: GitHub Actions workflow for docs deployment

- [ ] **Step 1: Decide on tooling**

Read the existing project CI to understand constraints. Recommended: start with `pdoc` — one command, zero config:

```bash
pip install pdoc
pdoc src/sapguimcp/sapgui/ -o site/
```

If mkdocs/RTD preferred, set up `mkdocs.yml` with `mkdocstrings` plugin.

- [ ] **Step 2: Build docs locally and verify**

Verify all classes appear, doctests render as code examples, hierarchy is navigable.

- [ ] **Step 3: Add GitHub Actions workflow**

```yaml
# .github/workflows/docs.yml
name: Deploy Docs
on:
  push:
    branches: [main]
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install pdoc pydantic pywin32-stubs
      - run: pdoc src/sapguimcp/sapgui/ -o site/
      - uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./site
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/docs.yml
git commit -m "ci(pysapgui): add docs site deployment (#498)"
```

**Note:** This task completes in the standalone repo (#492). The workflow above is a template — adapt to the final repo structure.

---

## Phase 4: Testing

### Task 16: Unit test completeness audit (#488)

**Files:**
- Modify: all files in `unittests/sapgui/`

- [ ] **Step 1: Identify untested public methods**

For each component file, compare the public methods against existing test files. List any method that has zero test coverage.

Focus areas likely missing tests:
- `components/window.py` — `send_v_key()`, `hard_copy()`, `tab_forward()`, etc.
- `components/field.py` — label properties (color_index, char_height, etc.)
- `components/checkbox.py` — `GuiRadioButton` group properties
- `components/combobox.py` — `entries` property iteration
- `components/shell.py` — context menu methods, `GuiHTMLViewer`, `GuiToolbarControl`

- [ ] **Step 2: Write missing tests**

One test per public method minimum. Use the same `make_mock_com()` pattern from `conftest.py`.

- [ ] **Step 3: Run full suite and check coverage**

Run: `python -m pytest unittests/sapgui/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Run isort + black, then commit**

```bash
python -m isort unittests/sapgui/
python -m black unittests/sapgui/
git add unittests/sapgui/
git commit -m "test(pysapgui): complete unit test coverage audit (#488)"
```

---

### Task 17: Integration test infrastructure (#489)

**Files:**
- Modify: `unittests/sapgui/conftest.py`
- Create: `unittests/sapgui/test_integration.py` (if not exists — check first)

- [ ] **Step 1: Add pytest marker and skip logic**

In `conftest.py`, add or verify:

```python
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires SAP GUI and live system")

@pytest.fixture
def live_session():
    """Connect to running SAP GUI. Skip if not available."""
    try:
        from sapguimcp.sapgui import SapGui
        app = SapGui.connect()
        session = app.connections[0].sessions[0]
        return session
    except Exception:
        pytest.skip("SAP GUI not available")
```

- [ ] **Step 2: Add smoke test**

```python
@pytest.mark.integration
def test_connect_and_read_session_info(live_session):
    """Smoke test: connect to SAP GUI and read session info."""
    info = live_session.info
    assert info.system_name  # non-empty
    assert info.client  # non-empty
    assert info.user  # non-empty
```

- [ ] **Step 3: Commit**

```bash
git add unittests/sapgui/conftest.py unittests/sapgui/test_integration.py
git commit -m "test(pysapgui): add integration test infrastructure (#489)"
```

---

### Task 18: CI pipeline (#490)

**Files:**
- Create: `.github/workflows/pysapgui-ci.yml` (or add to existing workflow)

- [ ] **Step 1: Check existing CI workflows**

Read `.github/workflows/` to understand existing CI structure. The pysapgui CI should be a separate job or workflow that only runs sapgui tests.

- [ ] **Step 2: Create CI workflow**

```yaml
name: pysapgui CI

on:
  push:
    paths:
      - 'src/sapguimcp/sapgui/**'
      - 'unittests/sapgui/**'
  pull_request:
    paths:
      - 'src/sapguimcp/sapgui/**'
      - 'unittests/sapgui/**'

jobs:
  test:
    runs-on: windows-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: python -m pytest unittests/sapgui/ -v --tb=short -m "not integration"

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install ruff mypy
      - run: ruff check src/sapguimcp/sapgui/
      - run: mypy src/sapguimcp/sapgui/ --ignore-missing-imports
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/pysapgui-ci.yml
git commit -m "ci(pysapgui): add CI pipeline for lint, type-check, tests (#490)"
```

---

## Phase 5: Extraction & Packaging

### Task 19: Rename imports and create package alias (#491)

**Important:** Simply renaming `sapguimcp.sapgui` → `pysapgui` in import statements would cause ImportError because the package is still physically at `src/sapguimcp/sapgui/`. We need to do this together with creating the package path.

**Files:**
- Create: `src/pysapgui/` — the actual package directory (move files here)
- Modify: all internal imports (~91 occurrences)
- Create: `src/sapguimcp/sapgui/__init__.py` — compatibility shim re-exporting from `pysapgui`
- Modify: `unittests/sapgui/` — update test imports

- [ ] **Step 1: Inventory all imports**

Run: `grep -rn "sapguimcp.sapgui" src/sapguimcp/sapgui/ unittests/sapgui/`

- [ ] **Step 2: Move the package**

```bash
# Move sapgui source to top-level pysapgui package
cp -r src/sapguimcp/sapgui/ src/pysapgui/
```

- [ ] **Step 3: Rename all internal imports in src/pysapgui/**

Replace `sapguimcp.sapgui` → `pysapgui` in all files under `src/pysapgui/`.

Use find-and-replace (sed or IDE). ~91 occurrences across ~25 files.

- [ ] **Step 4: Create compatibility shim**

Replace `src/sapguimcp/sapgui/__init__.py` with a re-export shim so the desktop backend keeps working:

```python
"""Compatibility shim — pysapgui has moved to its own package.

This re-exports the public API so existing ``sapguimcp.sapgui`` imports
continue to work until the MCP server migrates to ``pysapgui``.
"""
from pysapgui import SapGui  # noqa: F401
from pysapgui import _com, _errors, _factory, _types, login, models  # noqa: F401
from pysapgui import components  # noqa: F401
```

- [ ] **Step 5: Update test imports**

Replace `sapguimcp.sapgui` → `pysapgui` in all files under `unittests/sapgui/`.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest unittests/ -v`
Expected: ALL PASS — both `pysapgui` imports (direct) and `sapguimcp.sapgui` imports (shim) resolve

- [ ] **Step 7: Commit**

```bash
git add src/pysapgui/ src/sapguimcp/sapgui/__init__.py unittests/sapgui/
git commit -m "refactor(pysapgui): move to standalone package with compat shim (#491)"
```

---

### Task 20: Extract to own repo (#492)

**Files:**
- Create: standalone `pyproject.toml`
- Create: `LICENSE` (MIT)
- Create: new GitHub repo

This task is done manually with the user. Key steps:

- [ ] **Step 1: Verify PyPI name availability**

Check if `pysapgui` is available on PyPI. The existing `PySapGUI` package (gutskodv) may conflict under PyPI name normalization. If taken, discuss alternative names.

- [ ] **Step 2: Create standalone pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pysapgui"
version = "0.1.0"
description = "Typed Python wrapper for the SAP GUI Scripting API"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
dependencies = [
    "pywin32>=306; sys_platform == 'win32'",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff",
    "mypy",
]
```

- [ ] **Step 3: Create new repo and push**

```bash
# Create repo on GitHub (Hochfrequenz/pysapgui)
# Use git filter-repo to extract history, or start fresh
git init pysapgui
# Copy files, push
```

- [ ] **Step 4: Update sapgui.mcp**

Replace bundled `sapgui/` with a `pysapgui` dependency:

```toml
# pyproject.toml
dependencies = [
    "pysapgui>=0.1.0",
    # ... rest
]
```

Update `src/sapguimcp/backend/desktop/__init__.py` imports from `sapguimcp.sapgui` → `pysapgui`.

- [ ] **Step 5: First PyPI release**

Set up GitHub Actions publish workflow in the new repo. Tag `v0.1.0` and publish.
