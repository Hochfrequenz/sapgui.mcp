# Full-Depth Element Tree with Comprehensive Attributes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture all SAP GUI COM properties in `ElementInfo`, remove depth limits from `dump_tree`, and add smart truncation with a `depth` parameter to MCP tools so the LLM knows when deeper elements exist and can request them.

**Architecture:** Two repos, two feature branches. sapsucker (library) extends `ElementInfo` and removes depth limits. sapguimcp (MCP server) installs sapsucker in dev mode, removes hardcoded `max_depth` values, adds `depth` parameter + truncation metadata to LLM-facing tools. Internal backend code always uses the full tree.

**Tech Stack:** Python 3.12, pydantic, SAP GUI Scripting COM (via sapsucker/pywin32), pytest

**Spec:** `docs/superpowers/specs/2026-04-05-full-depth-element-info-design.md`

**Dev setup:** `pip install -e C:/github/sapsucker` for fast iteration between repos.

---

## Part A: sapsucker changes (repo: `C:/github/sapsucker`, branch: `feat/full-element-info`)

### File Map

| File | Role | Change |
|------|------|--------|
| `src/sapsucker/models.py` | Data models | Add 13 new fields to `ElementInfo` |
| `src/sapsucker/components/base.py` | COM tree traversal | Read new props in `_dump_tree_recursive` and `_probe_bdt_fields`, default `max_depth=None` |
| `unittests/test_models.py` | Model tests | Add tests for new fields + backward compat |
| `unittests/test_base.py` | dump_tree tests | Add tests for new props in tree, unlimited depth |

---

### Task A1: Create feature branch in sapsucker

- [ ] **Step 1: Create branch from latest remote main**

```bash
cd C:/github/sapsucker
git fetch origin main && git checkout -b feat/full-element-info origin/main
```

- [ ] **Step 2: Verify tests pass on clean branch**

```bash
python -m pytest unittests/test_models.py unittests/test_base.py -v --tb=short
```

---

### Task A2: Extend `ElementInfo` with all COM properties

**Files:**
- Modify: `src/sapsucker/models.py`
- Modify: `unittests/test_models.py`

- [ ] **Step 1: Write test for new fields with defaults**

Append to `unittests/test_models.py` inside `class TestElementInfo`:

```python
    def test_new_fields_have_defaults(self):
        """Existing code creating ElementInfo with 6 fields still works."""
        elem = ElementInfo(
            id="x", type="GuiTextField", type_as_number=31,
            name="x", text="", changeable=False,
        )
        assert elem.tooltip == ""
        assert elem.default_tooltip == ""
        assert elem.icon_name == ""
        assert elem.modified is False
        assert elem.acc_text == ""
        assert elem.acc_tooltip == ""
        assert elem.acc_text_on_request == ""
        assert elem.height == 0
        assert elem.width == 0
        assert elem.left == 0
        assert elem.top == 0
        assert elem.screen_left == 0
        assert elem.screen_top == 0
        assert elem.is_symbol_font is False
        assert elem.container_type is False

    def test_new_fields_populated(self):
        """ElementInfo with all fields explicitly set."""
        elem = ElementInfo(
            id="btn", type="GuiButton", type_as_number=40,
            name="btn[0]", text="Save", changeable=True,
            tooltip="Save Document (Ctrl+S)", icon_name="ICON_SAVE",
            modified=False, height=25, width=80, left=10, top=5,
            screen_left=110, screen_top=205, is_symbol_font=False,
            acc_text="Save", acc_tooltip="Save Document",
            default_tooltip="Save", acc_text_on_request="",
            container_type=False,
        )
        assert elem.tooltip == "Save Document (Ctrl+S)"
        assert elem.icon_name == "ICON_SAVE"
        assert elem.height == 25
        assert elem.screen_left == 110
        assert elem.container_type is False

    def test_serialization_includes_new_fields(self):
        elem = ElementInfo(
            id="x", type="GuiButton", type_as_number=40,
            name="x", text="", changeable=True,
            tooltip="Weiter (Enter)", icon_name="B_OKAY",
        )
        d = elem.model_dump()
        assert d["tooltip"] == "Weiter (Enter)"
        assert d["icon_name"] == "B_OKAY"
        restored = ElementInfo.model_validate(d)
        assert restored.tooltip == "Weiter (Enter)"
```

- [ ] **Step 2: Run tests — should fail (fields don't exist)**

```bash
python -m pytest unittests/test_models.py -v -k "new_fields or serialization_includes"
```

- [ ] **Step 3: Add new fields to `ElementInfo`**

In `src/sapsucker/models.py`, extend the class:

```python
class ElementInfo(BaseModel):
    """Structured information about a SAP GUI element and its children."""

    id: str
    type: str
    type_as_number: int
    name: str
    text: str
    changeable: bool
    children: list[ElementInfo] = []

    # Extended properties (all have safe defaults for backward compatibility)
    tooltip: str = ""
    default_tooltip: str = ""
    icon_name: str = ""
    modified: bool = False
    acc_text: str = ""
    acc_tooltip: str = ""
    acc_text_on_request: str = ""
    height: int = 0
    width: int = 0
    left: int = 0
    top: int = 0
    screen_left: int = 0
    screen_top: int = 0
    is_symbol_font: bool = False
    container_type: bool = False
```

- [ ] **Step 4: Run tests — should pass**

```bash
python -m pytest unittests/test_models.py -v
```

- [ ] **Step 5: Run all existing tests for backward compat**

```bash
python -m pytest unittests/ -k "not integration" -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add src/sapsucker/models.py unittests/test_models.py
git commit -m "feat: extend ElementInfo with all COM properties (13 new fields)"
```

---

### Task A3: Read new properties in `_dump_tree_recursive` and `_probe_bdt_fields`

**Files:**
- Modify: `src/sapsucker/components/base.py`
- Modify: `unittests/test_base.py`

- [ ] **Step 1: Write test for new properties in dump_tree output**

Append to `unittests/test_base.py` inside `class TestDumpTree`:

```python
    def test_captures_tooltip_and_icon(self):
        """dump_tree reads tooltip, icon_name, and other new properties."""
        child = make_mock_com(
            type_as_number=40, type_name="GuiButton",
            id="btn", name="btn[0]", text="",
            tooltip="Weiter (Enter)", icon_name="B_OKAY",
            modified=False, height=25, width=80,
            container_type=False,
        )
        parent = make_mock_com(container_type=True, children=[child])
        vc = GuiVContainer(parent)
        result = vc.dump_tree()
        assert len(result) == 1
        assert result[0].tooltip == "Weiter (Enter)"
        assert result[0].icon_name == "B_OKAY"
        assert result[0].height == 25
        assert result[0].width == 80
        assert result[0].container_type is False

    def test_safe_fallback_on_missing_property(self):
        """If a COM object lacks a new property, the default is used."""
        child = make_mock_com(
            type_as_number=31, type_name="GuiTextField",
            id="txt", name="txtF", text="hello",
            container_type=False,
        )
        # Remove Tooltip property to simulate missing COM attr
        del child.Tooltip
        parent = make_mock_com(container_type=True, children=[child])
        vc = GuiVContainer(parent)
        result = vc.dump_tree()
        assert result[0].tooltip == ""  # Falls back to default
        assert result[0].text == "hello"  # Existing props still work
```

- [ ] **Step 2: Run tests — should fail (dump_tree doesn't read new props)**

```bash
python -m pytest unittests/test_base.py -v -k "tooltip_and_icon or missing_property"
```

- [ ] **Step 3: Update `_dump_tree_recursive` to read all properties**

In `src/sapsucker/components/base.py`, update the `ElementInfo` construction
inside `_dump_tree_recursive` (lines 273-286):

```python
            child_info = ElementInfo(
                id=str(_safe_com_attr(child, "Id", "")),
                type=str(_safe_com_attr(child, "Type", "")),
                type_as_number=int(_safe_com_attr(child, "TypeAsNumber", 0)),
                name=str(_safe_com_attr(child, "Name", "")),
                text=str(_safe_com_attr(child, "Text", "")),
                changeable=bool(_safe_com_attr(child, "Changeable", False)),
                tooltip=str(_safe_com_attr(child, "Tooltip", "")),
                default_tooltip=str(_safe_com_attr(child, "DefaultTooltip", "")),
                icon_name=str(_safe_com_attr(child, "IconName", "")),
                modified=bool(_safe_com_attr(child, "Modified", False)),
                acc_text=str(_safe_com_attr(child, "AccText", "")),
                acc_tooltip=str(_safe_com_attr(child, "AccTooltip", "")),
                acc_text_on_request=str(_safe_com_attr(child, "AccTextOnRequest", "")),
                height=int(_safe_com_attr(child, "Height", 0)),
                width=int(_safe_com_attr(child, "Width", 0)),
                left=int(_safe_com_attr(child, "Left", 0)),
                top=int(_safe_com_attr(child, "Top", 0)),
                screen_left=int(_safe_com_attr(child, "ScreenLeft", 0)),
                screen_top=int(_safe_com_attr(child, "ScreenTop", 0)),
                is_symbol_font=bool(_safe_com_attr(child, "IsSymbolFont", False)),
                container_type=bool(_safe_com_attr(child, "ContainerType", False)),
                children=(
                    _dump_tree_recursive(child, depth + 1, max_depth)
                    if depth + 1 < max_depth and _safe_com_attr(child, "ContainerType", False)
                    else []
                ),
            )
```

Apply the same pattern to `_probe_bdt_fields` (lines 240-249):

```python
                result.append(
                    ElementInfo(
                        id=child_id,
                        type=str(_safe_com_attr(child, "Type", "")),
                        type_as_number=int(_safe_com_attr(child, "TypeAsNumber", 0)),
                        name=str(_safe_com_attr(child, "Name", "")),
                        text=str(_safe_com_attr(child, "Text", "")),
                        changeable=bool(_safe_com_attr(child, "Changeable", False)),
                        tooltip=str(_safe_com_attr(child, "Tooltip", "")),
                        default_tooltip=str(_safe_com_attr(child, "DefaultTooltip", "")),
                        icon_name=str(_safe_com_attr(child, "IconName", "")),
                        modified=bool(_safe_com_attr(child, "Modified", False)),
                        acc_text=str(_safe_com_attr(child, "AccText", "")),
                        acc_tooltip=str(_safe_com_attr(child, "AccTooltip", "")),
                        acc_text_on_request=str(_safe_com_attr(child, "AccTextOnRequest", "")),
                        height=int(_safe_com_attr(child, "Height", 0)),
                        width=int(_safe_com_attr(child, "Width", 0)),
                        left=int(_safe_com_attr(child, "Left", 0)),
                        top=int(_safe_com_attr(child, "Top", 0)),
                        screen_left=int(_safe_com_attr(child, "ScreenLeft", 0)),
                        screen_top=int(_safe_com_attr(child, "ScreenTop", 0)),
                        is_symbol_font=bool(_safe_com_attr(child, "IsSymbolFont", False)),
                        container_type=bool(_safe_com_attr(child, "ContainerType", False)),
                        children=[],
                    )
                )
```

**DRY opportunity:** Extract a helper `_build_element_info(child, children)` to avoid the duplication. Both call sites use the same property reads.

- [ ] **Step 4: Run tests — should pass**

```bash
python -m pytest unittests/test_base.py -v -k "TestDumpTree"
```

- [ ] **Step 5: Run all tests**

```bash
python -m pytest unittests/ -k "not integration" -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add src/sapsucker/components/base.py unittests/test_base.py
git commit -m "feat: read all COM properties in dump_tree and BDT probe"
```

---

### Task A4: Default `max_depth=None` (unlimited) with safety cap

**Files:**
- Modify: `src/sapsucker/components/base.py`
- Modify: `unittests/test_base.py`

- [ ] **Step 1: Write test for unlimited depth**

Append to `unittests/test_base.py` inside `class TestDumpTree`:

```python
    def test_unlimited_depth_default(self):
        """dump_tree() with no args traverses full depth."""
        gc = make_mock_com(type_as_number=31, id="gc", name="gc", container_type=False)
        child = make_mock_com(type_as_number=74, id="c", name="c", container_type=True, children=[gc])
        parent = make_mock_com(container_type=True, children=[child])
        vc = GuiVContainer(parent)
        result = vc.dump_tree()  # No max_depth arg
        assert len(result) == 1
        assert len(result[0].children) == 1
        assert result[0].children[0].id == "gc"

    def test_explicit_max_depth_still_works(self):
        """Backward compat: dump_tree(max_depth=1) still limits depth."""
        gc = make_mock_com(type_as_number=31, id="gc", name="gc", container_type=False)
        child = make_mock_com(type_as_number=74, id="c", name="c", container_type=True, children=[gc])
        parent = make_mock_com(container_type=True, children=[child])
        vc = GuiVContainer(parent)
        result = vc.dump_tree(max_depth=1)
        assert len(result) == 1
        assert result[0].children == []  # Truncated at depth 1
```

- [ ] **Step 2: Run tests — unlimited test may already pass (default=20 is deep enough for mock)**

```bash
python -m pytest unittests/test_base.py -v -k "unlimited_depth or explicit_max_depth"
```

- [ ] **Step 3: Change `dump_tree` signature and recursion logic**

In `src/sapsucker/components/base.py`:

Update `dump_tree` (line ~299):
```python
    def dump_tree(self, max_depth: int | None = None) -> list[ElementInfo]:
        """Return a recursive tree of ElementInfo for all children.

        Args:
            max_depth: Maximum recursion depth. None means unlimited (with a
                       hard safety cap of 200 to prevent infinite recursion).
        """
        effective_depth = max_depth if max_depth is not None else 200
        return _dump_tree_recursive(self._com, 0, effective_depth)
```

- [ ] **Step 4: Run all dump_tree tests**

```bash
python -m pytest unittests/test_base.py -v -k "TestDumpTree"
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest unittests/ -k "not integration" -v --tb=short
```

- [ ] **Step 6: Format and commit**

```bash
python -m isort src/ unittests/ && python -m black src/ unittests/
git add src/sapsucker/components/base.py unittests/test_base.py
git commit -m "feat: default dump_tree to unlimited depth with 200 safety cap"
```

---

### Task A5: Push sapsucker branch, run CI

- [ ] **Step 1: Push**

```bash
cd C:/github/sapsucker
git push -u origin feat/full-element-info
```

- [ ] **Step 2: Verify CI passes**

```bash
gh pr create --title "feat: comprehensive ElementInfo + unlimited dump_tree depth" --draft
gh pr checks <PR_NUMBER>
```

---

## Part B: sapguimcp changes (repo: `C:/github/sapgui.mcp`, branch: `feat/full-depth-tree`)

### Prerequisites

Install sapsucker dev mode:
```bash
cd C:/github/sapgui.mcp
pip install -e C:/github/sapsucker
```

### File Map

| File | Role | Change |
|------|------|--------|
| `backend/desktop/__init__.py` | Desktop backend | Remove `max_depth` args, remove tooltip workaround, use `elem.tooltip` |
| `backend/desktop/_truncation.py` | New: truncation helper | `truncate_tree()` + `compute_tree_depth()` |
| `tools/sap_tools.py` | MCP tools | Add `depth` param to 3 tools, remove 1 `max_depth` arg |
| `tools/com_tools.py` | COM snapshot tool | Add `depth` param to `sap_com_snapshot` |
| `tools/se24_edit_tools.py` | SE24 editor | Remove 1 `max_depth` arg |
| `tools/table_helpers.py` | Table helper | Remove 1 `max_depth` arg |
| `models/sap_results.py` | Result models | Add truncation metadata fields |
| `unittests/desktop/test_truncation_unit.py` | New: truncation tests | Unit tests for truncate_tree |

---

### Task B1: Create feature branch and install sapsucker dev mode

- [ ] **Step 1: Create branch**

```bash
cd C:/github/sapgui.mcp
git fetch origin main && git checkout -b feat/full-depth-tree origin/main
```

- [ ] **Step 2: Install sapsucker in dev mode**

```bash
pip install -e C:/github/sapsucker
```

- [ ] **Step 3: Verify new fields are available**

```bash
python -c "from sapsucker.models import ElementInfo; e = ElementInfo(id='x', type='t', type_as_number=0, name='n', text='', changeable=False); print(e.tooltip, e.icon_name)"
```

Expected: ` ` (two empty strings)

---

### Task B2: Create truncation helper

**Files:**
- Create: `src/sapguimcp/backend/desktop/_truncation.py`
- Create: `unittests/desktop/test_truncation_unit.py`

- [ ] **Step 1: Write tests**

```python
"""Unit tests for tree truncation helper."""
from __future__ import annotations

from sapsucker.models import ElementInfo

from sapguimcp.backend.desktop._truncation import compute_tree_depth, truncate_tree


def _elem(id: str, children: list | None = None) -> ElementInfo:
    return ElementInfo(
        id=id, type="GuiTextField", type_as_number=31,
        name=id, text="", changeable=False,
        children=children or [],
    )


def test_flat_tree_no_truncation():
    tree = [_elem("a"), _elem("b")]
    result, max_depth, hidden = truncate_tree(tree, depth=5)
    assert len(result) == 2
    assert max_depth == 1
    assert hidden == 0


def test_truncation_at_depth_1():
    tree = [_elem("a", children=[_elem("a1"), _elem("a2")])]
    result, max_depth, hidden = truncate_tree(tree, depth=1)
    assert len(result) == 1
    assert result[0].children == []
    assert max_depth == 2
    assert hidden == 2


def test_truncation_preserves_shallow_children():
    tree = [_elem("a", children=[_elem("a1", children=[_elem("a1a")])])]
    result, max_depth, hidden = truncate_tree(tree, depth=2)
    assert len(result[0].children) == 1
    assert result[0].children[0].children == []
    assert max_depth == 3
    assert hidden == 1


def test_no_truncation_when_depth_exceeds_tree():
    tree = [_elem("a", children=[_elem("a1")])]
    result, max_depth, hidden = truncate_tree(tree, depth=99)
    assert len(result[0].children) == 1
    assert max_depth == 2
    assert hidden == 0


def test_compute_tree_depth_empty():
    assert compute_tree_depth([]) == 0


def test_compute_tree_depth_nested():
    tree = [_elem("a", children=[_elem("b", children=[_elem("c")])])]
    assert compute_tree_depth(tree) == 3
```

- [ ] **Step 2: Run tests — should fail (module doesn't exist)**

```bash
python -m pytest unittests/desktop/test_truncation_unit.py -v
```

- [ ] **Step 3: Implement truncation helper**

Create `src/sapguimcp/backend/desktop/_truncation.py`:

```python
"""Tree truncation for LLM-facing tool responses.

Internal backend code always operates on the full tree. This module
provides helpers to truncate the tree to a given depth for tool results,
while reporting how much was hidden.
"""

from __future__ import annotations

from sapsucker.models import ElementInfo


def compute_tree_depth(tree: list[ElementInfo]) -> int:
    """Return the maximum depth of the tree (1-indexed, 0 if empty)."""
    if not tree:
        return 0
    max_child = 0
    for elem in tree:
        if elem.children:
            max_child = max(max_child, compute_tree_depth(elem.children))
    return 1 + max_child


def truncate_tree(
    tree: list[ElementInfo], depth: int
) -> tuple[list[ElementInfo], int, int]:
    """Truncate a full tree to a given depth.

    Returns:
        (truncated_tree, max_depth_found, elements_hidden)
        - truncated_tree: copy with children beyond depth replaced by []
        - max_depth_found: deepest level in the original tree
        - elements_hidden: total elements beyond the cutoff
    """
    max_depth_found = compute_tree_depth(tree)
    hidden = [0]  # Mutable counter for nested function

    def _truncate(nodes: list[ElementInfo], current_depth: int) -> list[ElementInfo]:
        result = []
        for elem in nodes:
            if current_depth >= depth:
                # Count this element and all descendants as hidden
                hidden[0] += _count_all(elem)
                continue
            truncated_children = (
                _truncate(elem.children, current_depth + 1)
                if elem.children
                else []
            )
            result.append(elem.model_copy(update={"children": truncated_children}))
        return result

    truncated = _truncate(tree, 0)
    return truncated, max_depth_found, hidden[0]


def _count_all(elem: ElementInfo) -> int:
    """Count an element and all its descendants."""
    total = 1
    for child in elem.children:
        total += _count_all(child)
    return total
```

- [ ] **Step 4: Run tests — should pass**

```bash
python -m pytest unittests/desktop/test_truncation_unit.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/desktop/_truncation.py unittests/desktop/test_truncation_unit.py
git commit -m "feat: add tree truncation helper for LLM-facing tool responses"
```

---

### Task B3: Remove all hardcoded `max_depth` values

**Files:**
- Modify: `src/sapguimcp/backend/desktop/__init__.py` (2 locations)
- Modify: `src/sapguimcp/tools/sap_tools.py` (1 location)
- Modify: `src/sapguimcp/tools/se24_edit_tools.py` (1 location)
- Modify: `src/sapguimcp/tools/table_helpers.py` (1 location)

- [ ] **Step 1: Find and remove all explicit `max_depth` args**

Search for `max_depth` in the codebase:

```bash
grep -rn "max_depth" src/sapguimcp/ --include="*.py"
```

Remove the `max_depth=N` argument from each `dump_tree()` call:

1. `backend/desktop/__init__.py`: `dump_tree(max_depth=2)` in `check_popup` → `dump_tree()`
2. `backend/desktop/__init__.py`: `dump_tree(max_depth=2)` in `dismiss_popup` → `dump_tree()`
3. `tools/sap_tools.py`: `dump_tree(max_depth=3)` in `_get_button_tooltips_desktop` → `dump_tree()`
4. `tools/se24_edit_tools.py`: `dump_tree(max_depth=8)` → `dump_tree()`
5. `tools/table_helpers.py`: `dump_tree(max_depth=8)` → `dump_tree()`

- [ ] **Step 2: Remove tooltip workaround in `discover_buttons` and `check_popup`**

In `backend/desktop/__init__.py`, the tooltip fallback code (from PR #614)
now becomes unnecessary — `elem.tooltip` is available directly.

In `discover_buttons` (~lines 654-666), replace the tooltip workaround:
```python
            for elem in _flatten(tree):
                if elem.type_as_number != 40:
                    continue
                label = elem.text.strip()
                if not label:
                    label = elem.tooltip.strip()
                if label:
                    buttons.append({"label": label, "id": elem.id, "selector": elem.id})
```

Same in `check_popup` (~lines 1369-1383).

- [ ] **Step 3: Run existing integration tests**

```bash
python -m pytest unittests/desktop/test_popup_rework_unit.py unittests/desktop/test_popup_rework_exploration.py -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "feat: remove all hardcoded max_depth values, simplify tooltip fallback"
```

---

### Task B4: Add `depth` parameter to MCP tools

**Files:**
- Modify: `src/sapguimcp/tools/sap_tools.py`
- Modify: `src/sapguimcp/tools/com_tools.py`
- Modify: `src/sapguimcp/backend/desktop/__init__.py`
- Modify: `src/sapguimcp/models/sap_results.py`

- [ ] **Step 1: Add truncation metadata to result models**

In `models/sap_results.py`, add to `DiscoveredFields`, `DiscoveredButtons`,
`FormFieldsResult`, and `ComSnapshotResult`:

```python
    depth_shown: int | None = Field(default=None, description="Tree depth shown in this response")
    max_depth_found: int | None = Field(default=None, description="Maximum depth in the full tree")
    elements_hidden: int | None = Field(default=None, description="Elements beyond depth cutoff not shown")
```

- [ ] **Step 2: Add `depth` param to `sap_discover_fields`**

In `tools/sap_tools.py`, add `depth: int = 3` parameter. After getting fields
from backend, compute truncation metadata using the full tree. The field
discovery already flattens the tree, so truncation applies to the snapshot/tree
output, not the field list itself.

For field/button discovery, `depth` controls how deep in the GUI tree we search.
The backend always searches the full tree. The `depth` parameter is reported back
so the LLM knows if there are deeper elements.

```python
    async def sap_discover_fields(
        depth: int = Field(default=3, ge=1, description="Tree depth to search"),
        session: str | None = None,
        agent_id: str | None = None,
    ) -> DiscoveredFields:
```

After getting fields from `backend.discover_fields()`, add truncation metadata:
```python
    from sapguimcp.backend.desktop._truncation import compute_tree_depth
    # The backend searched full depth; report how deep the tree goes
    # (actual truncation only matters for snapshot/tree tools)
```

- [ ] **Step 3: Add `depth` param to `sap_com_snapshot`**

In `tools/com_tools.py`, add `depth: int = 3` parameter. Thread it through to
`backend.get_snapshot(depth=depth)`.

Update `get_snapshot` in `backend/desktop/__init__.py` to accept `depth`:
```python
    async def get_snapshot(self, depth: int | None = None) -> ComTreeSnapshot:
```
When `depth` is provided, truncate the tree before formatting as text. Append
a summary line: `"--- N elements at depth 4-7 not shown. Use depth=7 to see all. ---"`

- [ ] **Step 4: Run tests**

```bash
python -m pytest unittests/desktop/ -k "not integration" -v --tb=short
```

- [ ] **Step 5: Format and commit**

```bash
python -m isort src/ unittests/ && python -m black src/ unittests/
git add -u && git add src/sapguimcp/backend/desktop/_truncation.py unittests/desktop/test_truncation_unit.py
git commit -m "feat: add depth parameter to MCP tools with truncation metadata"
```

---

### Task B5: Integration testing and regression check

- [ ] **Step 1: Run live integration tests**

```bash
python -m pytest unittests/desktop/test_popup_rework_exploration.py -v -s --tb=short
python -m pytest unittests/desktop/test_bp_integration.py -v --tb=short
```

- [ ] **Step 2: Run linting**

```bash
tox -e linting
```

- [ ] **Step 3: Run all unit tests**

```bash
python -m pytest unittests/ -k "not integration and not exploration" -q --tb=line
```

- [ ] **Step 4: Push and create PR**

```bash
git push -u origin feat/full-depth-tree
gh pr create --title "feat: full-depth element tree with comprehensive attributes" \
  --body "Depends on sapsucker feat/full-element-info branch."
```
