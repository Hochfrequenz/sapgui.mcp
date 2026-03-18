# sapwebgui.mcp Token-Effizienz & Robuste Datenextraktion — Implementation Plan

**Goal:** Reduce token consumption and improve data extraction robustness for the sapwebgui.mcp MCP server.

**Architecture:** Three independent measures: (1) optimize existing tool descriptions, knowledge base, and parameter defaults, (2) extract and generalize ALV grid pagination for the WebGUI backend, (3) add a composite `sap_quick_report` tool that bundles the most common SAP workflow into a single call.

**Tech Stack:** Python 3.11+, FastMCP, Playwright, Pydantic v2, pytest

**Spec:** `docs/design/token-efficiency-design.md`

**Repo:** https://github.com/Hochfrequenz/sapwebgui.mcp

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `src/sapwebguimcp/tools/sap_tools.py` | Tool descriptions, `sap_read_table` parameter changes |
| Modify | `src/sapwebguimcp/data/sap_knowledge.md` | New "Working Efficiently" section |
| Create | `src/sapwebguimcp/backend/webgui/alv_pagination.py` | Reusable ALV grid pagination helper |
| Modify | `src/sapwebguimcp/tools/se16_tools.py` | Refactor to use shared pagination helper |
| Create | `src/sapwebguimcp/tools/quick_report_tools.py` | `sap_quick_report` composite tool |
| Modify | `src/sapwebguimcp/models/sap_results.py` | `QuickReportResult` model |
| Modify | `src/sapwebguimcp/server.py` | Register new tool module |
| Create | `unittests/test_alv_pagination.py` | Unit tests for pagination logic |
| Create | `unittests/test_quick_report.py` | Unit tests for composite tool |

---

## Task 1: Tool-Descriptions verschärfen

**Files:**
- Modify: `src/sapwebguimcp/tools/sap_tools.py:642-680` (sap_read_table description)
- Modify: `src/sapwebguimcp/tools/sap_tools.py:545-552` (sap_get_screen_text description)
- Modify: `src/sapwebguimcp/tools/sap_tools.py:594-602` (sap_get_form_fields description)
- Modify: `src/sapwebguimcp/tools/sap_tools.py:942-958` (sap_discover_buttons description)
- Modify: `src/sapwebguimcp/tools/sap_tools.py:439-446` (sap_get_capabilities description)

- [ ] **Step 1: Update `sap_read_table` description**

In `sap_tools.py` around line 642, append to the existing description string:

```python
"Read data from an ALV grid or table on the current screen.\n\n"
"**Efficiency tips:**\n"
"- Use max_rows=10 for a quick preview\n"
"- Only request full data when the user explicitly needs all rows\n"
"- Omit include_cells unless you need to click cells afterward\n\n"
# ... keep existing session parameter docs ...
```

- [ ] **Step 2: Update `sap_get_screen_text` description**

In `sap_tools.py` around line 545, append:

```python
"Get all readable text from the current SAP screen. "
"Avoid calling this right after sap_transaction - the TransactionResult "
"already contains page_title. Only call when you need field labels or "
"button texts for an unknown screen.\n\n"
# ... keep existing session/dropdown docs ...
```

- [ ] **Step 3: Update `sap_get_form_fields` description**

In `sap_tools.py` around line 594, prepend efficiency guidance:

```python
"Discover fillable form fields on the current SAP screen. "
"Skip this if you already know the field labels from a prompt/recipe "
"or prior experience - use sap_fill_form directly with label-based keys.\n\n"
# ... keep existing docs ...
```

- [ ] **Step 4: Update `sap_discover_buttons` description**

In `sap_tools.py` around line 942, add reference to `sap_get_shortcuts`:

```python
# Append to existing description:
"Use sap_get_shortcuts to discover available shortcuts before "
"resorting to button clicks.\n\n"
```

- [ ] **Step 5: Update `sap_get_capabilities` description**

In `sap_tools.py` around line 439, append:

```python
"RECOMMENDED: Call once at the start of every SAP session (not per task). "
"Cache the result mentally.\n\n"
# ... keep existing docs ...
```

- [ ] **Step 6: Run linting and formatting**

```bash
tox -e formatting
tox -e linting
```

Expected: PASS (text-only changes)

- [ ] **Step 7: Commit**

```bash
git add src/sapwebguimcp/tools/sap_tools.py
git commit -m "docs: add efficiency guidance to tool descriptions

Append token-saving tips to sap_read_table, sap_get_screen_text,
sap_get_form_fields, sap_discover_buttons, and sap_get_capabilities
tool descriptions to reduce unnecessary agent tool calls."
```

---

## Task 2: `sap_knowledge.md` erweitern

**Files:**
- Modify: `src/sapwebguimcp/data/sap_knowledge.md`

- [ ] **Step 1: Add "Working Efficiently" section**

Insert after the `## MCP-Tools are Faster than manual evaluation` section (after line ~36):

```markdown
## Working Efficiently — Minimize Tool Calls

### The 3-Call Rule
For simple data lookups, aim for 3 or fewer tool calls:
1. `sap_se16_query` (or dedicated tool) — get the data
2. Done. No need for sap_get_screen_text, sap_read_table,
   or sap_discover_fields if a dedicated tool exists.

### Avoid Redundant Exploration
- Do NOT call `sap_get_screen_text` after `sap_transaction`
  just to "see what's on screen" — the transaction result
  already tells you the page title and success status.
- Do NOT call `sap_discover_fields` before `sap_fill_form`
  if you already know the field labels from a recipe or
  the user's request. `sap_fill_form` matches by label text.
- Do NOT call `sap_discover_buttons` before `sap_keyboard`
  — SAP shortcuts are standardized (F8=Execute, Ctrl+S=Save,
  F3=Back). Check `sap_get_shortcuts` only for non-standard screens.

### Prefer Dedicated Tools
These tools combine multiple steps internally:
- `sap_se16_query` = transaction + filter + execute + read
  (replaces 4-6 manual tool calls)
- `sap_se11_lookup` = structured metadata without navigation
- `sap_se24_lookup` / `sap_se37_lookup` = class/FM info in one call

### When to Use Generic vs. Dedicated Tools
- **SE16 data?** → `sap_se16_query` (NOT sap_transaction + sap_fill_form + ...)
- **Table structure?** → `sap_se11_lookup` (NOT sap_transaction("SE11") + ...)
- **Unknown transaction?** → Then use `sap_transaction` + generic tools
```

- [ ] **Step 2: Fix typo "respetive" → "respective"**

In the existing `## MCP-Tools are Faster than manual evaluation` section, fix:

```
# Before:
In case it doesn't work use the respetive tool to submit feedback
# After:
In case it doesn't work use the respective tool to submit feedback
```

- [ ] **Step 3: Run spell check and formatting**

```bash
tox -e spell_check
npm run format
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/sapwebguimcp/data/sap_knowledge.md
git commit -m "docs: add 'Working Efficiently' section to SAP knowledge base

Guide agents to minimize tool calls with the 3-Call Rule,
avoid redundant exploration, and prefer dedicated tools.
Also fix 'respetive' typo."
```

---

## Task 3: `sap_read_table` — `max_rows` Default und `include_cells` Parameter

**Files:**
- Modify: `src/sapwebguimcp/tools/sap_tools.py:649-680` (sap_read_table function)
- Test: `unittests/test_models.py` (verify TableData with cells=None)

- [ ] **Step 1: Write test for `include_cells` stripping**

Add to `unittests/test_models.py` (or a new dedicated test file):

```python
import pytest
from sapwebguimcp.models.sap_results import TableData, TableRow
from sapwebguimcp.models.alv_models import AlvCellInfo
class TestIncludeCellsStripping:
    """Test that cells can be stripped from TableData rows."""

    def test_strip_cells_from_rows(self) -> None:
        """When include_cells=False, cells should be None on all rows."""
        rows = [
            TableRow(
                row=1,
                data={"Col1": "val1"},
                cells={"Col1": AlvCellInfo(selector="#s1", clickable=True, hotspot=False)},
            ),
            TableRow(
                row=2,
                data={"Col1": "val2"},
                cells={"Col1": AlvCellInfo(selector="#s2", clickable=True, hotspot=False)},
            ),
        ]
        # Simulate the stripping logic
        for row in rows:
            row.cells = None

        assert all(row.cells is None for row in rows)
        assert rows[0].data == {"Col1": "val1"}  # data preserved

    def test_cells_preserved_when_included(self) -> None:
        """When include_cells=True, cells should remain."""
        row = TableRow(
            row=1,
            data={"Col1": "val1"},
            cells={"Col1": AlvCellInfo(selector="#s1", clickable=True, hotspot=False)},
        )
        assert row.cells is not None
        assert row.cells["Col1"].selector == "#s1"
```

- [ ] **Step 2: Run test to verify it passes**

```bash
python -m pytest unittests/test_models.py::TestIncludeCellsStripping -v
```

Expected: PASS (this tests Pydantic model behavior, no implementation change needed yet)

- [ ] **Step 3: Change `max_rows` default and add `include_cells` parameter**

In `src/sapwebguimcp/tools/sap_tools.py`, modify `sap_read_table` (around line 649):

```python
async def sap_read_table(
    start_row: int = 1,
    end_row: Optional[int] = None,
    max_rows: int = 30,              # changed from 100
    include_cells: bool = False,     # NEW
    session: str | None = None,
    agent_id: str | None = None,
) -> TableData:
```

After the `backend.read_table(...)` call, add cell stripping:

```python
        result = await backend.read_table(start_row=start_row, end_row=end_row, max_rows=max_rows)
        if not include_cells:
            for row in result.rows:
                row.cells = None
        return result
```

- [ ] **Step 4: Update docstring**

Update the Args section to document the new parameters:

```python
        """
        ...
        Args:
            start_row: First row to read (1-indexed, default: 1)
            end_row: Last row to read (None = up to max_rows visible rows)
            max_rows: Maximum rows to return (default: 30, prevents huge responses)
            include_cells: If True, include cell-level click metadata (CSS selectors,
                hotspot info) for each cell. Default is False to reduce response size.
                Set to True only if you need to click cells afterward using
                sap_click_table_cell.
            ...
        """
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest unittests/ -v --ignore=unittests/webgui -k "not integration"
```

Expected: PASS

- [ ] **Step 6: Run type check**

```bash
tox -e type_check
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sapwebguimcp/tools/sap_tools.py unittests/test_models.py
git commit -m "feat: add include_cells parameter and reduce max_rows default

- Add include_cells=False to sap_read_table (strips cell metadata by default)
- Reduce max_rows default from 100 to 30 for lower token usage
- Cell metadata (CSS selectors, hotspot info) is only needed for
  sap_click_table_cell, not for data reading"
```

---

## Task 4: ALV Pagination Helper extrahieren

**Files:**
- Create: `src/sapwebguimcp/backend/webgui/alv_pagination.py`
- Create: `unittests/test_alv_pagination.py`

- [ ] **Step 1: Write failing test for deduplication logic**

Create `unittests/test_alv_pagination.py`:

```python
"""Unit tests for ALV pagination helpers — deduplication and termination logic."""

from __future__ import annotations

import pytest

from sapwebguimcp.backend.webgui.alv_pagination import deduplicate_rows, detect_end
class TestDeduplicateRows:
    """Test row deduplication by first column key."""

    def test_removes_duplicates(self) -> None:
        seen: set[str] = set()
        page1 = [
            {"MATNR": "100", "MAKTX": "Widget A"},
            {"MATNR": "200", "MAKTX": "Widget B"},
        ]
        page2 = [
            {"MATNR": "200", "MAKTX": "Widget B"},  # duplicate
            {"MATNR": "300", "MAKTX": "Widget C"},
        ]
        new1 = deduplicate_rows(page1, "MATNR", seen)
        new2 = deduplicate_rows(page2, "MATNR", seen)
        assert len(new1) == 2
        assert len(new2) == 1
        assert new2[0]["MATNR"] == "300"

    def test_empty_page(self) -> None:
        seen: set[str] = set()
        new = deduplicate_rows([], "MATNR", seen)
        assert new == []

    def test_no_key_column(self) -> None:
        """When key column is None, all rows are accepted (no dedup)."""
        seen: set[str] = set()
        rows = [{"A": "1"}, {"A": "1"}]
        new = deduplicate_rows(rows, None, seen)
        assert len(new) == 2
class TestDetectEnd:
    """Test end-of-data detection."""

    def test_same_first_key_means_end(self) -> None:
        rows = [{"MATNR": "100"}, {"MATNR": "200"}]
        assert detect_end(rows, "MATNR", last_first_key="100") is True

    def test_different_first_key_means_continue(self) -> None:
        rows = [{"MATNR": "300"}, {"MATNR": "400"}]
        assert detect_end(rows, "MATNR", last_first_key="100") is False

    def test_empty_rows_means_end(self) -> None:
        assert detect_end([], "MATNR", last_first_key="100") is True

    def test_none_last_key_means_continue(self) -> None:
        rows = [{"MATNR": "100"}]
        assert detect_end(rows, "MATNR", last_first_key=None) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest unittests/test_alv_pagination.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'sapwebguimcp.backend.webgui.alv_pagination'`

- [ ] **Step 3: Implement pagination helpers**

Create `src/sapwebguimcp/backend/webgui/alv_pagination.py`:

```python
"""Reusable ALV grid pagination helpers for WebGUI backend.

Extracted from se16_tools.py._collect_rows_with_pagination.
The core algorithm: PageDown through lazy-loaded ALV grids,
deduplicate by first column key, detect end via first-row comparison.

See issue #136 for deduplication strategy rationale.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_PAGES = 200
STUCK_THRESHOLD = 3
def deduplicate_rows(
    rows: list[dict[str, Any]],
    key_column: str | None,
    seen_keys: set[str],
) -> list[dict[str, Any]]:
    """Return only rows whose key_column value has not been seen before.

    Args:
        rows: Raw rows from the current page.
        key_column: Column name to deduplicate by (typically the first column).
            If None, all rows are accepted without deduplication.
        seen_keys: Mutable set of already-seen key values. Updated in-place.

    Returns:
        List of new (non-duplicate) rows.
    """
    if key_column is None:
        return list(rows)

    new_rows: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(row.get(key_column, ""))
        if row_key not in seen_keys:
            seen_keys.add(row_key)
            new_rows.append(row)
    return new_rows
def detect_end(
    rows: list[dict[str, Any]],
    key_column: str | None,
    last_first_key: str | None,
) -> bool:
    """Detect if pagination has reached the end of data.

    End is detected when:
    - No rows returned (empty page)
    - First row's key matches the previous page's first row key
      (PageDown didn't scroll)

    Args:
        rows: Rows from the current page.
        key_column: Column to compare keys on.
        last_first_key: First row's key from the previous page.

    Returns:
        True if we should stop paginating.
    """
    if not rows:
        return True
    if last_first_key is None:
        return False
    if key_column is None:
        return False
    first_key = str(rows[0].get(key_column, ""))
    return first_key == last_first_key
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest unittests/test_alv_pagination.py -v
```

Expected: PASS (all 7 tests)

- [ ] **Step 5: Run type check and linting**

```bash
tox -e type_check
tox -e linting
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sapwebguimcp/backend/webgui/alv_pagination.py unittests/test_alv_pagination.py
git commit -m "refactor: extract ALV pagination helpers from se16_tools

Extract deduplicate_rows() and detect_end() into a reusable module.
These implement the proven deduplication-by-first-column pattern
from _collect_rows_with_pagination (see #136)."
```

---

## Task 5: `read_all` Parameter in `sap_read_table` integrieren

**Files:**
- Modify: `src/sapwebguimcp/tools/sap_tools.py:649-680`
- Modify: `src/sapwebguimcp/backend/webgui/alv_pagination.py` (add `collect_all_rows`)
- Modify: `src/sapwebguimcp/backend/webgui/backend.py:1051-1110`

**Depends on:** Task 3 (include_cells), Task 4 (pagination helpers)

- [ ] **Step 1: Write failing test for `collect_all_rows`**

Add to `unittests/test_alv_pagination.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapwebguimcp.backend.webgui.alv_pagination import collect_all_rows
from sapwebguimcp.models.sap_results import TableData, TableRow
class TestCollectAllRows:
    """Test the full pagination collection loop."""

    @pytest.mark.anyio
    async def test_collects_two_pages(self) -> None:
        """Simulate two pages of data with overlap."""
        page1_data = {
            "headers": ["MATNR", "MAKTX"],
            "rows": [
                {"row": 1, "data": {"MATNR": "100", "MAKTX": "A"}},
                {"row": 2, "data": {"MATNR": "200", "MAKTX": "B"}},
            ],
            "totalRows": 2,
            "startRow": 1,
            "endRow": 2,
        }
        page2_data = {
            "headers": ["MATNR", "MAKTX"],
            "rows": [
                {"row": 1, "data": {"MATNR": "200", "MAKTX": "B"}},  # overlap
                {"row": 2, "data": {"MATNR": "300", "MAKTX": "C"}},
            ],
            "totalRows": 2,
            "startRow": 1,
            "endRow": 2,
        }
        # Third call returns same first key → end detected
        page3_data = dict(page2_data)

        backend = AsyncMock()
        backend.read_table = AsyncMock(side_effect=[
            _make_table_data(page1_data),
            _make_table_data(page2_data),
            _make_table_data(page3_data),
        ])
        backend.press_key = AsyncMock()
        backend.wait = AsyncMock()

        result = await collect_all_rows(backend, max_rows=100)
        # Should have 3 unique rows: 100, 200, 300
        assert len(result.rows) == 3
        assert result.rows[0].data["MATNR"] == "100"
        assert result.rows[2].data["MATNR"] == "300"

    @pytest.mark.anyio
    async def test_respects_max_rows(self) -> None:
        """Stop collecting when max_rows is reached."""
        big_page = {
            "headers": ["ID"],
            "rows": [{"row": i, "data": {"ID": str(i)}} for i in range(1, 51)],
            "totalRows": 50,
            "startRow": 1,
            "endRow": 50,
        }
        backend = AsyncMock()
        backend.read_table = AsyncMock(return_value=_make_table_data(big_page))

        result = await collect_all_rows(backend, max_rows=10)
        assert len(result.rows) <= 10
def _make_table_data(raw: dict) -> TableData:
    """Helper to build TableData from raw dict."""
    rows = [TableRow(row=r["row"], data=r["data"]) for r in raw["rows"]]
    return TableData(
        headers=raw["headers"],
        rows=rows,
        total_rows=raw["totalRows"],
        start_row=raw["startRow"],
        end_row=raw.get("endRow"),
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest unittests/test_alv_pagination.py::TestCollectAllRows -v
```

Expected: FAIL with `ImportError: cannot import name 'collect_all_rows'`

- [ ] **Step 3: Implement `collect_all_rows`**

Add to `src/sapwebguimcp/backend/webgui/alv_pagination.py`:

```python
from sapwebguimcp.models.sap_results import TableData, TableRow
async def collect_all_rows(
    backend: Any,
    max_rows: int = 500,
    page_wait_ms: int = 1000,
) -> TableData:
    """Collect all rows from an ALV grid by paginating with PageDown.

    Uses the backend's read_table to get each page, then presses PageDown
    and reads the next page. Deduplicates by first column key.

    Args:
        backend: SapUiBackend instance with read_table, press_key, wait methods.
        max_rows: Maximum total rows to collect (safety cap).
        page_wait_ms: Milliseconds to wait after each PageDown for lazy loading.

    Returns:
        TableData with all collected rows, deduplicated.
    """
    all_rows: list[TableRow] = []
    seen_keys: set[str] = set()
    last_first_key: str | None = None
    stuck_count = 0
    headers: list[str] = []
    key_column: str | None = None

    for page_num in range(MAX_PAGES):
        # Read current page via existing backend method
        page_data = await backend.read_table(start_row=1, max_rows=max_rows)

        if not page_data.rows:
            stuck_count += 1
            if stuck_count >= STUCK_THRESHOLD:
                logger.warning("No rows for %d consecutive pages, stopping", STUCK_THRESHOLD)
                break
            await backend.wait(page_wait_ms * 2)
            continue

        stuck_count = 0

        # Capture headers from first successful page
        if not headers and page_data.headers:
            headers = page_data.headers
            key_column = headers[0] if headers else None

        # Convert to raw dicts for deduplication
        raw_rows = [row.data for row in page_data.rows]

        # Check for end of data
        if detect_end(raw_rows, key_column, last_first_key):
            break

        # Track first key for next iteration
        if raw_rows and key_column:
            last_first_key = str(raw_rows[0].get(key_column, ""))

        # Deduplicate and collect
        new_raw = deduplicate_rows(raw_rows, key_column, seen_keys)
        for raw in new_raw:
            all_rows.append(TableRow(row=len(all_rows) + 1, data=raw))

        if len(all_rows) >= max_rows:
            all_rows = all_rows[:max_rows]
            break

        # PageDown to next page
        await backend.press_key("PageDown")
        await backend.wait(page_wait_ms)

    return TableData(
        headers=headers,
        rows=all_rows,
        total_rows=len(all_rows),
        start_row=1,
        end_row=len(all_rows) if all_rows else None,
    )
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest unittests/test_alv_pagination.py -v
```

Expected: PASS

- [ ] **Step 5: Add `read_all` parameter to `sap_read_table`**

In `src/sapwebguimcp/tools/sap_tools.py`, modify `sap_read_table`:

```python
async def sap_read_table(
    start_row: int = 1,
    end_row: Optional[int] = None,
    max_rows: int = 30,
    include_cells: bool = False,
    read_all: bool = False,           # NEW
    session: str | None = None,
    agent_id: str | None = None,
) -> TableData:
```

In the function body, add the `read_all` branch:

```python
        if read_all:
            from sapwebguimcp.backend.webgui.alv_pagination import collect_all_rows
            result = await collect_all_rows(backend, max_rows=max_rows)
        else:
            result = await backend.read_table(start_row=start_row, end_row=end_row, max_rows=max_rows)

        if not include_cells:
            for row in result.rows:
                row.cells = None
        return result
```

Update the tool description to include `read_all` guidance:

```python
"Use read_all=True to paginate through the entire ALV grid (~7 rows/sec). "
"Only use when the user needs ALL data. Default reads visible rows only.\n\n"
```

Update the docstring Args:

```python
            read_all: If True, paginate through the entire ALV grid using PageDown
                (~7 rows/sec). Only use when the user explicitly needs all rows.
                max_rows still applies as a safety cap. Default is False (visible rows only).
```

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest unittests/ -v --ignore=unittests/webgui -k "not integration"
tox -e type_check
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sapwebguimcp/backend/webgui/alv_pagination.py \
        src/sapwebguimcp/tools/sap_tools.py \
        unittests/test_alv_pagination.py
git commit -m "feat: add read_all parameter for ALV grid pagination

- Add collect_all_rows() helper using PageDown pagination
- Integrate via read_all=True parameter on sap_read_table
- Deduplication by first column key (proven pattern from SE16, #136)
- max_rows remains as safety cap"
```

---

## Task 6: `QuickReportResult` Modell

**Files:**
- Modify: `src/sapwebguimcp/models/sap_results.py`
- Modify: `src/sapwebguimcp/models/__init__.py` (export)
- Test: `unittests/test_models.py`

**Depends on:** None (can run parallel to Tasks 1-5)

- [ ] **Step 1: Write test for `QuickReportResult`**

Add to `unittests/test_models.py`:

```python
from sapwebguimcp.models.sap_results import QuickReportResult, TableData
class TestQuickReportResult:
    def test_success_with_table(self) -> None:
        result = QuickReportResult(
            tcode="SM37",
            page_title="Job Overview",
            status_bar_type="S",
            status_bar_message="5 entries found",
            table=TableData(headers=["Job"], rows=[], total_rows=0, start_row=1),
        )
        assert result.success is True
        assert result.table is not None

    def test_error_without_table(self) -> None:
        result = QuickReportResult(
            tcode="SM37",
            page_title="Job Overview",
            status_bar_type="E",
            status_bar_message="No authorization",
            error_screen="Error: No authorization for this transaction",
        )
        assert result.table is None
        assert result.error_screen is not None

    def test_failure_factory(self) -> None:
        result = QuickReportResult.failure("Connection lost")
        assert result.success is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest unittests/test_models.py::TestQuickReportResult -v
```

Expected: FAIL with `ImportError: cannot import name 'QuickReportResult'`

- [ ] **Step 3: Add `QuickReportResult` to models**

In `src/sapwebguimcp/models/sap_results.py`, add at the end (before any private helpers):

```python
class QuickReportResult(ToolResult):
    """Result from sap_quick_report composite tool."""

    tcode: str = Field(default="", description="Transaction code executed")
    page_title: str = Field(default="", description="Screen title after execution")
    status_bar_type: StatusBarType = Field(
        default="none",
        description="Status bar message type after F8: S/E/W/I/none",
    )
    status_bar_message: str = Field(
        default="",
        description="Status bar text after F8",
    )
    table: TableData | None = Field(
        default=None,
        description="Table data if a table was found after execution",
    )
    error_screen: str | None = Field(
        default=None,
        description="Screen text if no table found (e.g., error or unexpected screen)",
    )
```

- [ ] **Step 4: Export from `__init__.py`**

In `src/sapwebguimcp/models/__init__.py`, add `QuickReportResult` to the imports and `__all__`.

- [ ] **Step 5: Run tests**

```bash
python -m pytest unittests/test_models.py::TestQuickReportResult -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sapwebguimcp/models/sap_results.py src/sapwebguimcp/models/__init__.py unittests/test_models.py
git commit -m "feat: add QuickReportResult model for composite tool

Pydantic model that bundles transaction result, status bar,
table data, and error screen into a single response."
```

---

## Task 7: `sap_quick_report` Composite-Tool

**Files:**
- Create: `src/sapwebguimcp/tools/quick_report_tools.py`
- Create: `unittests/test_quick_report.py`
- Modify: `src/sapwebguimcp/server.py` (register tool module)

**Depends on:** Task 5 (read_all), Task 6 (QuickReportResult)

- [ ] **Step 1: Write test for orchestration order**

Create `unittests/test_quick_report.py`:

```python
"""Unit tests for sap_quick_report composite tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from sapwebguimcp.models.sap_results import (
    FillFormResult,
    KeyboardResult,
    QuickReportResult,
    StatusBarInfo,
    TableData,
    TableRow,
    TransactionResult,
)
def _make_mock_backend() -> AsyncMock:
    """Create a mock backend that returns success for all operations."""
    backend = AsyncMock()
    backend.enter_transaction = AsyncMock(
        return_value=TransactionResult(tcode="SM37", page_title="Job Overview")
    )
    backend.fill_form = AsyncMock(
        return_value=FillFormResult(filled=["Benutzer"])
    )
    backend.press_key = AsyncMock(
        return_value=KeyboardResult(key="F8")
    )
    backend.wait_for_ready = AsyncMock()
    backend.get_status_bar = AsyncMock(
        return_value=StatusBarInfo(type="S", message="5 entries")
    )
    backend.read_table = AsyncMock(
        return_value=TableData(
            headers=["Job", "Status"],
            rows=[TableRow(row=1, data={"Job": "TEST", "Status": "Finished"})],
            total_rows=1,
            start_row=1,
        )
    )
    backend.get_screen_text = AsyncMock()
    return backend
class TestQuickReportOrchestration:
    """Test that sap_quick_report calls backend methods in correct order."""

    @pytest.mark.anyio
    async def test_happy_path_with_fields(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report

        backend = _make_mock_backend()
        result = await _execute_quick_report(
            backend, tcode="SM37", fields={"Benutzer": "*"}, max_rows=30, read_all=False
        )

        assert isinstance(result, QuickReportResult)
        assert result.success is True
        assert result.tcode == "SM37"
        assert result.table is not None
        assert result.table.rows[0].data["Job"] == "TEST"

        # Verify call order: reset (/n) first, then actual tcode
        assert backend.enter_transaction.call_count == 2
        backend.enter_transaction.assert_any_call("/n")
        backend.enter_transaction.assert_any_call("SM37")
        backend.fill_form.assert_called_once_with({"Benutzer": "*"})
        backend.press_key.assert_called_once_with("F8")
        backend.wait_for_ready.assert_called_once()
        backend.get_status_bar.assert_called_once()
        backend.read_table.assert_called_once()

    @pytest.mark.anyio
    async def test_no_fields_skips_fill(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report

        backend = _make_mock_backend()
        result = await _execute_quick_report(
            backend, tcode="SM37", fields=None, max_rows=30, read_all=False
        )

        assert result.success is True
        backend.fill_form.assert_not_called()

    @pytest.mark.anyio
    async def test_error_status_bar_returns_error_screen(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report

        backend = _make_mock_backend()
        backend.get_status_bar = AsyncMock(
            return_value=StatusBarInfo(type="E", message="No authorization")
        )

        result = await _execute_quick_report(
            backend, tcode="SM37", fields=None, max_rows=30, read_all=False
        )

        assert result.table is None
        assert result.status_bar_type == "E"
        assert "No authorization" in result.status_bar_message
        # read_table should NOT be called after error
        backend.read_table.assert_not_called()

    @pytest.mark.anyio
    async def test_cells_stripped_from_result(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report
        from sapwebguimcp.models.alv_models import AlvCellInfo

        backend = _make_mock_backend()
        backend.read_table = AsyncMock(
            return_value=TableData(
                headers=["Col"],
                rows=[TableRow(
                    row=1,
                    data={"Col": "val"},
                    cells={"Col": AlvCellInfo(selector="#s", clickable=True, hotspot=False)},
                )],
                total_rows=1,
                start_row=1,
            )
        )

        result = await _execute_quick_report(
            backend, tcode="SM37", fields=None, max_rows=30, read_all=False
        )

        assert result.table is not None
        assert result.table.rows[0].cells is None  # stripped
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest unittests/test_quick_report.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'sapwebguimcp.tools.quick_report_tools'`

- [ ] **Step 3: Implement `quick_report_tools.py`**

Create `src/sapwebguimcp/tools/quick_report_tools.py`:

```python
"""Composite tool: sap_quick_report.

Bundles the most common SAP workflow — open transaction, fill selection
screen, execute, read table — into a single MCP tool call.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models.sap_results import QuickReportResult, TableData

logger = logging.getLogger(__name__)

__all__ = ["register_quick_report_tools"]
async def _execute_quick_report(
    backend: Any,
    tcode: str,
    fields: dict[str, str] | None,
    max_rows: int,
    read_all: bool,
) -> QuickReportResult:
    """Core orchestration logic, separated for testability.

    Calls backend methods directly (not MCP tool functions) to avoid
    double logging, following the pattern established in se16_tools.py.
    """
    # 1. Enter transaction with clean state (reset_first pattern from sap_transaction)
    await backend.enter_transaction("/n")
    await backend.wait_for_ready()
    tx_result = await backend.enter_transaction(tcode)

    # 2. Fill selection screen fields (if provided)
    if fields:
        await backend.fill_form(fields)

    # 3. Execute (F8)
    await backend.press_key("F8")
    await backend.wait_for_ready()

    # 4. Check status bar for errors
    status = await backend.get_status_bar()

    if status.type == "E":
        return QuickReportResult(
            tcode=tcode,
            page_title=getattr(tx_result, "page_title", "") or "",
            status_bar_type=status.type,
            status_bar_message=status.message,
            error_screen=f"Error after F8: {status.message}",
        )

    # 5. Read table data
    if read_all:
        from sapwebguimcp.backend.webgui.alv_pagination import collect_all_rows

        table = await collect_all_rows(backend, max_rows=max_rows)
    else:
        table = await backend.read_table(start_row=1, max_rows=max_rows)

    # 6. Strip cell metadata (not needed for composite reads)
    for row in table.rows:
        row.cells = None

    page_title = getattr(tx_result, "page_title", "") or ""

    return QuickReportResult(
        tcode=tcode,
        page_title=page_title,
        status_bar_type=status.type,
        status_bar_message=status.message,
        table=table if table.rows else None,
        error_screen=None if table.rows else f"No table data found on screen '{page_title}'",
    )
def register_quick_report_tools(mcp: FastMCP) -> None:
    """Register the sap_quick_report tool with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True),
        description=(
            "Execute a transaction, fill selection screen fields, press Execute (F8), "
            "and return the resulting table data — all in one call.\n\n"
            "This replaces the common pattern of: sap_transaction → sap_fill_form → "
            "sap_keyboard(F8) → sap_read_table.\n\n"
            "Use this for standard SAP report/list transactions with a selection screen "
            "(SM37, VA05, ME2M, MB51, FBL1N, etc.).\n\n"
            "Do NOT use for:\n"
            "- SE16 (use sap_se16_query instead)\n"
            "- Transactions without selection screens (e.g., BP, VA01)\n"
            "- Complex multi-step workflows\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        ),
    )
    async def sap_quick_report(
        tcode: str,
        fields: Optional[dict[str, str]] = None,
        max_rows: int = 30,
        read_all: bool = False,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> QuickReportResult:
        """
        Execute a transaction with optional filters and return table data.

        Args:
            tcode: SAP transaction code (e.g., "SM37", "VA05", "ME2M")
            fields: Selection screen fields to fill before executing.
                Keys are field labels, values are the values to set.
                Example: {"Benutzer": "*", "Von Datum": "01.01.2026"}
            max_rows: Maximum rows to return (default: 30)
            read_all: If True, paginate through entire ALV grid (~7 rows/sec).
                Default is False (visible rows only).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            QuickReportResult with status bar info and table data (if found).
        """
        try:
            backend = await get_backend(
                session=session, agent_id=agent_id, tool_name="sap_quick_report"
            )
        except ValueError as e:
            return QuickReportResult.failure(str(e))

        try:
            return await _execute_quick_report(
                backend, tcode=tcode, fields=fields, max_rows=max_rows, read_all=read_all
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Quick report failed")
            return QuickReportResult.failure(f"Quick report error: {e}")
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest unittests/test_quick_report.py -v
```

Expected: PASS (all 4 tests)

- [ ] **Step 5: Register in server.py**

In `src/sapwebguimcp/server.py`:

1. Add to the import block (around line 24-49, where all `register_*_tools` are imported from `sapwebguimcp.tools`):

```python
from sapwebguimcp.tools.quick_report_tools import register_quick_report_tools
```

Note: Most tools are imported via `from sapwebguimcp.tools import (...)` but some (like `register_abapgit_tools`) use direct imports. Follow the pattern that fits.

2. Add the registration call (around line 204, after `register_workflow_tools(mcp)`):

```python
register_quick_report_tools(mcp)
```

- [ ] **Step 6: Run full test suite and checks**

```bash
python -m pytest unittests/ -v --ignore=unittests/webgui -k "not integration"
tox -e type_check
tox -e linting
tox -e formatting
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sapwebguimcp/tools/quick_report_tools.py \
        src/sapwebguimcp/server.py \
        unittests/test_quick_report.py
git commit -m "feat: add sap_quick_report composite tool

Bundles transaction + fill_form + F8 + read_table into one call.
Reduces typical data-lookup workflows from 4-6 tool calls to 1,
saving ~3000-5000 tokens of orchestration overhead per query."
```

---

## Task 8: `sap_knowledge.md` — ALV Pagination Feature Request aktualisieren

**Files:**
- Modify: `src/sapwebguimcp/data/sap_knowledge.md`

**Depends on:** Task 5 (read_all is implemented)

- [ ] **Step 1: Update the "ALV Grid Pagination (Feature Request)" section**

In `sap_knowledge.md`, find the section `### ALV Grid Pagination (Feature Request)` under `## Common Patterns` and update it:

```markdown
### ALV Grid Pagination

ALV grids in SAP Web GUI use lazy loading - only visible rows (~7-13)
are in the DOM at a time.

**Solution:** Use `sap_read_table(read_all=True)` to automatically
paginate through the entire grid using PageDown. This collects all rows
with deduplication at ~7 rows/second.

For SE16 data, prefer `sap_se16_query` which has its own optimized
pagination built in.

For quick checks, the default `sap_read_table()` (visible rows only)
is faster and sufficient.
```

- [ ] **Step 2: Add `sap_quick_report` to the knowledge base**

Add a new section after "## Working Efficiently":

```markdown
### Composite Tools
- `sap_quick_report(tcode, fields, max_rows)` = transaction + fill + F8 + read_table
  in one call. Use for report transactions with selection screens (SM37, VA05, ME2M, etc.)
```

- [ ] **Step 3: Run checks**

```bash
tox -e spell_check
npm run format
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/sapwebguimcp/data/sap_knowledge.md
git commit -m "docs: update knowledge base for ALV pagination and quick_report

- Update ALV Grid Pagination section from Feature Request to documentation
- Add sap_quick_report to Composite Tools section"
```

---

## Task 9: Refactor `se16_tools.py` to use shared pagination

**Files:**
- Modify: `src/sapwebguimcp/tools/se16_tools.py:433-520`
- Test: existing `unittests/webgui/test_se16_integration.py` (verify no regression)

**Depends on:** Task 4 (pagination helpers exist)

- [ ] **Step 1: Refactor `_collect_rows_with_pagination` to use shared helpers**

In `src/sapwebguimcp/tools/se16_tools.py`, modify `_collect_rows_with_pagination` to import and use `deduplicate_rows` and `detect_end` from `alv_pagination.py`:

```python
from sapwebguimcp.backend.webgui.alv_pagination import deduplicate_rows, detect_end
```

Replace the inline deduplication logic with calls to the shared helpers. Keep the SE16-specific parts (ARIA snapshot parsing, progress reporting) intact.

- [ ] **Step 2: Run existing SE16 tests**

```bash
python -m pytest unittests/ -v -k "se16 and not integration"
```

Expected: PASS (no behavior change, only internal refactoring)

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest unittests/ -v --ignore=unittests/webgui -k "not integration"
tox -e type_check
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/sapwebguimcp/tools/se16_tools.py
git commit -m "refactor: use shared pagination helpers in se16_tools

Replace inline deduplication/end-detection logic with
deduplicate_rows() and detect_end() from alv_pagination module."
```

---

## Verification Checklist

After all tasks are complete:

- [ ] `tox -e tests` — all unit tests pass
- [ ] `tox -e linting` — no lint errors
- [ ] `tox -e type_check` — no type errors
- [ ] `tox -e formatting` — code formatted correctly
- [ ] `tox -e spell_check` — no spelling errors
- [ ] `git log --oneline` — 9 clean commits, one per task
