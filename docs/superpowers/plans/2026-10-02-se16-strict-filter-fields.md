# SE16 strict filter fields (desktop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the desktop backend, `sap_se16_query` must fail before F8 (no query is run) whenever a requested filter field cannot be applied in the SE16N selection grid, and the error must name the unapplied field(s) and list the fields SE16N offers (issue #907).

**Architecture:** `_fill_se16n_filters_desktop` returns a `_FilterFillResult` dataclass (`unapplied_fields`, `other_errors`, `offered_fields`) instead of `list[str]`. `_find_and_set_filter_cell` / `_set_filter_with_scrolling` report the field names they saw so the offered list comes from the existing scan. `_execute_se16_query_desktop` inspects the result right after the fill and returns an `_empty_failure(...)` before max-hits/F8. `_empty_failure` gains an optional `filter_warnings` parameter and the status-bar error path passes warnings through. WebGUI backend, success path and `output_file` path are unchanged.

**Tech Stack:** Python 3.11+, pytest (anyio), `unittest.mock`, pydantic models (`SE16Result`), SAP GUI scripting via `DesktopBackend` (COM), ruff, mypy `--strict`.

Spec: `docs/superpowers/specs/2026-10-02-se16-strict-filter-fields-design.md`

---

## File Structure

| File                                         | Action | Responsibility                                                                                                                                                                                            |
| -------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `unittests/desktop/test_se16_integration.py` | Modify | Live desktop tests: case 1, case 2, case 3 (if discoverable), regression                                                                                                                                  |
| `src/sapguimcp/tools/se16_tools.py`          | Modify | `_FilterFillResult`, offered-field collection, `_format_offered_fields`, `_filter_fill_failure`, `_empty_failure(filter_warnings=...)`, fail-before-F8 in `_execute_se16_query_desktop`, tool description |
| `unittests/test_se16_filter_warnings.py`     | Modify | Unit tests for all of the above; rewrite `test_execute_se16_query_desktop_returns_filter_warnings`                                                                                                        |

No new files. `src/sapguimcp/models/se16_models.py` is unchanged (`SE16Result.failure(...)` already accepts `filter_warnings`, since `ToolResult.failure(error, **kwargs)` forwards kwargs).

Conventions to follow: live tests use `@skip_no_sap`, `@pytest.mark.anyio`, the module-scoped `backend` fixture from `unittests/desktop/conftest.py`, call `_execute_se16_query(backend, table, filters, max_hits)` and end with `await go_home(backend)`. Live tests are run **one at a time** (`-k <name>`), and the desktop fixture teardown closes **all** SAP GUI connections of the user, so do not run them while other SAP GUI work is open. Use only standard tables (`T000`, `TSTC`); no hostnames, SIDs, users or client numbers in code, comments or commit messages.

---

## Task 1: Live desktop integration tests (write first, confirm FAIL on current code)

**Files:**

- Modify: `unittests/desktop/test_se16_integration.py` (append after `test_se16_wildcard_filter`)

- [ ] **Step 1: Append cases 1, 2 and the regression test**

Append to the end of `unittests/desktop/test_se16_integration.py`:

```python


# ---------------------------------------------------------------------------
# SE16 strict filter fields (#907): unappliable filters must fail before F8
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_se16_unknown_field_with_valid_filter_fails(backend):
    """#907 case 1: a valid filter that matches nothing plus a made-up field must fail, not report 'no rows'."""
    result = await _execute_se16_query(backend, "T000", {"MANDT": "ZZZ", "ZZZFAKEFIELD": "X"}, 10)
    assert result.success is False, "Unknown filter field must make the query fail"
    assert result.error is not None
    assert "ZZZFAKEFIELD" in result.error
    assert "Offered fields:" in result.error
    assert "MANDT" in result.error, f"Offered list should contain MANDT: {result.error}"
    assert result.returned_rows == 0
    assert result.rows == []
    assert any("ZZZFAKEFIELD" in w for w in result.filter_warnings)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_only_unknown_field_fails_instead_of_unfiltered_rows(backend):
    """#907 case 2: only a made-up field on a populated table used to return unfiltered rows with success=True."""
    result = await _execute_se16_query(backend, "T000", {"ZZZFAKEFIELD": "X"}, 10)
    assert result.success is False, "Unknown filter field must make the query fail"
    assert result.error is not None
    assert "ZZZFAKEFIELD" in result.error
    assert result.returned_rows == 0
    assert result.rows == []
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_valid_filter_still_returns_filtered_rows(backend):
    """#907 regression: a valid filter still returns filtered rows, with success=True and no warnings."""
    result = await _execute_se16_query(backend, TEST_TABLE, {"TCODE": "SE16"}, 10)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.returned_rows >= 1
    assert result.filter_warnings == []
    for row in result.rows:
        assert row.data["TCODE"] == "SE16"
    await go_home(backend)
```

- [ ] **Step 2: Run each new test against the unchanged code, one at a time**

Commands (run sequentially, never in parallel; close other SAP GUI work first because teardown closes all SAP GUI connections):

```
uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_unknown_field_with_valid_filter_fails -x
uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_only_unknown_field_fails_instead_of_unfiltered_rows -x
uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_valid_filter_still_returns_filtered_rows -x
```

Expected:

- case 1: **FAIL**. Today the unknown field only becomes a warning and F8 runs, so either `success is False` fails (success=True, 0 hits) or `"ZZZFAKEFIELD" in result.error` fails (the error-status-bar path drops the warning via `_empty_failure`, and `error` is just `SE16N error: ...`). Either assertion failing is the expected red.
- case 2: **FAIL** at `assert result.success is False` (unfiltered T000 rows come back with success=True).
- regression: **PASS** (it guards behaviour that must not change).

If case 1 or 2 unexpectedly passes, stop and re-read the spec; the fix may already be partially present.

- [ ] **Step 3: Case 3 discovery - find a standard column SE16N does not offer as a selection field**

SE16N does not offer string-like columns (DDIC types `STRG`, `RSTR`, `LCHR`, `LRAW`, `RAW` long) as selection criteria. Discover a standard transparent table with such a column on the live system (read-only):

1. Ask DD03L for candidates (this uses the tool being fixed with one valid filter, which is fine):

    ```python
    # scratch, not committed - e.g. run once via a throwaway pytest or sap_run_script session
    result = await _execute_se16_query(backend, "DD03L", {"DATATYPE": "STRG", "AS4LOCAL": "A"}, 50)
    print([(r.data.get("TABNAME"), r.data.get("FIELDNAME")) for r in result.rows])
    ```

    Repeat with `"DATATYPE": "RSTR"` if no hits. Keep only entries whose `TABNAME` is a **standard, non-namespaced** table (no leading `/`, no leading `Z`/`Y`) and whose table is transparent (confirm in `DD02L`: `{"TABNAME": "<TAB>", "TABCLASS": "TRANSP"}` returns a row).

2. For the candidate, run `sap_se16_query` manually through `_execute_se16_query(backend, "<TAB>", {"<FIELD>": "X"}, 5)` on the **unchanged** code and open SE16N for `<TAB>` to confirm the field is **not** in the selection grid (the call returns a `Field '<FIELD>' not found in SE16N selection criteria` warning). Prefer a table that is small and present on every system (a repository/customizing table such as a text or buffer table).
3. Pick one `(TABLE, FIELD)` pair and hard-code it in the test below. Do not put system-specific values in it.

- [ ] **Step 4: Add case 3 (or the fallback)**

If a pair was found, append (replace `<TABLE>` / `<FIELD>` with the discovered standard names):

```python


@skip_no_sap
@pytest.mark.anyio
async def test_se16_real_column_not_offered_by_se16n_fails(backend):
    """#907 case 3: a real column that SE16N does not offer as selection field must fail, not run unfiltered."""
    result = await _execute_se16_query(backend, "<TABLE>", {"<FIELD>": "X"}, 10)
    assert result.success is False, "Field not offered by SE16N must make the query fail"
    assert result.error is not None
    assert "<FIELD>" in result.error
    assert "Offered fields:" in result.error
    assert result.returned_rows == 0
    assert result.rows == []
    await go_home(backend)
```

Run it on the unchanged code (same one-at-a-time rule): `uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_real_column_not_offered_by_se16n_fails -x`. Expected: **FAIL** at `success is False`.

**Fallback:** if no standard table with such a column can be found reliably, do not add the test. Instead append this comment block after the regression test so the reason is recorded, and rely on the unit tests (Task 3) for case 3:

```python
# #907 case 3 (a real table column that SE16N does not offer as a selection field) has no live
# test: no standard, non-namespaced table with a string/raw-string column could be identified
# reliably across systems. The behaviour is identical to an unknown field (the SE16N grid simply
# lacks the row) and is covered by the unit tests in unittests/test_se16_filter_warnings.py.
```

- [ ] **Step 5: Commit the red tests**

```
git add unittests/desktop/test_se16_integration.py
git commit -m "test: live desktop SE16 tests for strict filter fields (#907)"
```

(Cases 1/2 stay red until Task 7.)

---

## Task 2: `_FilterFillResult` and `_empty_failure(filter_warnings=...)`

**Files:**

- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `unittests/test_se16_filter_warnings.py`

- [ ] **Step 1: Write failing unit tests**

In `unittests/test_se16_filter_warnings.py` change the import line

```python
from sapguimcp.tools.se16_tools import _execute_se16_query_desktop, register_se16_tools
```

to

```python
from sapguimcp.tools.se16_tools import (
    _empty_failure,
    _execute_se16_query_desktop,
    _FilterFillResult,
    register_se16_tools,
)
```

and append:

```python


class TestFilterFillResult:
    def test_defaults_are_empty_and_independent(self) -> None:
        first = _FilterFillResult()
        second = _FilterFillResult()
        first.unapplied_fields.append("X")

        assert first.unapplied_fields == ["X"]
        assert second.unapplied_fields == []
        assert second.other_errors == []
        assert second.offered_fields == []


class TestEmptyFailureFilterWarnings:
    def test_passes_filter_warnings_through(self) -> None:
        now = datetime.now(UTC)

        result = _empty_failure("boom", "T000", now, filter_warnings=["w1", "w2"])

        assert result.success is False
        assert result.error == "boom"
        assert result.filter_warnings == ["w1", "w2"]

    def test_defaults_to_no_warnings(self) -> None:
        result = _empty_failure("boom", "T000", datetime.now(UTC))

        assert result.filter_warnings == []
```

- [ ] **Step 2: Run, expect FAIL**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k "FilterFillResult or EmptyFailureFilterWarnings" -x`
Expected: FAIL with `ImportError: cannot import name '_FilterFillResult'`.

- [ ] **Step 3: Implement**

In `src/sapguimcp/tools/se16_tools.py` add to the imports (alphabetical, stdlib block):

```python
from dataclasses import dataclass, field
```

(place above `from datetime import ...`).

Replace `_empty_failure` with:

```python
def _empty_failure(
    error: str,
    table: str,
    retrieved_at: datetime,
    total_hits: int = 0,
    columns: list[str] | None = None,
    filter_warnings: list[str] | None = None,
) -> SE16Result:
    """Create a failure SE16Result with empty rows."""
    return SE16Result.failure(
        error=error,
        table=table,
        total_hits=total_hits,
        returned_rows=0,
        truncated=False,
        columns=columns or [],
        rows=[],
        filter_warnings=filter_warnings or [],
        retrieved_at=retrieved_at,
    )
```

Add directly above `_find_and_set_filter_cell`:

```python
@dataclass
class _FilterFillResult:
    """Outcome of filling the SE16N selection criteria grid on the desktop backend."""

    unapplied_fields: list[str] = field(default_factory=list)  # requested names (as given) not found in the grid
    other_errors: list[str] = field(default_factory=list)  # non-field problems, e.g. grid not found
    offered_fields: list[str] = field(default_factory=list)  # technical names seen in the grid, deduped, grid order
```

- [ ] **Step 4: Run, expect PASS**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k "FilterFillResult or EmptyFailureFilterWarnings" -x`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add src/sapguimcp/tools/se16_tools.py unittests/test_se16_filter_warnings.py
git commit -m "feat: add _FilterFillResult and filter_warnings pass-through in _empty_failure (#907)"
```

---

## Task 3: Fill returns `_FilterFillResult` and collects offered fields

**Files:**

- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `unittests/test_se16_filter_warnings.py`

- [ ] **Step 1: Write failing unit tests with a fake selection grid**

Add to the imports of `unittests/test_se16_filter_warnings.py`:

```python
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from sapguimcp.backend.desktop import DesktopBackend
```

(and add `_fill_se16n_filters_desktop` to the `sapguimcp.tools.se16_tools` import list). If importing `DesktopBackend` fails on a non-Windows CI, guard these tests with `pytest.importorskip("sapguimcp.backend.desktop")`; first check by running the existing suite.

Append:

```python
class _ValueCell:
    def __init__(self, grid: "_FakeGrid", name: str) -> None:
        self._grid = grid
        self._name = name

    @property
    def Text(self) -> str:  # noqa: N802  (mirrors the SAP GUI COM attribute)
        return self._grid.values.get(self._name, "")

    @Text.setter
    def Text(self, value: str) -> None:  # noqa: N802
        self._grid.values[self._name] = value


class _NameCell:
    def __init__(self, text: str) -> None:
        self.Text = text


class _Scrollbar:
    def __init__(self, maximum: int) -> None:
        self.Maximum = maximum
        self.Position = 0


class _FakeGrid:
    """Minimal stand-in for the SE16N GuiTableControl: column 6 = field name, column 2 = From-value."""

    def __init__(self, names: list[str], visible: int) -> None:
        self._names = names
        self.RowCount = len(names)
        self.VisibleRowCount = visible
        self.VerticalScrollbar = _Scrollbar(max(0, len(names) - visible))
        self.values: dict[str, str] = {}

    def GetCell(self, row: int, col: int) -> Any:  # noqa: N802
        idx = self.VerticalScrollbar.Position + row
        name = self._names[idx] if idx < len(self._names) else ""
        if col == 6:
            return _NameCell(name)
        return _ValueCell(self, name)


def _desktop_backend_with_grid(grid: _FakeGrid | None) -> MagicMock:
    backend = MagicMock(spec=DesktopBackend)
    session = MagicMock()
    if grid is None:
        session.find_by_id.side_effect = RuntimeError("not found")
    else:
        session.find_by_id.return_value = SimpleNamespace(com=grid)
    backend.require_session.return_value = session

    async def _run(fn: Any) -> Any:
        return fn()

    backend.com = SimpleNamespace(run=_run)
    return backend


@pytest.mark.anyio
async def test_fill_all_fields_found_collects_no_offered_fields() -> None:
    grid = _FakeGrid(["MANDT", "MTEXT", "ORT01"], visible=5)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"mtext": "Foo"})

    assert result == _FilterFillResult()
    assert grid.values == {"MTEXT": "Foo"}


@pytest.mark.anyio
async def test_fill_unknown_field_within_visible_rows_lists_visible_names_only() -> None:
    # row_count (3) <= visible (5): no scrolling, offered names come from the visible rows only
    grid = _FakeGrid(["MANDT", "", "MTEXT"], visible=5)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert result.other_errors == []
    assert result.offered_fields == ["MANDT", "MTEXT"]  # blank padding row skipped
    assert grid.VerticalScrollbar.Position == 0


@pytest.mark.anyio
async def test_fill_unknown_field_walks_scrolled_grid_dedupes_and_keeps_order() -> None:
    names = ["MANDT", "MTEXT", "ORT01", "MTEXT", "MWAER", "", "ADRNR"]  # MTEXT repeated, one blank
    grid = _FakeGrid(names, visible=3)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert result.offered_fields == ["MANDT", "MTEXT", "ORT01", "MWAER", "ADRNR"]
    assert grid.VerticalScrollbar.Position == 0  # scrolled back to top


@pytest.mark.anyio
async def test_fill_later_field_still_set_after_an_unapplied_one_and_found_field_adds_no_offered() -> None:
    grid = _FakeGrid(["MANDT", "MTEXT", "ORT01", "MWAER", "ADRNR"], visible=2)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZFAKE": "X", "ADRNR": "1"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert grid.values == {"ADRNR": "1"}  # field after the unapplied one was still searched and set
    assert result.offered_fields == ["MANDT", "MTEXT", "ORT01", "MWAER", "ADRNR"]


@pytest.mark.anyio
async def test_fill_two_unapplied_fields_dedupes_offered_across_scans() -> None:
    grid = _FakeGrid(["MANDT", "MTEXT", "ORT01", "MWAER"], visible=2)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZ1": "X", "ZZZ2": "Y"})

    assert result.unapplied_fields == ["ZZZ1", "ZZZ2"]
    assert result.offered_fields == ["MANDT", "MTEXT", "ORT01", "MWAER"]


@pytest.mark.anyio
async def test_fill_table_control_missing_is_other_error() -> None:
    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(None), {"MANDT": "1"})

    assert result.unapplied_fields == []
    assert result.other_errors == ["SE16N selection criteria table control not found"]
    assert result.offered_fields == []


@pytest.mark.anyio
async def test_fill_non_desktop_backend_is_other_error() -> None:
    result = await _fill_se16n_filters_desktop(MagicMock(), {"MANDT": "1"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert result.other_errors[0].startswith("Filter filling requires DesktopBackend")
```

- [ ] **Step 2: Run, expect FAIL**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k "test_fill_" -x`
Expected: FAIL; the current function returns `list[str]` (e.g. `assert [] == _FilterFillResult()` fails, and the others fail on `.unapplied_fields` with `AttributeError: 'list' object has no attribute ...`).

- [ ] **Step 3: Implement the scan changes**

In `src/sapguimcp/tools/se16_tools.py` replace `_find_and_set_filter_cell`, `_fill_se16n_filters_desktop` and `_set_filter_with_scrolling` (keep `_SE16N_*` constants) with:

```python
def _find_and_set_filter_cell(
    raw_tc: Any, field_upper: str, value: str, visible: int, seen: list[str] | None = None
) -> bool:
    """Scan visible rows of an SE16N table control for a field and set its filter value.

    If ``seen`` is given, the (non-blank) field names read from the visible rows are appended to it,
    so a caller can report which fields SE16N offers when the field is not found.

    Returns True if the field was found and set, False otherwise.
    """
    for r in range(visible):
        try:
            fname_cell = raw_tc.GetCell(r, _SE16N_COL_FIELDNAME)
            text: str = fname_cell.Text
            if seen is not None and text.strip():
                seen.append(text.strip())
            if text.upper() == field_upper:
                raw_tc.GetCell(r, _SE16N_COL_LOW).Text = value
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return False


def _dedupe_keep_order(names: list[str]) -> list[str]:
    """Remove duplicates from ``names`` while keeping first-seen order."""
    return list(dict.fromkeys(names))


async def _fill_se16n_filters_desktop(
    backend: WebGuiBackend | DesktopBackend,
    filters: dict[str, str],
) -> _FilterFillResult:
    """Fill SE16N filter values via the selection criteria table control (COM).

    SE16N uses a GuiTableControl for its selection criteria grid.  Each row
    represents a table field; column 6 holds the technical field name and
    column 2 holds the "From-Value" (Von-Wert) filter input.

    The table control only exposes currently visible rows via ``GetCell``.
    If a field is beyond the visible range, the vertical scrollbar is
    repositioned to bring it into view.

    Fields that cannot be found are reported in ``unapplied_fields``; for them the names of all
    fields the grid offers are collected into ``offered_fields`` (successful fills cost nothing extra).
    """
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return _FilterFillResult(
            other_errors=[f"Filter filling requires DesktopBackend (got {type(backend).__name__})"]
        )

    session = backend.require_session()
    com = backend.com

    def _apply_filters() -> _FilterFillResult:
        result = _FilterFillResult()
        tc = None
        for tc_id in _SE16N_TC_IDS:
            try:
                tc = session.find_by_id(tc_id)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        if tc is None:
            result.other_errors.append("SE16N selection criteria table control not found")
            return result
        # Unwrap Python wrapper to get the raw COM dispatch object
        raw: Any = getattr(tc, "com", getattr(tc, "_com", tc))

        row_count: int = raw.RowCount
        visible: int = raw.VisibleRowCount
        logger.debug("SE16N selection grid", extra={"row_count": row_count, "visible": visible})

        offered: list[str] = []
        for field_name, value in filters.items():
            field_upper = field_name.upper()
            seen: list[str] = []

            # Try visible rows first
            if _find_and_set_filter_cell(raw, field_upper, value, visible, seen):
                logger.info("SE16N desktop filter set", extra={"field_name": field_upper, "value": value})
                continue

            # Field not in visible range - scroll through the table (unless everything is visible already)
            if row_count > visible and _set_filter_with_scrolling(raw, field_upper, value, visible, seen):
                continue

            result.unapplied_fields.append(field_name)
            offered.extend(seen)

        result.offered_fields = _dedupe_keep_order(offered)
        return result

    return await com.run(_apply_filters)


def _set_filter_with_scrolling(
    raw_tc: Any, field_upper: str, value: str, visible: int, seen: list[str] | None = None
) -> bool:
    """Scroll through an SE16N table control to find and set a filter value.

    Field names read while scrolling are appended to ``seen`` (may contain duplicates from overlapping windows).
    """
    scroll_max = raw_tc.VerticalScrollbar.Maximum
    found = False
    for scroll_pos in range(1, scroll_max + 1):
        try:
            raw_tc.VerticalScrollbar.Position = scroll_pos
        except Exception:  # pylint: disable=broad-exception-caught
            break
        if _find_and_set_filter_cell(raw_tc, field_upper, value, visible, seen):
            logger.info(
                "SE16N desktop filter set (scrolled)",
                extra={"field_name": field_upper, "value": value, "scroll": scroll_pos},
            )
            found = True
            break
    # Scroll back to top
    try:
        raw_tc.VerticalScrollbar.Position = 0
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return found
```

Note: `_execute_se16_query_desktop` still treats the return value as `list[str]` at this point, so the old test and the call site are updated in Task 5. To keep the tree consistent in the meantime, do the Task 4 and Task 5 edits before running the full suite; the targeted runs below only exercise the new function.

- [ ] **Step 4: Run, expect PASS**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k "test_fill_" -x`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add src/sapguimcp/tools/se16_tools.py unittests/test_se16_filter_warnings.py
git commit -m "feat: SE16N desktop filter fill reports unapplied and offered fields (#907)"
```

---

## Task 4: Offered-field formatting (cap 50, "+N more") and failure builder

**Files:**

- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `unittests/test_se16_filter_warnings.py`

- [ ] **Step 1: Write failing unit tests**

Add `_filter_fill_failure` and `_format_offered_fields` to the `sapguimcp.tools.se16_tools` import list, then append:

```python
class TestFormatOfferedFields:
    def test_empty_returns_empty_string(self) -> None:
        assert _format_offered_fields([]) == ""

    def test_joins_names(self) -> None:
        assert _format_offered_fields(["A", "B", "C"]) == "A, B, C"

    def test_exactly_fifty_has_no_suffix(self) -> None:
        names = [f"F{i:02d}" for i in range(50)]

        text = _format_offered_fields(names)

        assert text == ", ".join(names)
        assert "more" not in text

    def test_more_than_fifty_is_capped_with_suffix(self) -> None:
        names = [f"F{i:02d}" for i in range(53)]

        text = _format_offered_fields(names)

        assert text == ", ".join(names[:50]) + ", … (+3 more)"
        assert "F50" not in text


class TestFilterFillFailure:
    def test_unapplied_fields_message_and_warnings(self) -> None:
        fill = _FilterFillResult(unapplied_fields=["ZZZ1", "ZZZ2"], offered_fields=["MANDT", "MTEXT"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.success is False
        assert result.error == (
            "Filter field(s) 'ZZZ1', 'ZZZ2' not available as SE16N selection criteria for table T000. "
            "Offered fields: MANDT, MTEXT. "
            "A field can exist in the table without being an SE16N selection field; "
            "use sap-adt `run_query` if available."
        )
        assert result.filter_warnings == [
            "Field 'ZZZ1' not found in SE16N selection criteria",
            "Field 'ZZZ2' not found in SE16N selection criteria",
        ]
        assert result.total_hits == 0
        assert result.rows == []

    def test_empty_offered_list_omits_offered_sentence(self) -> None:
        fill = _FilterFillResult(unapplied_fields=["ZZZ1"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.error is not None
        assert "Offered fields" not in result.error
        assert result.error.startswith("Filter field(s) 'ZZZ1' not available as SE16N selection criteria for table T000.")

    def test_only_other_errors(self) -> None:
        fill = _FilterFillResult(other_errors=["SE16N selection criteria table control not found", "second"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.success is False
        assert result.error == "Could not apply filters: SE16N selection criteria table control not found; second"
        assert result.filter_warnings == ["SE16N selection criteria table control not found", "second"]

    def test_both_kinds_use_unapplied_error_and_append_other_errors_to_warnings(self) -> None:
        fill = _FilterFillResult(unapplied_fields=["ZZZ1"], other_errors=["other"], offered_fields=["MANDT"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.error is not None
        assert result.error.startswith("Filter field(s) 'ZZZ1' not available")
        assert "other" not in result.error
        assert result.filter_warnings == ["Field 'ZZZ1' not found in SE16N selection criteria", "other"]
```

- [ ] **Step 2: Run, expect FAIL**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k "FormatOfferedFields or FilterFillFailure" -x`
Expected: FAIL with `ImportError: cannot import name '_filter_fill_failure'`.

- [ ] **Step 3: Implement**

In `src/sapguimcp/tools/se16_tools.py`, add the constant next to the other `_SE16N_*` constants:

```python
# Maximum number of offered SE16N selection fields named in a filter failure message
_SE16N_MAX_OFFERED_FIELDS = 50
```

and add below `_dedupe_keep_order`:

```python
def _format_offered_fields(offered: list[str]) -> str:
    """Join offered field names, capped at 50 with a '… (+N more)' suffix. Empty list -> empty string."""
    shown = ", ".join(offered[:_SE16N_MAX_OFFERED_FIELDS])
    extra = len(offered) - _SE16N_MAX_OFFERED_FIELDS
    if extra > 0:
        shown += f", … (+{extra} more)"
    return shown


def _filter_fill_failure(fill: _FilterFillResult, table: str, now: datetime) -> SE16Result:
    """Build the failure result for filters that could not be applied (the query is not run)."""
    warnings = [f"Field '{name}' not found in SE16N selection criteria" for name in fill.unapplied_fields]
    warnings.extend(fill.other_errors)
    if not fill.unapplied_fields:
        error = "Could not apply filters: " + "; ".join(fill.other_errors)
        return _empty_failure(error, table, now, filter_warnings=warnings)

    names = ", ".join(f"'{name}'" for name in fill.unapplied_fields)
    error = f"Filter field(s) {names} not available as SE16N selection criteria for table {table}."
    offered = _format_offered_fields(fill.offered_fields)
    if offered:
        error += f" Offered fields: {offered}."
    error += (
        " A field can exist in the table without being an SE16N selection field; use sap-adt `run_query` if available."
    )
    return _empty_failure(error, table, now, filter_warnings=warnings)
```

- [ ] **Step 4: Run, expect PASS**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k "FormatOfferedFields or FilterFillFailure" -x`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```
git add src/sapguimcp/tools/se16_tools.py unittests/test_se16_filter_warnings.py
git commit -m "feat: build SE16 filter failure result with offered fields (#907)"
```

---

## Task 5: Fail before F8 in `_execute_se16_query_desktop` (+ rewrite the old test)

**Files:**

- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `unittests/test_se16_filter_warnings.py`

- [ ] **Step 1: Rewrite/add the failing tests**

In `unittests/test_se16_filter_warnings.py` **replace** `test_execute_se16_query_desktop_returns_filter_warnings` (the whole function, currently asserting `success is True` and F8 pressed) with:

```python
async def _run_desktop_query_with_fill(fill: _FilterFillResult, backend: AsyncMock | None = None) -> tuple[SE16Result, AsyncMock]:
    backend = backend or _make_desktop_backend()
    with patch("sapguimcp.tools.se16_tools._fill_se16n_filters_desktop", new=AsyncMock(return_value=fill)):
        result = await _execute_se16_query_desktop(
            backend,
            table="TSTC",
            filters={"ZZZFAKE": "X", "TCODE": "SE16"},
            max_hits=10,
            now=datetime.now(UTC),
        )
    return result, backend


def _pressed_keys(backend: AsyncMock) -> list[str]:
    return [call.args[0] for call in backend.press_key.await_args_list]


@pytest.mark.anyio
async def test_execute_se16_query_desktop_unapplied_field_fails_before_f8() -> None:
    fill = _FilterFillResult(unapplied_fields=["ZZZFAKE"], offered_fields=["TCODE", "PGMNA"])

    result, backend = await _run_desktop_query_with_fill(fill)

    assert result.success is False
    assert result.error is not None
    assert "'ZZZFAKE'" in result.error
    assert "Offered fields: TCODE, PGMNA." in result.error
    assert result.filter_warnings == ["Field 'ZZZFAKE' not found in SE16N selection criteria"]
    assert result.returned_rows == 0
    assert result.rows == []
    assert _pressed_keys(backend) == ["Enter"]  # F8 never pressed
    backend.read_table.assert_not_awaited()
    backend.get_status_bar.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_se16_query_desktop_only_other_errors_fails_before_f8() -> None:
    fill = _FilterFillResult(other_errors=["SE16N selection criteria table control not found"])

    result, backend = await _run_desktop_query_with_fill(fill)

    assert result.success is False
    assert result.error == "Could not apply filters: SE16N selection criteria table control not found"
    assert result.filter_warnings == ["SE16N selection criteria table control not found"]
    assert _pressed_keys(backend) == ["Enter"]


@pytest.mark.anyio
async def test_execute_se16_query_desktop_both_error_kinds_fails_with_unapplied_error() -> None:
    fill = _FilterFillResult(unapplied_fields=["ZZZFAKE"], other_errors=["other problem"], offered_fields=["TCODE"])

    result, backend = await _run_desktop_query_with_fill(fill)

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("Filter field(s) 'ZZZFAKE' not available as SE16N selection criteria for table TSTC.")
    assert "other problem" not in result.error
    assert result.filter_warnings == ["Field 'ZZZFAKE' not found in SE16N selection criteria", "other problem"]
    assert _pressed_keys(backend) == ["Enter"]


@pytest.mark.anyio
async def test_execute_se16_query_desktop_clean_fill_runs_query_unchanged() -> None:
    result, backend = await _run_desktop_query_with_fill(_FilterFillResult())

    assert result.success is True
    assert result.filter_warnings == []
    assert result.returned_rows == 1
    assert result.rows[0].data["TCODE"] == "SE16"
    assert _pressed_keys(backend) == ["Enter", "F8"]


@pytest.mark.anyio
async def test_execute_se16_query_desktop_status_bar_error_keeps_filter_warnings_param() -> None:
    """The status-bar error path passes filter warnings to _empty_failure (none exist at F8 time today)."""
    backend = _make_desktop_backend()
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="E", message="boom"))

    result, _ = await _run_desktop_query_with_fill(_FilterFillResult(), backend)

    assert result.success is False
    assert result.error == "SE16N error: boom"
    assert result.filter_warnings == []
```

Keep `_run_desktop_query_with_fill`'s signature line within the repo's line length (ruff format will wrap it in Task 8).

- [ ] **Step 2: Run, expect FAIL**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k "test_execute_se16_query_desktop" -x`
Expected: FAIL. The current code stores `fill` in `filter_warnings` (a `_FilterFillResult`, not a list: pydantic validation error) or still presses F8, so `success is False` / `["Enter"]` assertions fail.

- [ ] **Step 3: Implement in `_execute_se16_query_desktop`**

Replace the filter block

```python
    if filters:
        await backend.press_key("Enter")
        await backend.wait(2000)
        filter_errors = await _fill_se16n_filters_desktop(backend, filters)
        if filter_errors:
            filter_warnings = filter_errors
            logger.warning("Some desktop filters could not be applied", extra={"errors": filter_errors})
```

with

```python
    if filters:
        await backend.press_key("Enter")
        await backend.wait(2000)
        fill = await _fill_se16n_filters_desktop(backend, filters)
        if fill.unapplied_fields or fill.other_errors:
            logger.warning(
                "Desktop filters could not be applied, not running the query",
                extra={"unapplied": fill.unapplied_fields, "errors": fill.other_errors},
            )
            return _filter_fill_failure(fill, table, now)
```

and pass the (now always empty, kept for safety) warnings in the status-bar error path:

```python
    if sbar.type == "E":
        return _empty_failure(f"SE16N error: {sbar.message}", table, now, filter_warnings=filter_warnings)
```

`filter_warnings: list[str] = []` at the top of the function stays (it is still used by the "no entries" branch).

- [ ] **Step 4: Run, expect PASS**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -x`
Expected: all tests in the file pass (including the pre-existing `TestSE16ResultFilterWarnings` and `test_file_output_summary_carries_filter_warnings`).

- [ ] **Step 5: Commit**

```
git add src/sapguimcp/tools/se16_tools.py unittests/test_se16_filter_warnings.py
git commit -m "feat: fail sap_se16_query before F8 when a desktop filter cannot be applied (#907)"
```

---

## Task 6: Tool description and docstring

**Files:**

- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `unittests/test_se16_filter_warnings.py`

- [ ] **Step 1: Write failing test**

Append to `unittests/test_se16_filter_warnings.py`:

```python
@pytest.mark.anyio
async def test_tool_description_documents_strict_filter_fields() -> None:
    server = FastMCP("t")
    register_se16_tools(server)
    async with Client(server) as client:
        tools = {t.name: t for t in await client.list_tools()}
    description = tools["sap_se16_query"].description or ""
    assert "desktop" in description.lower()
    assert "not offered by SE16N" in description
    assert "offered fields" in description.lower()
```

- [ ] **Step 2: Run, expect FAIL**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -k test_tool_description_documents_strict_filter_fields -x`
Expected: FAIL (`assert 'not offered by SE16N' in ...`).

- [ ] **Step 3: Implement**

In the `description=(...)` of `sap_se16_query`, insert before the `**Performance:**` line:

```python
            "**Filters (desktop backend):** if a filter field is unknown or not offered by SE16N as a "
            "selection field, the call fails (success=false) without running the query and the error "
            "lists the offered fields. Omit such filters instead.\n\n"
```

and extend the `filters:` line of the docstring Args:

```python
            filters: Optional filter dict {field_name: value} - uses technical field names. On the desktop
                backend, a field that is unknown or not offered by SE16N makes the call fail.
```

- [ ] **Step 4: Run, expect PASS**

`uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -x`
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add src/sapguimcp/tools/se16_tools.py unittests/test_se16_filter_warnings.py
git commit -m "docs: describe strict desktop filter fields in sap_se16_query (#907)"
```

---

## Task 7: Verification - unit suites, lint, types, then the live tests again

**Files:** none (fix-ups only, if a check fails).

- [ ] **Step 1: Unit tests**

```
uv run --group tests python -m pytest unittests/test_se16_filter_warnings.py -x
uv run --group tests python -m pytest unittests/ -k "not integration and not exploration" -x -q
```

Expected: all pass. Also grep for other users of the changed signatures and fix any: `rg "_fill_se16n_filters_desktop|_find_and_set_filter_cell|_set_filter_with_scrolling" src unittests` (only `se16_tools.py` and `test_se16_filter_warnings.py` should appear).

- [ ] **Step 2: Ruff**

```
uv run --group linting ruff format .
uv run --group linting ruff check .
uv run --group linting ruff check --select I .
```

Expected: no remaining findings (format may rewrite long lines in the new tests; re-run the unit tests afterwards).

- [ ] **Step 3: mypy**

`uv run --group type_check mypy --show-error-codes src/sapguimcp --strict`
Expected: `Success: no issues found`.

- [ ] **Step 4: Public-repo hygiene check on the diff**

`git diff main -- . ":(exclude)docs/superpowers"` and confirm: no hostnames, system IDs, transport numbers (`K9...`), `/XXX/` namespaces, client numbers, user names or paths with user names.

- [ ] **Step 5: Live tests again, one at a time (SAP reachable, no other SAP GUI work open)**

```
uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_unknown_field_with_valid_filter_fails -x
uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_only_unknown_field_fails_instead_of_unfiltered_rows -x
uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_real_column_not_offered_by_se16n_fails -x   # only if case 3 was added
uv run --group tests python -m pytest unittests/desktop/test_se16_integration.py -k test_se16_valid_filter_still_returns_filtered_rows -x
```

Expected: all PASS (cases 1/2/3 now red-to-green). Then run the pre-existing SE16 filter tests to guard against regressions, again one at a time: `-k test_se16_single_filter`, `-k test_se16_multiple_filters`, `-k test_se16_wildcard_filter`.

If the multiple-filters test now fails because `PGMNA` is not offered as a selection field on a system, that is the new intended behaviour surfacing: inspect the error's offered list, and only then adjust that test's filter (do not weaken the production check).

- [ ] **Step 6: Commit any fix-ups**

```
git add -A src unittests
git commit -m "chore: lint/format fixes for strict SE16 filter fields (#907)"
```

(Skip if there is nothing to commit.) Do not push or open a PR without asking; the PR workflow (self-review, Copilot review, CI green, ask before merge) applies.
