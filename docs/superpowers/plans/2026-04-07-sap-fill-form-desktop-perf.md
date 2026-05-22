# `sap_fill_form` Desktop Backend Performance Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `desktop.fill_form` from timing out on multi-field calls (e.g. BP person creation) by hoisting the expensive `dump_tree()` work out of the per-field loop. Pass the flattened tree as a required parameter into `find_field_by_label` and its tree-using strategies. Also add a canonical example payload to the `sap_fill_form` tool description so agents stop guessing the wrong shape.

**Architecture:** Single repo, single feature branch (`fix/627-sap-fill-form-desktop-perf`, already created). Pure refactor inside `src/sapguimcp/backend/desktop/_element_finder.py` and `src/sapguimcp/backend/desktop/__init__.py`, plus a one-line docstring change in `src/sapguimcp/tools/sap_tools.py`. No new modules, no public API change.

**Tech Stack:** Python 3.12, pytest, pytest-anyio, SAP GUI Scripting COM (via sapsucker/pywin32), FastMCP

**Spec:** `docs/superpowers/specs/2026-04-07-sap-fill-form-desktop-perf-design.md`

**Issue:** Hochfrequenz/sapgui.mcp#627

---

## File Map

| File | Role | Change |
|------|------|--------|
| `src/sapguimcp/backend/desktop/_element_finder.py` | Element-finder helpers | Add `_dump_flat_tree` helper. Add required `flat_tree` parameter to `find_field_by_label`, `_find_by_label_text`, `_find_by_readonly_textfield_label`. |
| `src/sapguimcp/backend/desktop/__init__.py` | Desktop backend impl | Five callers of `find_field_by_label` updated to compute `flat_tree` once at the top of their COM closure and pass it in. `fill_form` is the perf-critical one. |
| `src/sapguimcp/tools/sap_tools.py` | MCP tool registrations | Append canonical example payload to `sap_fill_form` description string. |
| `unittests/desktop/test_element_finder.py` | Element-finder unit tests | Update 10 existing `find_field_by_label(...)` call sites to pass a `flat_tree`. Add new regression tests (count assertion, prebuilt-tree assertion). |
| `unittests/desktop/test_bp_integration.py` | BP integration tests | Add a new `skip_no_sap` test that fills 7 BP fields in one `sap_fill_form` call and asserts it completes under a wall-clock soft limit. |

---

## Task 1: Verify clean starting state

**Files:** none

- [ ] **Step 1: Confirm we're on the fix branch**

```bash
git rev-parse --abbrev-ref HEAD
```

Expected output: `fix/627-sap-fill-form-desktop-perf`

- [ ] **Step 2: Run the existing element-finder tests as baseline**

```bash
python -m pytest unittests/desktop/test_element_finder.py -v --tb=short
```

Expected: all tests pass on the unmodified code. If they don't, stop and investigate before touching anything.

- [ ] **Step 3: Run the existing desktop backend tests as baseline**

```bash
python -m pytest unittests/desktop/ -v --tb=short -k "not integration and not exploration and not stress"
```

Expected: all non-`skip_no_sap` tests pass. (The integration tests under `skip_no_sap` won't run unless an SAP session is available — that's fine.)

---

## Task 2: Add `_dump_flat_tree` helper in `_element_finder.py`

**Files:**
- Modify: `src/sapguimcp/backend/desktop/_element_finder.py` (after `_flatten`, before `_extract_container_path`)
- Modify: `unittests/desktop/test_element_finder.py` (add new test class)

- [ ] **Step 1: Write the failing test**

Append to `unittests/desktop/test_element_finder.py` (at the bottom of the file, after the last `class Test...`):

```python
class TestDumpFlatTree:
    """Helper that dumps and flattens the usr subtree."""

    def test_returns_flat_list_from_session(self):
        from sapguimcp.backend.desktop._element_finder import _dump_flat_tree

        child = _make_elem(
            type_as_number=30,
            name="CHILD",
            text="Child",
            elem_id="wnd[0]/usr/sub/lblCHILD",
        )
        parent = _make_elem(
            type_as_number=30,
            name="PARENT",
            text="Parent",
            elem_id="wnd[0]/usr/lblPARENT",
            children=[child],
        )
        session = _make_session_with_tree([parent])

        flat = _dump_flat_tree(session)

        # Both parent and child should appear in the flat list
        assert len(flat) == 2
        assert flat[0].name == "PARENT"
        assert flat[1].name == "CHILD"

    def test_uses_given_wnd_id(self):
        from sapguimcp.backend.desktop._element_finder import _dump_flat_tree

        # Build a session whose wnd[1]/usr returns a single element
        session = MagicMock()
        usr1 = MagicMock()
        elem = _make_elem(
            type_as_number=30,
            name="POPUPLBL",
            text="PopupLabel",
            elem_id="wnd[1]/usr/lblPOPUPLBL",
        )
        usr1.dump_tree.return_value = [elem]

        def find_by_id(element_id, raise_error=True):
            if element_id == "wnd[1]/usr":
                return usr1
            if not raise_error:
                return None
            raise Exception(f"Element not found: {element_id}")

        session.find_by_id = find_by_id

        flat = _dump_flat_tree(session, wnd_id="wnd[1]")
        assert len(flat) == 1
        assert flat[0].name == "POPUPLBL"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
python -m pytest unittests/desktop/test_element_finder.py::TestDumpFlatTree -v
```

Expected: `ImportError` or `AttributeError` — `_dump_flat_tree` doesn't exist yet.

- [ ] **Step 3: Add the helper to `_element_finder.py`**

In `src/sapguimcp/backend/desktop/_element_finder.py`, immediately after the `_flatten` function (around line 43), add:

```python
def _dump_flat_tree(session: Any, wnd_id: str = "wnd[0]") -> list[Any]:
    """Dump and flatten the ``usr`` subtree of the given window.

    Centralises the ``find_by_id(...)/dump_tree()/_flatten()`` idiom so that
    callers in the desktop backend can compute the flat tree once and pass it
    into ``find_field_by_label`` (and its tree-using strategy helpers) without
    each helper redundantly re-dumping the tree.
    """
    usr = session.find_by_id(f"{wnd_id}/usr")
    return _flatten(usr.dump_tree())
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
python -m pytest unittests/desktop/test_element_finder.py::TestDumpFlatTree -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/desktop/_element_finder.py unittests/desktop/test_element_finder.py
git commit -m "feat(desktop): add _dump_flat_tree helper in _element_finder

Centralises the find_by_id/dump_tree/_flatten idiom so callers can hoist
the tree dump out of per-field loops. Pure addition; no callers yet.

Refs #627"
```

---

## Task 3: Refactor `_find_by_label_text` to take `flat_tree`

**Files:**
- Modify: `src/sapguimcp/backend/desktop/_element_finder.py:70-96`

This helper is currently called only by `find_field_by_label`. After this task it requires a `flat_tree` parameter and no longer dumps the tree itself. We'll fix the one caller in Task 5.

- [ ] **Step 1: Update `_find_by_label_text` signature and body**

Replace the existing function (currently at lines 70–96) with:

```python
def _find_by_label_text(
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None:
    """Strategy 2: Find a field via a matching ``GuiLabel`` in ``flat_tree``.

    The caller is responsible for providing a flat tree (typically via
    :func:`_dump_flat_tree`). This helper no longer fetches its own tree so
    that batch callers like ``desktop.fill_form`` can share one tree across
    many label lookups.

    Prefers exact match (after stripping) over substring match.
    """
    needle = label.strip().lower()

    # First pass: exact match
    for elem in flat_tree:
        if elem.type_as_number == _TYPE_LABEL and elem.text.strip().lower() == needle:
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            field = _find_by_name_prefix(session, elem.name, path_prefix)
            if field is not None:
                return field

    # Second pass: substring match
    for elem in flat_tree:
        if elem.type_as_number == _TYPE_LABEL and needle in elem.text.strip().lower():
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            field = _find_by_name_prefix(session, elem.name, path_prefix)
            if field is not None:
                return field

    return None
```

- [ ] **Step 2: Run all element-finder tests — they will mostly fail; that is expected**

```bash
python -m pytest unittests/desktop/test_element_finder.py -v --tb=short
```

Expected: tests in `TestFindFieldByLabelText` and any other class that exercises Strategy 2 fail with `TypeError: _find_by_label_text() missing 1 required positional argument: 'flat_tree'` (because `find_field_by_label` is still calling it the old way). We'll fix all callers in Task 5. **Do not commit yet** — the tree is in an intentionally broken state.

---

## Task 4: Refactor `_find_by_readonly_textfield_label` to take `flat_tree`

**Files:**
- Modify: `src/sapguimcp/backend/desktop/_element_finder.py:99-152`

Same shape as Task 3.

- [ ] **Step 1: Update `_find_by_readonly_textfield_label` signature and body**

Replace the existing function (currently at lines 99–152) with:

```python
def _find_by_readonly_textfield_label(  # pylint: disable=too-many-locals
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None:
    """Strategy 3: Non-changeable ``GuiTextField`` acting as visual label.

    SAP address screens use read-only ``GuiTextField`` (type 31,
    ``changeable=False``) as labels. Examples: "Straße/Hausnummer",
    "Postleitzahl/Ort".

    For composite labels containing ``"/"``, the label text is split and each
    part is matched to the consecutive changeable input fields that follow the
    label in the flat tree. Example: "Straße" → ``ADDR2_DATA-STREET``,
    "Hausnummer" → ``ADDR2_DATA-HOUSE_NUM1``.

    Also supports the full composite text (e.g. "Straße/Hausnummer" → first
    field).

    The caller provides ``flat_tree``; this helper no longer dumps its own.
    """
    needle = label.strip().lower()
    input_types = {_TYPE_TEXT_FIELD, _TYPE_CTEXT_FIELD, _TYPE_PASSWORD_FIELD, _TYPE_COMBOBOX}

    for i, elem in enumerate(flat_tree):
        # Only consider non-changeable text fields as labels
        if elem.type_as_number != _TYPE_TEXT_FIELD or elem.changeable:
            continue
        elem_text = elem.text.strip().lower()
        if not elem_text:
            continue

        # Collect consecutive changeable input fields that follow this label
        following_inputs: list[Any] = []
        for j in range(i + 1, len(flat_tree)):
            sibling = flat_tree[j]
            if sibling.type_as_number in input_types and sibling.changeable:
                following_inputs.append(sibling)
            elif sibling.type_as_number in input_types and not sibling.changeable:
                continue  # Skip other read-only text fields (might be another label)
            else:
                break  # Stop at non-input elements (buttons, boxes, containers)

        if not following_inputs:
            continue

        # Exact match on full composite label → first input field
        if elem_text == needle:
            return session.find_by_id(following_inputs[0].id)

        # Split composite label on "/" and match individual parts
        if "/" in elem_text:
            parts = [p.strip().lower() for p in elem_text.split("/")]
            for idx, part in enumerate(parts):
                if part == needle and idx < len(following_inputs):
                    return session.find_by_id(following_inputs[idx].id)

    return None
```

- [ ] **Step 2: Tree still broken — do not commit. Move on to Task 5.**

---

## Task 5: Refactor `find_field_by_label` to take `flat_tree`

**Files:**
- Modify: `src/sapguimcp/backend/desktop/_element_finder.py:168-204`

- [ ] **Step 1: Update `find_field_by_label` signature and body**

Replace the existing function (currently at lines 168–204) with:

```python
def find_field_by_label(
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None:
    """Find an input field by its associated label text.

    The caller must provide a ``flat_tree`` (typically obtained via
    :func:`_dump_flat_tree`). Strategies 2 and 3 walk this list directly
    instead of dumping their own tree, so a batch caller like
    ``desktop.fill_form`` can hoist the dump out of its per-field loop.

    Strategies (tried in order):

    1. Name-prefix convention: label ``lblFOO`` -> try ``txtFOO``, ``ctxtFOO``,
       ``pwdFOO``, ``cmbFOO``
    2. Recursive label text match: walk ``flat_tree``, find label matching
       text, then find associated field via name prefix
    3. Read-only text field label: non-changeable ``GuiTextField`` as visual
       label, supports composite labels like "Straße/Hausnummer"
    4. ``find_by_name`` fallback: use SAP's native ``FindByName``
    """
    # Strategy 1: direct name prefix
    field = _find_by_name_prefix(session, label, path_prefix=f"{wnd_id}/usr/")
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "name_prefix"})
        return field

    # Strategy 2: label text match (GuiLabel type 30)
    field = _find_by_label_text(session, label, flat_tree, wnd_id=wnd_id)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "label_text"})
        return field

    # Strategy 3: read-only text field label (composite labels like "Straße/Hausnummer")
    field = _find_by_readonly_textfield_label(session, label, flat_tree, wnd_id=wnd_id)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "readonly_textfield_label"})
        return field

    # Strategy 4: SAP native FindByName
    field = _find_by_sap_name(session, label, wnd_id=wnd_id)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "sap_name"})
        return field

    logger.debug("find_field", extra={"label": label, "strategy": "not_found"})
    return None
```

- [ ] **Step 2: Tree still broken — every caller is wrong. Move on to Task 6.**

---

## Task 6: Update existing tests in `test_element_finder.py`

**Files:**
- Modify: `unittests/desktop/test_element_finder.py:77, 86, 94, 113, 128, 141, 275, 306, 330, 346`

There are 10 call sites of `find_field_by_label` in this file. Each needs a `flat_tree` argument. Because the existing test helper `_make_session_with_tree` returns elements without children, the same list is its own flat representation.

- [ ] **Step 1: Update each call site to pass the flat tree**

For each line below, change `find_field_by_label(session, "...")` to `find_field_by_label(session, "...", flat_tree)`. The `flat_tree` value is the same list that was passed to `_make_session_with_tree([...])` for that test. The exact mapping:

| Line | Test method | Old call | Tree variable to pass |
|------|-------------|----------|-----------------------|
| 77 | `test_finds_text_field_by_name` | `find_field_by_label(session, "MATNR")` | `[]` (test passes `_make_session_with_tree([], ...)`) |
| 86 | `test_finds_ctext_field_by_name` | `find_field_by_label(session, "MATNR")` | `[]` |
| 94 | `test_returns_none_when_no_match` | `find_field_by_label(session, "NONEXISTENT")` | `[]` |
| 113 | `test_finds_field_via_label_text` | `find_field_by_label(session, "Material")` | `[label_elem]` |
| 128 | `test_case_insensitive_label_match` | `find_field_by_label(session, "company code")` | `[label_elem]` |
| 141 | `test_finds_via_find_by_name` | `find_field_by_label(session, "SOME_FIELD")` | `[]` |
| 275 | `test_full_composite_label_resolves_to_first_field` | `find_field_by_label(session, "Straße/Hausnummer")` | `[label, street, house]` |
| 306 | `test_composite_part_resolves_to_correct_field` | `find_field_by_label(session, "Hausnummer")` | `[label, street, house]` |
| 330 | `test_non_composite_readonly_label` | `find_field_by_label(session, "Bemerkungen")` | `[label, field]` |
| 346 | `test_no_following_inputs_returns_none` | `find_field_by_label(session, "Hinweis")` | `[label]` |

For each test, **bind the tree to a local variable before calling `_make_session_with_tree`** and reuse it in both calls. Example for line 113 (the first non-trivial one):

```python
def test_finds_field_via_label_text(self):
    label_elem = _make_elem(
        type_as_number=30,
        name="MATNR",
        text="Material",
        elem_id="wnd[0]/usr/lblMATNR",
    )
    txt_field = MagicMock()
    flat_tree = [label_elem]
    session = _make_session_with_tree(
        flat_tree,
        find_by_id_extras={"wnd[0]/usr/txtMATNR": txt_field},
    )
    result = find_field_by_label(session, "Material", flat_tree)
    assert result is txt_field
```

For tests where the tree is `[]`, you can either bind `flat_tree = []` or just inline `[]` at the call site:

```python
result = find_field_by_label(session, "MATNR", [])
```

Apply the same pattern at all 10 call sites listed above.

- [ ] **Step 2: Run the element-finder tests**

```bash
python -m pytest unittests/desktop/test_element_finder.py -v --tb=short
```

Expected: all tests in this file pass. If a test fails on something other than the signature, stop and investigate — Tasks 3–5 may have broken behavior.

- [ ] **Step 3: Commit**

```bash
git add src/sapguimcp/backend/desktop/_element_finder.py unittests/desktop/test_element_finder.py
git commit -m "refactor(desktop): require flat_tree on find_field_by_label

Hoist dump_tree out of the per-call path of find_field_by_label and its
two tree-using strategy helpers (_find_by_label_text,
_find_by_readonly_textfield_label). The flat tree is now a required
parameter; callers compute it once via _dump_flat_tree.

Strategies 1 and 4 are unchanged (they don't walk the tree). All
existing test_element_finder.py call sites updated.

Production callers in desktop/__init__.py are updated in a separate
commit (next task).

Refs #627"
```

---

## Task 7: Update production callers in `desktop/__init__.py`

**Files:**
- Modify: `src/sapguimcp/backend/desktop/__init__.py:919-997, 1094-1115, 1117-1155`

There are five callers of `find_field_by_label` in this file. Each must compute `flat_tree` once at the top of its COM closure and pass it in.

- [ ] **Step 1: Verify the import**

Open `src/sapguimcp/backend/desktop/__init__.py` and confirm `_dump_flat_tree` is imported. Find the existing import block that pulls names from `._element_finder` and add `_dump_flat_tree` to it. Search for `from ._element_finder import` (or however the existing imports are structured) — add `_dump_flat_tree` to the imported names.

If you need to confirm the exact import pattern:

```bash
python -c "from sapguimcp.backend.desktop._element_finder import _dump_flat_tree; print('ok')"
```

Expected: `ok`. (This validates the helper is importable; the production-file import is what you actually edit.)

- [ ] **Step 2: Update `fill_field` (around line 919)**

Find the `_fill` closure inside `async def fill_field`. Replace:

```python
def _fill() -> None:
    wnd_id = _active_window_id(session)
    field = find_field_by_label(session, label, wnd_id=wnd_id)
    if field is None:
        raise ValueError(f"Field not found: {label}")
    _set_field_value(_unwrap_com(field), value)
```

with:

```python
def _fill() -> None:
    wnd_id = _active_window_id(session)
    flat_tree = _dump_flat_tree(session, wnd_id)
    field = find_field_by_label(session, label, flat_tree, wnd_id=wnd_id)
    if field is None:
        raise ValueError(f"Field not found: {label}")
    _set_field_value(_unwrap_com(field), value)
```

- [ ] **Step 3: Update `fill_main_input` (around line 937)**

In `async def fill_main_input`, replace the `_fill` closure with:

```python
def _fill() -> bool:
    wnd_id = _active_window_id(session)
    flat_tree = _dump_flat_tree(session, wnd_id)
    for lbl in labels:
        field = find_field_by_label(session, lbl, flat_tree, wnd_id=wnd_id)
        if field is not None:
            _set_field_value(_unwrap_com(field), value)
            return True
    return False
```

- [ ] **Step 4: Update `fill_form` (around line 954) — the perf-critical one**

In `async def fill_form`, replace the `_fill` closure with:

```python
def _fill() -> dict[str, Any]:
    wnd_id = _active_window_id(session)
    flat_tree = _dump_flat_tree(session, wnd_id)
    filled: list[str] = []
    not_found: list[str] = []
    errors: list[dict[str, str]] = []
    for label, value in fields.items():
        try:
            field = find_field_by_label(session, label, flat_tree, wnd_id=wnd_id)
            if field is None:
                not_found.append(label)
                continue
            _set_field_value(_unwrap_com(field), value)
            filled.append(label)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            errors.append({"field": label, "error": str(exc)})
    return {"filled": filled, "not_found": not_found, "errors": errors, "wnd_id": wnd_id}
```

The diff is exactly two lines: the `flat_tree = _dump_flat_tree(...)` line is added, and the `find_field_by_label(...)` call inside the loop now passes `flat_tree` as its third argument.

- [ ] **Step 5: Update `select_dropdown` fallback (around line 1104)**

In `async def select_dropdown`, the `_select` closure currently does:

```python
def _select() -> dict[str, Any]:
    wnd_id = _active_window_id(session)
    cmb = find_combobox_by_label(session, label, wnd_id=wnd_id)
    if cmb is None:
        # Also try find_field_by_label as fallback
        cmb = find_field_by_label(session, label, wnd_id=wnd_id)
    ...
```

Change to:

```python
def _select() -> dict[str, Any]:
    wnd_id = _active_window_id(session)
    cmb = find_combobox_by_label(session, label, wnd_id=wnd_id)
    if cmb is None:
        # Also try find_field_by_label as fallback
        flat_tree = _dump_flat_tree(session, wnd_id)
        cmb = find_field_by_label(session, label, flat_tree, wnd_id=wnd_id)
    ...
```

(Note: only fetch the tree inside the fallback branch, not unconditionally — `find_combobox_by_label` is the common case and doesn't need it.)

- [ ] **Step 6: Update `focus_and_type` fallback (around line 1147)**

In `async def focus_and_type`, the `_type` closure currently calls `find_field_by_label(session, accessible_name, wnd_id=wnd_id)` only after the direct-find prefix loop has failed. Change Strategy 2 to:

```python
# Strategy 2: label-based search (slower)
flat_tree = _dump_flat_tree(session, wnd_id)
field = find_field_by_label(session, accessible_name, flat_tree, wnd_id=wnd_id)
```

Same reasoning as Step 5: only compute the tree when we actually need it, not unconditionally.

- [ ] **Step 7: Run the desktop unit tests**

```bash
python -m pytest unittests/desktop/test_element_finder.py unittests/desktop/test_general_tools_integration.py -v --tb=short -k "not integration and not exploration and not stress"
```

Expected: all pass. If something else in `unittests/desktop/` was already importing or calling these methods, run a broader sweep:

```bash
python -m pytest unittests/desktop/ -v --tb=short -k "not integration and not exploration and not stress"
```

Expected: all non-`skip_no_sap` tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/sapguimcp/backend/desktop/__init__.py
git commit -m "fix(desktop): hoist dump_tree out of fill_form per-field loop

Five callers of find_field_by_label now compute flat_tree once at the
top of their COM closure (fill_form/fill_main_input batch the call across
all fields; the three single-shot callers still take one dump per call,
unchanged).

This is the load-bearing change for #627: BP person creation with ~7
labelled fields previously did up to 14 dump_tree calls in one COM
closure and timed out on the MCP client. After this change it does 1.

Fixes #627"
```

---

## Task 8: Add regression unit test — `fill_form` calls `dump_tree` exactly once

**Files:**
- Modify: `unittests/desktop/test_element_finder.py` (or create a new `unittests/desktop/test_fill_form_dump_tree.py` if you'd rather isolate it)

This is the test that will catch any future regression that re-introduces a per-field dump.

- [ ] **Step 1: Decide where to put the test**

The simplest choice is to extend `unittests/desktop/test_element_finder.py` with a new test class. The fancier option is a new file. **Pick the simpler one.** Append to `test_element_finder.py`.

- [ ] **Step 2: Write the failing test**

Append this class to the bottom of `unittests/desktop/test_element_finder.py`:

```python
class TestFillFormDumpTreeCount:
    """Regression for #627: fill_form must call dump_tree at most once per call.

    The bug was that desktop.fill_form looped over fields and each call to
    find_field_by_label internally re-dumped the tree (up to 2x via Strategies
    2 and 3). For ~7 BP fields that was ~14 dumps in one synchronous COM
    closure, blowing past the MCP client timeout. The fix hoists dump_tree
    out of the loop. This test asserts the hoist stays hoisted.
    """

    def test_fill_form_dumps_tree_once_for_many_fields(self):
        # Build a tree with 5 labels that all match Strategy 2 (label text)
        labels_and_fields = [
            ("Vorname", "FIRSTNAME"),
            ("Nachname", "LASTNAME"),
            ("Land", "COUNTRY"),
            ("Strasse", "STREET"),
            ("Ort", "CITY"),
        ]
        tree_elems = []
        find_by_id_extras = {}
        for label_text, name in labels_and_fields:
            tree_elems.append(
                _make_elem(
                    type_as_number=30,
                    name=name,
                    text=label_text,
                    elem_id=f"wnd[0]/usr/lbl{name}",
                )
            )
            field_mock = MagicMock()
            find_by_id_extras[f"wnd[0]/usr/txt{name}"] = field_mock

        session = _make_session_with_tree(tree_elems, find_by_id_extras=find_by_id_extras)
        usr = session.find_by_id("wnd[0]/usr")
        # Reset the call count after construction-time access
        usr.dump_tree.reset_mock()

        # Call find_field_by_label five times the way fill_form does it:
        # one shared flat_tree, reused across iterations.
        from sapguimcp.backend.desktop._element_finder import (
            _dump_flat_tree,
            find_field_by_label,
        )

        flat_tree = _dump_flat_tree(session)
        for label_text, _ in labels_and_fields:
            result = find_field_by_label(session, label_text, flat_tree)
            assert result is not None, f"Did not find {label_text}"

        assert usr.dump_tree.call_count == 1, (
            f"Expected dump_tree to be called exactly once when fill_form-style "
            f"hoisting is used; got {usr.dump_tree.call_count} calls. This is the "
            f"#627 regression: per-field dump_tree calls cause MCP client timeouts."
        )
```

- [ ] **Step 3: Run the helper-layer test**

```bash
python -m pytest unittests/desktop/test_element_finder.py::TestFillFormDumpTreeCount::test_fill_form_dumps_tree_once_for_many_fields -v
```

Expected: passes. (First green-bar moment — proves 5 lookups against a shared `flat_tree` produce exactly 1 `dump_tree` call.)

If the test FAILS, the most likely cause is that one of the strategy helpers in Task 3 or Task 4 still has a `dump_tree` call hiding in it. Re-read those files.

- [ ] **Step 4: Add the production-caller-layer test**

The Step 2 test only proves the *helpers* hoist correctly. It does NOT exercise `desktop.fill_form` itself, so a future regression that re-fetches `flat_tree` *inside* the loop in `desktop/__init__.py` would slip past it. Add a second test that calls the real `DesktopBackend.fill_form` against a mocked COM session and asserts the same invariant at the production-caller layer.

Append to the same `TestFillFormDumpTreeCount` class in `unittests/desktop/test_element_finder.py`:

```python
    def test_desktop_fill_form_dumps_tree_once_for_many_fields(self):
        """Production-layer regression: DesktopBackend.fill_form must call
        dump_tree at most once per call. Complements the helper-layer test
        above by exercising the real caller in src/.../desktop/__init__.py.
        """
        import asyncio

        from sapguimcp.backend.desktop import DesktopBackend

        labels_and_fields = [
            ("Vorname", "FIRSTNAME"),
            ("Nachname", "LASTNAME"),
            ("Land", "COUNTRY"),
            ("Strasse", "STREET"),
            ("Ort", "CITY"),
        ]
        tree_elems = []
        find_by_id_extras = {}
        for label_text, name in labels_and_fields:
            tree_elems.append(
                _make_elem(
                    type_as_number=30,
                    name=name,
                    text=label_text,
                    elem_id=f"wnd[0]/usr/lbl{name}",
                )
            )
            field_mock = MagicMock()
            # _set_field_value writes to .text — make the mock accept it
            field_mock.text = ""
            find_by_id_extras[f"wnd[0]/usr/txt{name}"] = field_mock

        session = _make_session_with_tree(tree_elems, find_by_id_extras=find_by_id_extras)
        usr = session.find_by_id("wnd[0]/usr")
        usr.dump_tree.reset_mock()

        # Stub Com.run so it just executes the closure synchronously in this thread.
        com = MagicMock()

        async def fake_run(callable_):
            return callable_()

        com.run = fake_run

        backend = DesktopBackend.__new__(DesktopBackend)  # bypass __init__
        backend.com = com
        backend._session = session  # noqa: SLF001 — direct assignment for test
        backend.require_session = lambda: session

        payload = {label: "value" for label, _ in labels_and_fields}
        result = asyncio.get_event_loop().run_until_complete(backend.fill_form(payload))

        assert usr.dump_tree.call_count == 1, (
            f"DesktopBackend.fill_form called dump_tree {usr.dump_tree.call_count} "
            f"times for {len(payload)} fields — should be exactly 1. This is the "
            f"#627 regression at the production-caller layer."
        )
        assert len(result.filled) == len(payload), (
            f"Expected all {len(payload)} fields filled, got {result.filled}; "
            f"not_found={result.not_found}, errors={result.errors}"
        )
```

**Note for the implementer:** the exact attribute name for the cached session on `DesktopBackend` (used in `backend._session = session`) may differ — verify by reading `src/sapguimcp/backend/desktop/__init__.py` for how `require_session` is implemented and assign whichever attribute it reads. If the codebase uses a different mechanism for backend construction in tests (e.g. a `conftest.py` fixture or a factory), prefer that over `__new__` + manual attribute assignment.

If `DesktopBackend.__init__` requires non-trivial wiring that makes `__new__`-based construction fragile, fall back to: keep only the helper-layer test from Step 2 and add a comment at the top of `TestFillFormDumpTreeCount` documenting that the production-caller layer is covered indirectly via the `skip_no_sap` integration test in Task 10.

- [ ] **Step 5: Run both regression tests**

```bash
python -m pytest unittests/desktop/test_element_finder.py::TestFillFormDumpTreeCount -v
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add unittests/desktop/test_element_finder.py
git commit -m "test(desktop): add regression test for #627 dump_tree count

Asserts that 5 find_field_by_label calls against a shared flat_tree
result in exactly 1 dump_tree COM call. If anyone re-introduces a
per-field dump in the future, this test fails loudly with a clear
message pointing at #627."
```

---

## Task 9: Add the canonical example to the `sap_fill_form` tool description

**Files:**
- Modify: `src/sapguimcp/tools/sap_tools.py:1146-1165`

This addresses the *first* error in #627 (`Additional properties are not allowed`), which was the agent guessing the wrong payload shape. A visible example in the tool description prevents the same guess.

- [ ] **Step 1: Update the description string**

In `src/sapguimcp/tools/sap_tools.py`, find the `@mcp.tool(...)` decorator on `sap_fill_form` (around line 1146). The current `description=` string ends with the session-parameter block. Append the example by adding two new lines at the very end of the description string, just before the closing `)`:

The current ending looks like:

```python
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
```

Change it to:

```python
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)\n\n'
            "**Example payload:**\n"
            '`{"fields": {"Vorname": "Mario", "Nachname": "Rossi"}, "strict": false}`'
        )
    )
```

- [ ] **Step 2: Smoke-test that the server still imports**

```bash
python -c "from sapguimcp.server import create_server; print('ok')"
```

Expected: `ok`. (Validates the docstring change didn't break the module.)

- [ ] **Step 3: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py
git commit -m "docs(tools): add canonical example payload to sap_fill_form

Addresses the first error in #627: agents guess the payload shape
wrong on attempt 1 (top-level field map vs. {fields: {...}, strict})
because the description listed key formats but never showed a complete
example. A one-line example in the tool description fixes this without
any schema change."
```

---

## Task 10: Add desktop integration test for BP 7-field fill

**Files:**
- Modify: `unittests/desktop/test_bp_integration.py`

This is the end-to-end proof that the user-reported scenario works. Marked `skip_no_sap`; only runs when an SAP session is available.

- [ ] **Step 1: Append the new test**

Add to `unittests/desktop/test_bp_integration.py` (after the existing `test_bp_fill_form_with_dropdown` test):

```python
@pytest.mark.anyio
async def test_bp_fill_form_seven_fields_under_timeout(backend):
    """Regression for #627: fill_form with 7 BP fields completes in one call.

    Before the dump_tree hoist fix, this exact scenario timed out on the MCP
    client because each find_field_by_label call re-dumped the GUI tree.
    With the fix it should complete in well under 5 seconds wall-clock.
    """
    import time

    await backend.enter_transaction("BP")
    await backend.press_key("F5")  # Create person
    await backend.wait(1000)
    await backend.press_key("Enter")
    await backend.wait(1000)

    # Seven labelled fields — the size that triggered #627. Mix of plain
    # labels and at least one composite ("Strasse/Hausnummer" → "Strasse").
    # Field labels are German because that's the original repro language.
    payload = {
        "Anrede": "Herr",
        "Vorname": "Mario",
        "Nachname": "Rossi",
        "Land": "DE",
        "Strasse": "Hauptstraße 1",
        "Postleitzahl": "10115",
        "Ort": "Berlin",
    }

    start = time.monotonic()
    result = await backend.fill_form(payload)
    elapsed = time.monotonic() - start

    # Soft wall-clock assertion — generous to absorb CI host load. Pre-fix
    # this scenario regularly took >> 30s and timed out the MCP client.
    assert elapsed < 5.0, (
        f"fill_form took {elapsed:.2f}s for 7 fields — likely a regression of "
        f"#627 (dump_tree no longer hoisted out of the per-field loop)."
    )

    # Most fields should land. Some labels (e.g. Anrede as dropdown) may
    # vary by SAP version — assert the perf invariant first, behaviour
    # second.
    assert result.success or len(result.filled) >= 5, (
        f"Expected at least 5 of 7 fields filled, got: filled={result.filled}, "
        f"not_found={result.not_found}, errors={result.errors}"
    )
    await go_home(backend)
```

- [ ] **Step 2: Try to run it (will skip if no SAP)**

```bash
python -m pytest unittests/desktop/test_bp_integration.py::test_bp_fill_form_seven_fields_under_timeout -v
```

Expected on a dev machine without SAP: `SKIPPED [1] ... skip_no_sap`.

Expected on a machine with SAP available: `PASSED` (and the test prints elapsed time below 5s).

- [ ] **Step 3: Commit**

```bash
git add unittests/desktop/test_bp_integration.py
git commit -m "test(desktop): add #627 BP 7-field fill_form regression test

End-to-end proof that the user-reported scenario from issue #627
(BP person creation, 7 labelled fields in one sap_fill_form call) now
completes well under any reasonable MCP timeout. Marked skip_no_sap;
only runs when an SAP session is available."
```

---

## Task 11: Final verification — full desktop suite + lint

**Files:** none modified

- [ ] **Step 1: Run the entire desktop unit suite**

```bash
python -m pytest unittests/desktop/ -v --tb=short -k "not integration and not exploration and not stress"
```

Expected: all non-`skip_no_sap` tests pass.

- [ ] **Step 2: Run the broader sapguimcp test suite that doesn't need SAP**

```bash
python -m pytest unittests/ -v --tb=short -k "not integration and not exploration and not stress" -x
```

Expected: no failures. The `-x` flag stops on the first failure so a regression is loud and immediate.

- [ ] **Step 3: Run isort + black on the touched files**

Per project memory (`feedback_isort_black.md`): always isort + black before any commit. The previous tasks each had their own commit, so run the formatters now and amend only if there are real changes — preferably create a final formatting commit if needed.

```bash
python -m isort src/sapguimcp/backend/desktop/_element_finder.py src/sapguimcp/backend/desktop/__init__.py src/sapguimcp/tools/sap_tools.py unittests/desktop/test_element_finder.py unittests/desktop/test_bp_integration.py
python -m black src/sapguimcp/backend/desktop/_element_finder.py src/sapguimcp/backend/desktop/__init__.py src/sapguimcp/tools/sap_tools.py unittests/desktop/test_element_finder.py unittests/desktop/test_bp_integration.py
```

Expected: either "unchanged" output (if previous edits were already conformant) or a small diff. Inspect with `git diff` before committing.

- [ ] **Step 4: If formatters made changes, commit them**

```bash
git status
git diff
git add -u
git commit -m "style: isort + black on #627 fix files"
```

If `git status` is clean, skip this step.

- [ ] **Step 5: Run pylint on the touched modules**

```bash
python -m pylint src/sapguimcp/backend/desktop/_element_finder.py src/sapguimcp/backend/desktop/__init__.py src/sapguimcp/tools/sap_tools.py
```

Expected: same score or better than before the change. New warnings should be either fixed or explicitly justified (e.g. `# pylint: disable=...` with a comment). Do not silence anything just to make the score green.

- [ ] **Step 6: Re-run the regression test alone as a final smoke**

```bash
python -m pytest unittests/desktop/test_element_finder.py::TestFillFormDumpTreeCount -v
```

Expected: pass. This is the assertion that would have caught the original bug.

---

## Task 12: Code review and PR

**Files:** none

- [ ] **Step 1: Review your own diff**

```bash
git log --oneline origin/main..HEAD
git diff origin/main...HEAD --stat
```

Sanity-check the diff stat: roughly the files in the File Map, no unrelated changes. If you see anything unexpected (lockfile changes, IDE files, drive-by edits), stop and clean up.

- [ ] **Step 2: Run the superpowers code-reviewer agent**

Per project memory (`feedback_review_every_pr.md`): always run a code reviewer before creating any PR. Dispatch the `superpowers:code-reviewer` agent against the diff (`origin/main...HEAD`) with the spec (`docs/superpowers/specs/2026-04-07-sap-fill-form-desktop-perf-design.md`) as the review baseline.

If the reviewer flags issues, fix them in new commits and re-run.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin fix/627-sap-fill-form-desktop-perf
```

- [ ] **Step 4: Create the PR (do not merge — user merges via GitHub UI)**

Per project memory (`feedback_never_merge.md`): never merge to main; create the PR and let the user merge it.

```bash
gh pr create --title "fix(desktop): hoist dump_tree out of fill_form loop (#627)" --body "$(cat <<'EOF'
## Summary
- Fixes Hochfrequenz/sapgui.mcp#627 — `sap_fill_form` on the desktop backend timed out when filling many label-matched fields (e.g. BP person creation).
- Root cause: each `find_field_by_label` call internally dumped the SAP GUI tree, and `desktop.fill_form` did this once per field inside one synchronous COM closure. For ~7 fields × up to 2 dumps each, that's ~14 expensive `dump_tree` COM calls in one closure → MCP client timeout.
- Fix: hoist the tree dump out of the per-field loop. `flat_tree` is now a required parameter on `find_field_by_label`, `_find_by_label_text`, and `_find_by_readonly_textfield_label`. Callers compute it once via `_dump_flat_tree`.
- Bonus fix: added a canonical example payload to the `sap_fill_form` tool description, addressing the *first* error in the same issue (the agent guessing the wrong payload shape on attempt 1).

## Test plan
- [ ] Unit: `unittests/desktop/test_element_finder.py` — all existing tests pass after signature change
- [ ] Unit: `TestDumpFlatTree` — new helper returns flat list
- [ ] Unit (regression): `TestFillFormDumpTreeCount::test_fill_form_dumps_tree_once_for_many_fields` — asserts `dump_tree.call_count == 1` for 5 fields. If anyone re-introduces a per-field dump in the future, this fails loudly with a message pointing at #627.
- [ ] Integration (`skip_no_sap`): `test_bp_fill_form_seven_fields_under_timeout` — fills 7 BP fields in one `sap_fill_form` call, asserts wall-clock < 5s.
- [ ] Manual: smoke-test BP person creation in OpenCode with the original payload from #627

Spec: `docs/superpowers/specs/2026-04-07-sap-fill-form-desktop-perf-design.md`

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Report the PR URL**

Print the PR URL returned by `gh pr create` and stop. **Do not merge.** The user merges via GitHub UI.

---

## Done criteria

- [ ] All steps in Tasks 1–12 complete
- [ ] `python -m pytest unittests/desktop/ -v -k "not integration and not exploration and not stress"` is green
- [ ] `TestFillFormDumpTreeCount::test_fill_form_dumps_tree_once_for_many_fields` is green
- [ ] PR open against `main`, not yet merged
- [ ] Code reviewer agent has approved (or all flagged issues addressed)

## Rollback

If something goes catastrophically wrong after this lands and needs to be reverted:

```bash
git revert <merge-commit-sha>
```

The change is fully self-contained — no schema migrations, no data, no config. A revert restores the previous behaviour (slow but functional for small forms).
