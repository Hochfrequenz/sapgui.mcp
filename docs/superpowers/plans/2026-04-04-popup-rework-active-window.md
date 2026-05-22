# Popup Rework: Active Window Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all desktop backend tools operate on the topmost SAP GUI window (`wnd[0]`, `wnd[1]`, `wnd[2]`...) instead of hardcoding `wnd[0]`, and remove the popup-blocking gates in the tool layer so modal dialogs become normal interaction targets.

**Architecture:** A new `_active_window_id(session)` helper detects the topmost open window. All backend methods and element-finder functions gain a `wnd_id` parameter that defaults to the active window. The tool layer stops treating popups as blockers for the desktop backend. A new `active_window` field on `ToolResult` tells the agent which window was used.

**Tech Stack:** Python 3.12, pydantic, SAP GUI Scripting COM API (via sapsucker), pytest + anyio

**Spec:** `docs/superpowers/specs/2026-04-04-popup-rework-active-window-design.md`

---

## File Map

| File | Role | Change |
|------|------|--------|
| `src/sapguimcp/backend/desktop/__init__.py` | Desktop backend | Add `_active_window_id()`, update ~15 methods to use it |
| `src/sapguimcp/backend/desktop/_element_finder.py` | Label→COM resolution | Add `wnd_id` param to 8 public functions |
| `src/sapguimcp/models/base.py` | Result base class | Add `active_window` field to `ToolResult` |
| `src/sapguimcp/tools/sap_tools.py` | MCP tool layer | Remove 9 popup-blocking checks (desktop only), populate `active_window` |
| `src/sapguimcp/tools/abapgit_tools.py` | abapGit pull | Update `_check_for_error_popup_desktop()` |
| `src/sapguimcp/data/sap_knowledge.md` | Agent instructions | Add active window guidance |
| `unittests/desktop/test_popup_rework_unit.py` | Unit tests | New: `_active_window_id`, element finder `wnd_id` |
| `unittests/desktop/test_popup_rework_exploration.py` | Integration tests | Flip assertions, add new tests |

---

### Task 1: Add `_active_window_id()` helper + unit tests

**Files:**
- Modify: `src/sapguimcp/backend/desktop/__init__.py` (top of file, after imports)
- Create: `unittests/desktop/test_popup_rework_unit.py`

- [ ] **Step 1: Write the unit test**

In `unittests/desktop/test_popup_rework_unit.py`:

```python
"""Unit tests for active window detection and element finder wnd_id support."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_session(*, has_wnd1: bool = False, has_wnd2: bool = False, has_wnd3: bool = False) -> MagicMock:
    """Create a mock session with configurable open windows."""
    session = MagicMock()
    windows = {"wnd[0]": MagicMock()}
    if has_wnd1:
        windows["wnd[1]"] = MagicMock()
    if has_wnd2:
        windows["wnd[2]"] = MagicMock()
    if has_wnd3:
        windows["wnd[3]"] = MagicMock()

    def find_by_id(element_id: str, raise_error: bool = True):
        result = windows.get(element_id)
        if result is None and raise_error:
            raise Exception(f"Element not found: {element_id}")
        return result

    session.find_by_id = find_by_id
    return session


def test_active_window_no_popup():
    from sapguimcp.backend.desktop import _active_window_id

    session = _make_session()
    assert _active_window_id(session) == "wnd[0]"


def test_active_window_wnd1():
    from sapguimcp.backend.desktop import _active_window_id

    session = _make_session(has_wnd1=True)
    assert _active_window_id(session) == "wnd[1]"


def test_active_window_wnd2():
    from sapguimcp.backend.desktop import _active_window_id

    session = _make_session(has_wnd1=True, has_wnd2=True)
    assert _active_window_id(session) == "wnd[2]"


def test_active_window_wnd3():
    from sapguimcp.backend.desktop import _active_window_id

    session = _make_session(has_wnd1=True, has_wnd2=True, has_wnd3=True)
    assert _active_window_id(session) == "wnd[3]"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest unittests/desktop/test_popup_rework_unit.py -v -k "active_window"
```

Expected: `ImportError` — `_active_window_id` doesn't exist yet.

- [ ] **Step 3: Implement `_active_window_id`**

In `src/sapguimcp/backend/desktop/__init__.py`, add after the `_flatten` function (around line 43) and before the `DesktopBackend` class:

```python
def _active_window_id(session: Any) -> str:
    """Return the element ID of the topmost open window.

    SAP GUI enforces strict modal stacking: wnd[2] cannot exist without wnd[1].
    We scan top-down to find the highest existing window.
    """
    for i in (3, 2, 1):
        if session.find_by_id(f"wnd[{i}]", raise_error=False) is not None:
            return f"wnd[{i}]"
    return "wnd[0]"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest unittests/desktop/test_popup_rework_unit.py -v -k "active_window"
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/desktop/__init__.py unittests/desktop/test_popup_rework_unit.py
git commit -m "feat: add _active_window_id() helper for topmost window detection"
```

---

### Task 2: Add `wnd_id` parameter to element finder functions + unit tests

**Files:**
- Modify: `src/sapguimcp/backend/desktop/_element_finder.py`
- Modify: `unittests/desktop/test_popup_rework_unit.py`

The element finder has 8 public functions that hardcode `wnd[0]`. Each gains an
optional `wnd_id: str = "wnd[0]"` parameter. The default preserves backward
compatibility so callers that don't pass it continue to work.

- [ ] **Step 1: Write unit tests for `wnd_id` parameter**

Append to `unittests/desktop/test_popup_rework_unit.py`:

```python
# ---- Element finder wnd_id tests ----


def _make_element(*, id: str, type_as_number: int, text: str, name: str, changeable: bool = True):
    """Create a mock ElementInfo."""
    elem = MagicMock()
    elem.id = id
    elem.type_as_number = type_as_number
    elem.text = text
    elem.name = name
    elem.changeable = changeable
    elem.children = []
    return elem


def test_extract_container_path_wnd1():
    from sapguimcp.backend.desktop._element_finder import _extract_container_path

    assert _extract_container_path("/app/con[0]/ses[0]/wnd[1]/usr/lblFOO") == "wnd[1]/usr/"


def test_extract_container_path_fallback_uses_param():
    from sapguimcp.backend.desktop._element_finder import _extract_container_path

    # When no wnd[ is found in the ID, fallback should use the wnd_id param
    assert _extract_container_path("some/weird/path", wnd_id="wnd[1]") == "wnd[1]/usr/"


def test_find_by_name_prefix_wnd1():
    from sapguimcp.backend.desktop._element_finder import _find_by_name_prefix

    session = MagicMock()
    field_mock = MagicMock()
    session.find_by_id = MagicMock(side_effect=lambda eid, raise_error=True: field_mock if eid == "wnd[1]/usr/txtFOO" else None)
    result = _find_by_name_prefix(session, "FOO", path_prefix="wnd[1]/usr/")
    assert result is field_mock


def test_find_button_by_label_wnd1():
    from sapguimcp.backend.desktop._element_finder import find_button_by_label

    session = MagicMock()
    btn_elem = _make_element(id="/app/con[0]/ses[0]/wnd[1]/tbar[0]/btn[0]", type_as_number=40, text="Save", name="btn[0]")
    wnd1_mock = MagicMock()
    wnd1_mock.dump_tree.return_value = [btn_elem]
    btn_com = MagicMock()

    def find_by_id(eid, raise_error=True):
        if eid == "wnd[1]":
            return wnd1_mock
        if eid == btn_elem.id:
            return btn_com
        return None

    session.find_by_id = find_by_id
    result = find_button_by_label(session, "Save", wnd_id="wnd[1]")
    assert result is btn_com
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest unittests/desktop/test_popup_rework_unit.py -v -k "wnd1 or wnd_id or container_path"
```

Expected: FAIL — functions don't accept `wnd_id` yet.

- [ ] **Step 3: Add `wnd_id` parameter to all element finder functions**

In `src/sapguimcp/backend/desktop/_element_finder.py`, update each function:

1. `_extract_container_path(label_id, wnd_id="wnd[0]")` — change fallback from `"wnd[0]/usr/"` to `f"{wnd_id}/usr/"`
2. `_find_by_name_prefix(session, label_name, path_prefix="wnd[0]/usr/")` — no signature change needed (callers pass the prefix). But update the docstring.
3. `_find_by_label_text(session, label, wnd_id="wnd[0]")` — change `session.find_by_id("wnd[0]/usr")` to `session.find_by_id(f"{wnd_id}/usr")`. Pass `wnd_id` to `_extract_container_path`.
4. `_find_by_readonly_textfield_label(session, label, wnd_id="wnd[0]")` — same pattern
5. `_find_by_sap_name(session, label, wnd_id="wnd[0]")` — change `session.find_by_id("wnd[0]/usr")` to `session.find_by_id(f"{wnd_id}/usr")`
6. `find_field_by_label(session, label, wnd_id="wnd[0]")` — pass `wnd_id` to all sub-strategies. For strategy 1 (`_find_by_name_prefix`), pass `path_prefix=f"{wnd_id}/usr/"`.
7. `find_button_by_label(session, label, wnd_id="wnd[0]")` — change `session.find_by_id("wnd[0]")` to `session.find_by_id(wnd_id)`
8. `find_checkbox_by_label(session, label, wnd_id="wnd[0]")` — change `session.find_by_id("wnd[0]/usr")` to `session.find_by_id(f"{wnd_id}/usr")`
9. `find_radio_by_label(session, label, wnd_id="wnd[0]")` — same pattern
10. `find_tab_by_label(session, label, wnd_id="wnd[0]")` — change `session.find_by_id("wnd[0]")` to `session.find_by_id(wnd_id)`
11. `find_combobox_by_label(session, label, wnd_id="wnd[0]")` — change `session.find_by_id("wnd[0]/usr")` to `session.find_by_id(f"{wnd_id}/usr")`

Every change follows the same pattern: replace the hardcoded `"wnd[0]"` string with the `wnd_id` parameter.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest unittests/desktop/test_popup_rework_unit.py -v
```

Expected: All PASSED

- [ ] **Step 5: Run existing element finder unit tests to verify no regression**

```bash
python -m pytest unittests/desktop/test_discover_fields_unit.py -v
```

Expected: All existing tests still pass (they don't pass `wnd_id`, so defaults to `"wnd[0]"`).

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/backend/desktop/_element_finder.py unittests/desktop/test_popup_rework_unit.py
git commit -m "feat: add wnd_id parameter to all element finder functions"
```

---

### Task 3: Update desktop backend methods to use active window

**Files:**
- Modify: `src/sapguimcp/backend/desktop/__init__.py`

Every method that currently hardcodes `wnd[0]` must call `_active_window_id(session)` and use the result. This is a mechanical change across ~15 methods.

- [ ] **Step 1: Write integration test that will pass after the change**

In `unittests/desktop/test_popup_rework_exploration.py`, update `test_02_se21_trigger_popup` — flip the bug-documenting assertions at the end:

```python
    # After the fix: tools should see popup fields
    assert len(form2.fields) > 0, "get_form_fields should see wnd[1] fields after fix"
    assert len(fields2) > 0, "discover_fields should see wnd[1] fields after fix"
```

Also add a new test:

```python
@skip_no_sap
@pytest.mark.anyio
async def test_05_snapshot_shows_active_window(backend):
    """After fix: get_snapshot shows wnd[1] when popup is open."""
    await backend.enter_transaction("SE21")
    await backend.wait_for_ready()

    form = await backend.get_form_fields()
    text_fields = [f for f in form.fields if str(f.field_type) == "text"]
    await backend.fill_form({text_fields[0].label: "ZTEST_POPUP_XYZ99"})
    await backend.wait(300)
    await backend.press_key("F5")
    await backend.wait(500)

    snapshot = await backend.get_snapshot()
    snapshot_text = str(snapshot)
    # Snapshot should now contain wnd[1] elements
    assert "wnd[1]" in snapshot_text, "Snapshot should show wnd[1] when popup is open"
```

- [ ] **Step 2: Run the new test to confirm it fails**

```bash
python -m pytest "unittests/desktop/test_popup_rework_exploration.py::test_05_snapshot_shows_active_window" -v -s
```

Expected: FAIL — snapshot still only shows wnd[0].

- [ ] **Step 3: Update all methods in `__init__.py`**

In each method, add `wnd_id = _active_window_id(session)` at the top of the COM lambda, then replace `"wnd[0]"` references:

**Methods to update** (line numbers from current file):

1. `get_status_bar()` (~488): `session.find_by_id("wnd[0]/sbar")` → `session.find_by_id(f"{wnd_id}/sbar")`
2. `get_screen_info()` (~502): `session.find_by_id("wnd[0]")` → `session.find_by_id(wnd_id)`
3. `get_screen_text()` (~520-522): both `wnd[0]` and `wnd[0]/sbar`
4. `discover_fields()` (~559): `session.find_by_id("wnd[0]/usr")` → `session.find_by_id(f"{wnd_id}/usr")`
5. `get_form_fields()` (~574): same pattern
6. `discover_buttons()` (~630): `session.find_by_id("wnd[0]")` → `session.find_by_id(wnd_id)`
7. `get_snapshot()` (~652): `session.find_by_id("wnd[0]")` → `session.find_by_id(wnd_id)`
8. `take_screenshot()` (~668): `session.find_by_id("wnd[0]")` → `session.find_by_id(wnd_id)`
9. `get_page_title()` (~802): `session.find_by_id("wnd[0]")` → `session.find_by_id(wnd_id)`
10. `press_key()` (~815-818): all three `wnd[0]` references
11. `fill_field()` (~849): `find_field_by_label(session, label)` → `find_field_by_label(session, label, wnd_id=wnd_id)`
12. `fill_main_input()` (~863): same — pass `wnd_id`
13. `fill_form()` (~884): same — pass `wnd_id` to `find_field_by_label`
14. `fill_grid_cell()` (~922): `session.find_by_id("wnd[0]/usr")` → `session.find_by_id(f"{wnd_id}/usr")`
15. `click_button()` (~944): `find_button_by_label(session, label)` → `find_button_by_label(session, label, wnd_id=wnd_id)`
16. `click_tab()` (~957): `find_tab_by_label(session, label)` → `find_tab_by_label(session, label, wnd_id=wnd_id)`
17. `type_text()` (~970): `session.find_by_id("wnd[0]")` → `session.find_by_id(wnd_id)`
18. `set_checkbox()` (~985): `find_checkbox_by_label(session, label)` → add `wnd_id=wnd_id`
19. `set_radio_button()` (~998): `find_radio_by_label(session, label)` → add `wnd_id=wnd_id`
20. `select_dropdown()` (~1012): `find_combobox_by_label` and `find_field_by_label` → add `wnd_id=wnd_id`
21. `focus_and_type()` (~1043): `session.find_by_id(f"wnd[0]/usr/...")` → `session.find_by_id(f"{wnd_id}/usr/...")`
22. `_find_editor_shell_raw()` (~1094): `session.find_by_id("wnd[0]/usr")` → `session.find_by_id(f"{wnd_id}/usr")`

**Pattern for each method:**

```python
async def some_method(self, ...):
    session = self._require_session()

    def _do():
        wnd_id = _active_window_id(session)  # ADD THIS LINE
        # ... replace "wnd[0]" with wnd_id or f"{wnd_id}/usr" ...
```

- [ ] **Step 4: Run the integration test**

```bash
python -m pytest "unittests/desktop/test_popup_rework_exploration.py::test_05_snapshot_shows_active_window" -v -s
```

Expected: PASS

- [ ] **Step 5: Run ALL existing desktop integration tests to check for regression**

```bash
python -m pytest unittests/desktop/ -v -k "integration and not exploration" --tb=short
```

Carefully review any failures — they may indicate methods that assumed `wnd[0]`.

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/backend/desktop/__init__.py unittests/desktop/test_popup_rework_exploration.py
git commit -m "feat: all desktop backend methods operate on active window"
```

---

### Task 4: Add `active_window` to `ToolResult` base class

**Files:**
- Modify: `src/sapguimcp/models/base.py`
- Modify: `unittests/desktop/test_popup_rework_unit.py`

- [ ] **Step 1: Write unit test**

Append to `unittests/desktop/test_popup_rework_unit.py`:

```python
def test_tool_result_has_active_window():
    from sapguimcp.models.base import ToolResult

    r = ToolResult(success=True, active_window="wnd[1]")
    assert r.active_window == "wnd[1]"


def test_tool_result_active_window_default_none():
    from sapguimcp.models.base import ToolResult

    r = ToolResult(success=True)
    assert r.active_window is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest unittests/desktop/test_popup_rework_unit.py -v -k "tool_result"
```

- [ ] **Step 3: Add `active_window` field to `ToolResult`**

In `src/sapguimcp/models/base.py`, add after the `popup` field (line ~74):

```python
    active_window: str | None = Field(
        default=None,
        description="Which window was operated on (e.g., 'wnd[0]', 'wnd[1]'). "
        "If 'wnd[1]' or higher, a modal dialog is open.",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest unittests/desktop/test_popup_rework_unit.py -v -k "tool_result"
```

- [ ] **Step 5: Run full unit test suite to check for model validation issues**

```bash
python -m pytest unittests/ -v -k "not integration and not exploration" --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/models/base.py unittests/desktop/test_popup_rework_unit.py
git commit -m "feat: add active_window field to ToolResult base class"
```

---

### Task 5: Remove popup-blocking checks in tool layer (desktop only)

**Files:**
- Modify: `src/sapguimcp/tools/sap_tools.py`

This is the core behavior change. Remove the 9 "popup blocking" pre-checks, but
**only for the desktop backend**. WebGUI keeps the current behavior.

- [ ] **Step 1: Write integration test for the new behavior**

In `unittests/desktop/test_popup_rework_exploration.py`, add:

```python
@skip_no_sap
@pytest.mark.anyio
async def test_06_keyboard_does_not_block_on_popup(backend):
    """After fix: sap_press_key works when popup is open (sends to active window)."""
    await backend.enter_transaction("SE21")
    await backend.wait_for_ready()

    form = await backend.get_form_fields()
    text_fields = [f for f in form.fields if str(f.field_type) == "text"]
    await backend.fill_form({text_fields[0].label: "ZTEST_POPUP_XYZ99"})
    await backend.wait(300)
    await backend.press_key("F5")
    await backend.wait(500)

    # Verify popup is open
    popup = await backend.check_popup()
    assert popup is not None, "Expected popup to be open"

    # press_key should work — it targets wnd[1] now
    result = await backend.press_key("Escape")
    assert result.success, f"press_key should succeed with popup open, got: {result.error}"

    # Popup should be closed now
    popup_after = await backend.check_popup()
    assert popup_after is None, "Popup should be closed after Escape"
```

- [ ] **Step 2: Identify and remove the 9 blocking locations**

In `src/sapguimcp/tools/sap_tools.py`, find each `check_popup()` + `"Popup blocking"` pattern.
Wrap the removal in a backend type check:

**Location 1: `sap_transaction` pre-check (line ~369-376)**

Keep this check — it's genuinely dangerous to enter an OkCode while a modal is open.
But improve the error message:

```python
        popup = await backend.check_popup()
        if popup:
            return TransactionResult.failure(
                f"Cannot navigate: a modal dialog is open (dismiss it first). "
                f"Dialog: {popup.message or 'confirmation required'}",
                tcode=tcode,
                popup=popup,
            )
```

**Location 2: `sap_transaction` post-navigation check (line ~387-394)**

Remove for desktop. The popup is now just normal state. For WebGUI, keep.

```python
                popup = await backend.check_popup()
                if popup and not _is_desktop_backend(backend):
                    return TransactionResult.failure(
                        f"Popup blocking: {popup.message or 'confirmation required'}",
                        tcode=tcode,
                        popup=popup,
                    )
```

**Location 3: `sap_transaction` new_window post-check (line ~401-408)**

Same — remove for desktop, keep for WebGUI.

**Location 4: `sap_press_key` pre-check (line ~540-548)**

Remove for desktop. The keystroke will go to the active window.

```python
            if not _is_desktop_backend(backend):
                popup = await backend.check_popup()
                if popup:
                    return KeyboardResult.failure(
                        f"Popup blocking: {popup.message or 'confirmation required'}",
                        key=key,
                        popup=popup,
                    )
```

**Location 5: `sap_press_key` post-check (line ~556-564)**

Remove for desktop. A popup appearing after a keystroke is just state change, not an error.

```python
            if not _is_desktop_backend(backend):
                popup_after = await backend.check_popup()
                if popup_after:
                    return KeyboardResult.failure(
                        f"Popup blocking: {popup_after.message or 'confirmation required'}",
                        key=key,
                        popup=popup_after,
                    )
```

**Location 6: `sap_fill_form` pre-check (line ~1201-1207)**

Remove for desktop. Field search now uses active window.

**Location 7: `sap_set_field` pre-check (line ~1278-1286)**

Remove for desktop.

**Location 8: `sap_set_checkbox` pre-check (line ~1327-1334)**

Remove for desktop.

**Location 9: `sap_set_radio_button` pre-check (line ~1370-1377)**

Remove for desktop.

- [ ] **Step 3: Add `_is_desktop_backend` import if not present**

The import already exists at line 57: `from sapguimcp.tools._backend_utils import _is_desktop_backend`

- [ ] **Step 4: Run the integration test**

```bash
python -m pytest "unittests/desktop/test_popup_rework_exploration.py::test_06_keyboard_does_not_block_on_popup" -v -s
```

Expected: PASS

- [ ] **Step 5: Run all exploration tests**

```bash
python -m pytest unittests/desktop/test_popup_rework_exploration.py -v -s --tb=short
```

Expected: All PASS (including the flipped assertions from Task 3)

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py unittests/desktop/test_popup_rework_exploration.py
git commit -m "feat: remove popup-blocking checks for desktop backend"
```

---

### Task 6: Populate `active_window` in tool results

**Files:**
- Modify: `src/sapguimcp/tools/sap_tools.py`
- Modify: `src/sapguimcp/backend/desktop/__init__.py`

The backend methods should return `active_window` in their results. The simplest
approach: have each backend method that returns a `ToolResult` populate
`active_window` before returning.

- [ ] **Step 1: Write integration test**

In `unittests/desktop/test_popup_rework_exploration.py`:

```python
@skip_no_sap
@pytest.mark.anyio
async def test_07_active_window_in_keyboard_result(backend):
    """KeyboardResult includes active_window field."""
    await backend.enter_transaction("SE21")
    await backend.wait_for_ready()

    # Normal screen — active_window should be wnd[0]
    result = await backend.press_key("Enter")
    assert result.active_window == "wnd[0]", f"Expected wnd[0], got {result.active_window}"

    # Trigger popup
    form = await backend.get_form_fields()
    text_fields = [f for f in form.fields if str(f.field_type) == "text"]
    await backend.fill_form({text_fields[0].label: "ZTEST_POPUP_XYZ99"})
    await backend.wait(300)

    # This should return with active_window="wnd[1]" (popup appeared)
    # Note: F5 on SE21 triggers the popup but we can't easily test this
    # from the backend level since press_key reads post-action state.
    # For now, just verify the field exists.
    assert hasattr(result, "active_window")
```

- [ ] **Step 2: Update `press_key` to populate `active_window` in result**

In `src/sapguimcp/backend/desktop/__init__.py`, `press_key()` method:

```python
    def _press() -> tuple[str, str, str, str]:
        wnd_id = _active_window_id(session)
        wnd = session.find_by_id(wnd_id)
        cast(Any, wnd).send_v_key(vkey)
        # Re-detect active window AFTER the keystroke
        post_wnd_id = _active_window_id(session)
        post_wnd = session.find_by_id(post_wnd_id)
        title = str(cast(Any, post_wnd).text)
        sbar = session.find_by_id(f"{post_wnd_id}/sbar", raise_error=False)
        sbar_text = str(cast(Any, sbar).text) if sbar else ""
        sbar_type = str(cast(Any, sbar).message_type) if sbar else ""
        return title, sbar_text, sbar_type, post_wnd_id
    # ... in return:
    return KeyboardResult(
        success=True,
        key=key,
        page_title=title,
        status_bar_read=True,
        status_bar_type=resolved_type,
        status_bar_message=sbar_text,
        active_window=active_wnd,
    )
```

Note: Modal windows (`wnd[1]`) may not have a `/sbar`. Use `raise_error=False`.

- [ ] **Step 3: Update `fill_form`, `get_form_fields`, `discover_fields`, `get_screen_info` similarly**

Each method should set `active_window` on its result. For methods that return
`ToolResult` subclasses, pass `active_window=wnd_id` to the constructor.

For methods that return plain lists (like `discover_fields`), the tool layer in
`sap_tools.py` should detect the active window and attach it.

- [ ] **Step 4: Run tests**

```bash
python -m pytest unittests/desktop/test_popup_rework_exploration.py -v -s --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/desktop/__init__.py src/sapguimcp/tools/sap_tools.py
git commit -m "feat: populate active_window in tool results"
```

---

### Task 7: Update abapgit error popup detection

**Files:**
- Modify: `src/sapguimcp/tools/abapgit_tools.py`

The `_check_for_error_popup_desktop()` function (line 216-225) uses
`get_snapshot()` and searches for `"wnd[1]"` in the text. After our change,
`get_snapshot()` returns the active window's tree, so this approach is unreliable.
Switch to using `check_popup()` directly.

- [ ] **Step 1: Update `_check_for_error_popup_desktop()`**

Replace lines 216-225:

```python
async def _check_for_error_popup_desktop(backend: "SapUiBackend") -> str | None:
    """Check for error popup via check_popup (desktop backend)."""
    popup = await backend.check_popup()
    if popup is None:
        return None
    return popup.message
```

- [ ] **Step 2: Update the "Inaktive Objekte" detection in `_run_pull_and_check_errors()`**

Lines ~459-469 use `get_snapshot()` to check for "Inaktive Objekte". Since
`get_snapshot()` now shows the active window, if a popup with that text is open
it will appear in the snapshot naturally. However, using `check_popup()` is more
reliable:

```python
    # SAP may show an "Inaktive Objekte" / "Inactive Objects" popup after pull.
    popup = await backend.check_popup()
    if popup and popup.message:
        msg_lower = popup.message.lower()
        if "inaktive objekte" in msg_lower or "inactive objects" in msg_lower:
            logger.info("Detected inactive objects popup, confirming with Enter")
            await backend.press_key("Enter")
            await backend.wait(2000)
            try:
                await backend.wait_for_ready(timeout_ms=30_000)
            except Exception:
                pass
```

- [ ] **Step 3: Run abapgit-related tests if available**

```bash
python -m pytest unittests/desktop/test_abapgit_integration.py -v --tb=short 2>&1 | head -40
```

If no live abapgit test is possible, verify unit tests pass:

```bash
python -m pytest unittests/ -k "abapgit" -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/tools/abapgit_tools.py
git commit -m "fix: update abapgit error popup detection for active window model"
```

---

### Task 8: Update `sap_knowledge.md` with active window guidance

**Files:**
- Modify: `src/sapguimcp/data/sap_knowledge.md`

- [ ] **Step 1: Add guidance section**

After the "## When Stuck" section (around line 63), add:

```markdown
## Working with Modal Dialogs (Popups)

SAP often opens modal dialogs (popups) for confirmations, data entry forms,
transport prompts, and error messages. These appear at `wnd[1]` or `wnd[2]`.

**All tools automatically operate on the active window.** When a popup is open,
`sap_discover_fields`, `sap_get_form_fields`, `sap_fill_form`, `sap_press_key`,
and other tools target the popup — not the main window behind it.

**How to detect a popup opened:**
- Check the `active_window` field in tool results. `"wnd[0]"` means the main
  window; `"wnd[1]"` or higher means a modal dialog is open.
- After actions that change screen state (`sap_press_key`, `sap_fill_form`),
  always note the `active_window` value.

**Typical workflow:**
1. `sap_press_key(key="F5")` → result has `active_window="wnd[1]"` (dialog opened)
2. `sap_discover_fields()` → shows fields in the dialog
3. `sap_fill_form({...})` → fills dialog fields
4. `sap_press_key(key="Enter")` → result has `active_window="wnd[0]"` (dialog closed)

**To dismiss a dialog you don't need:** Use `sap_close_popup(close=True)` or
`sap_press_key(key="Escape")`.

**Cannot navigate while a dialog is open:** `sap_transaction()` will fail if a
modal dialog is present — dismiss it first.
```

- [ ] **Step 2: Commit**

```bash
git add src/sapguimcp/data/sap_knowledge.md
git commit -m "docs: add active window guidance to sap_knowledge.md"
```

---

### Task 9: Comprehensive regression testing

**Files:**
- Run existing integration tests

- [ ] **Step 1: Run all desktop integration tests**

```bash
python -m pytest unittests/desktop/ -k "integration" -v --tb=short
```

Watch for:
- Tests that open popups as part of their workflow (edit tools, abapgit)
- Tests that rely on `press_key` targeting `wnd[0]` specifically
- Tests that parse snapshot text looking for `wnd[1]`

- [ ] **Step 2: Run all unit tests**

```bash
python -m pytest unittests/ -k "not integration and not exploration" -v --tb=short
```

- [ ] **Step 3: Run the full exploration test suite**

```bash
python -m pytest unittests/desktop/test_popup_rework_exploration.py -v -s --tb=short
```

- [ ] **Step 4: Run isort + black**

```bash
python -m isort src/ unittests/ && python -m black src/ unittests/
```

- [ ] **Step 5: Final commit if formatting changed**

```bash
git add -u && git commit -m "style: isort + black formatting"
```

---

### Task 10: Create WebGUI follow-up issue

**Files:** None (GitHub issue)

Since the desktop backend is now fixed but WebGUI still has the old blocking
behavior, create a follow-up issue to track the WebGUI side.

- [ ] **Step 1: Create the issue**

```bash
gh issue create \
  --title "WebGUI backend: implement active window model for popup handling" \
  --label "enhancement" \
  --body "## Context

Desktop backend now uses \`_active_window_id()\` to operate on the topmost
window (see #600, #609). The popup-blocking checks in \`sap_tools.py\` are
removed for the desktop backend but **kept for WebGUI** to prevent regression.

## What needs to happen

1. Implement popup overlay detection in WebGUI JS scripts:
   - \`discover_fields.js\` — detect popup overlay, extract fields from popup DOM
   - \`detect_form_fields.js\` — same
   - \`check_popup.js\` — already works, but needs to return structured field info
2. Update \`WebGuiBackend\` methods to target popup overlay when present
3. Remove the WebGUI popup-blocking guards in \`sap_tools.py\`
4. Add integration tests for WebGUI popup interaction

## Design reference

\`docs/superpowers/specs/2026-04-04-popup-rework-active-window-design.md\`

Relates to #600, #609"
```

- [ ] **Step 2: Commit the plan document itself**

```bash
git add docs/superpowers/plans/2026-04-04-popup-rework-active-window.md
git commit -m "docs: add popup rework implementation plan"
```
