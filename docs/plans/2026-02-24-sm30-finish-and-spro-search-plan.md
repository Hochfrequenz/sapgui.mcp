# SM30 Finish + SPRO Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the SM30 tool (merge main, apply quality fixes) and implement a new SPRO Search tool for finding IMG customizing activities by keyword.

**Architecture:** SM30 is already implemented on `feat/sm30-tool` — needs merge with main and the same quality fixes applied to SM37/SLG1/ST22/SE09 (session threading, strict typing, bilingual patterns). SPRO Search is a new tool that navigates to SPRO, uses the IMG search function, and parses results into structured data.

**Tech Stack:** Python 3.12, Pydantic v2, FastMCP, Playwright (ARIA snapshots), pytest-anyio

---

## Phase 1: SM30 Finish (Existing Branch)

### Task 1: Merge main into feat/sm30-tool

**Step 1:** Check out the branch and merge main

```bash
cd /c/github/sapgui.mcp
git checkout feat/sm30-tool
git fetch origin main
git merge origin/main
```

**Step 2:** Resolve merge conflicts. Expected conflicts in:

- `src/sapguimcp/lang.py` — Keep both: existing SM30 constants + new SM37/SLG1/ST22/SE09 constants from main
- `src/sapguimcp/models/__init__.py` — Keep both: SM30 imports + SM37/SLG1/ST22/SE09 imports from main
- `src/sapguimcp/tools/__init__.py` — Keep both: SM30 registration + other tool registrations from main
- `src/sapguimcp/server.py` — Keep both: SM30 registration + other registrations from main
- `src/sapguimcp/parsers/__init__.py` — Keep both

**Step 3:** Commit the merge

```bash
git add -A
git commit -m "merge: update feat/sm30-tool with latest main"
```

**Step 4:** Verify the merge compiles

```bash
python -c "from sapguimcp.tools.sm30_tools import register_sm30_tools; print('OK')"
```

---

### Task 2: Apply quality fix — session threading in sm30_tools.py

The SM30 tool uses `sap_transaction_impl("SM30")` which ignores the session `page`. Replace with `navigate_transaction(page, "SM30")` from `sap_page_helpers.py`.

**Files:** Modify `src/sapguimcp/tools/sm30_tools.py`

**Step 1:** Replace imports. Remove:

```python
from sapguimcp.tools.sap_tool_impl import sap_transaction_impl
```

Add:

```python
from sapguimcp.tools.sap_page_helpers import navigate_transaction
```

**Step 2:** In `_lookup_view()`, replace:

```python
tx_result = await sap_transaction_impl("SM30")
if not tx_result.success:
    return SM30ViewResult.failure(
        error=f"Failed to navigate to SM30: {tx_result.error}",
        ...
    )
```

With:

```python
tx_error = await navigate_transaction(page, "SM30")
if tx_error:
    return SM30ViewResult.failure(
        error=f"Failed to navigate to SM30: {tx_error}",
        ...
    )
```

---

### Task 3: Apply quality fix — strict typing in sm30_tools.py

Replace all `Any` type annotations with proper Playwright types.

**Files:** Modify `src/sapguimcp/tools/sm30_tools.py`

**Step 1:** Add Playwright import:

```python
from playwright.async_api import Locator, Page
```

**Step 2:** Replace all `page: Any` with `page: Page` in:

- `_find_view_field(page: Page) -> Locator | None`
- `_fill_view_field(page: Page, view_name: str) -> str | None`
- `_click_display_button(page: Page) -> str | None` (if still used)
- `_ensure_display_mode(page: Page) -> None`
- `_check_view_not_found(page: Page, view_name: str) -> str | None`
- `_check_sm34_redirect(page: Page) -> str | None`
- `_collect_all_rows_with_pagination(page: Page, initial_snapshot: str) -> str`
- `_lookup_view(page: Page, view_name: str) -> SM30ViewResult`

**Step 3:** Fix return types: `_find_view_field` should return `Locator | None` not `Any`.

**Step 4:** Remove `from typing import Any` if no longer needed.

---

### Task 4: Apply quality fix — bilingual patterns in sm30_tools.py

Replace hardcoded DE/EN strings with `bilingual_pattern()` from `lang.py`.

**Files:** Modify `src/sapguimcp/tools/sm30_tools.py`

**Step 1:** Add lang imports:

```python
from sapguimcp.lang import (
    SM30_DISPLAY_BUTTON_DE,
    SM30_DISPLAY_BUTTON_EN,
    SM30_INITIAL_SCREEN_DE,
    SM30_INITIAL_SCREEN_EN,
    SM30_TABLE_VIEW_DE,
    SM30_TABLE_VIEW_EN,
    bilingual_pattern,
)
```

**Step 2:** Replace hardcoded field/button name strings with `bilingual_pattern()` or direct constant references:

- `_find_view_field`: Use `re.compile(bilingual_pattern(SM30_TABLE_VIEW_DE, SM30_TABLE_VIEW_EN))` for the textbox name
- `_ensure_display_mode`: Use `SM30_DISPLAY_BUTTON_DE`/`SM30_DISPLAY_BUTTON_EN` for radio button labels
- `_click_display_button` (if used): Use display button constants
- `_check_view_not_found`: Use constants from lang.py for not-found patterns
- `_check_sm34_redirect`: Already fine (checks for "SM34" literal)

---

### Task 5: Remove dead code and unused functions

**Files:** Modify `src/sapguimcp/tools/sm30_tools.py`

**Step 1:** Review and remove unused functions:

- `_collect_all_rows_with_pagination` — stub that just returns input. Remove (YAGNI).
- `_click_display_button` — if `_ensure_display_mode` + Enter handles display, this may be dead. Check if it's called. Remove if unused.

**Step 2:** Clean up any `# TODO` comments that won't be addressed.

---

### Task 6: Verify models don't use `Any` typing

**Files:** Review `src/sapguimcp/models/sm30_models.py`

**Step 1:** Check if `from typing import Any` is used. The current branch code imports `Any` but doesn't seem to use it (the `SM30ViewType` is `Literal["flat", "unsupported"]`). Remove unused `Any` import.

**Step 2:** Ensure `SM30ViewType` is exported in `__all__` of both `sm30_models.py` and `models/__init__.py`.

---

### Task 7: Run all CI checks and fix issues

**Step 1:** Run parser unit tests:

```bash
pytest unittests/test_sm30_parser.py -v --no-header 2>&1 | tail -30
```

**Step 2:** Run all parser tests (ensure no regressions):

```bash
pytest unittests/ -k "parser" -v --no-header 2>&1 | tail -30
```

**Step 3:** Run linting:

```bash
tox -e linting 2>&1 | tail -30
```

**Step 4:** Run type checking:

```bash
tox -e type_check 2>&1 | tail -30
```

**Step 5:** Fix any issues found. Common problems:

- Pylint unused-argument warnings
- Mypy strict typing violations
- Import ordering (isort)

---

### Task 8: Run code reviewer and implement findings

**Step 1:** Run the `superpowers:requesting-code-review` skill to review the SM30 implementation.

**Step 2:** Implement reviewer findings. Based on patterns from SM37/SLG1/ST22/SE09, expect:

- Session threading issues (should be fixed by Task 2)
- `Any` typing (should be fixed by Task 3)
- Hardcoded strings (should be fixed by Task 4)
- Missing exports in `__all__`
- Unused imports

**Step 3:** Run CI checks again after implementing fixes.

---

### Task 9: Format, push, and finalize SM30

**Step 1:** Run formatting:

```bash
black src/sapguimcp/tools/sm30_tools.py src/sapguimcp/parsers/sm30_parser.py src/sapguimcp/models/sm30_models.py
isort src/sapguimcp/tools/sm30_tools.py src/sapguimcp/parsers/sm30_parser.py src/sapguimcp/models/sm30_models.py
npm run format
```

**Step 2:** Run full test suite in both DE and EN:

```bash
SAP_LANGUAGE=DE pytest unittests/ -v --no-header 2>&1 | tail -40
SAP_LANGUAGE=EN pytest unittests/ -v --no-header 2>&1 | tail -40
```

**Step 3:** Push:

```bash
git push origin feat/sm30-tool
```

**Step 4:** User squash-merges to main.

---

## Phase 2: SPRO Search Exploration

### Task 10: Create SPRO exploration test file

**Files:** Create `unittests/test_spro_exploration.py`, create directory `unittests/testdata/spro_exploration/`

**Step 1:** Create exploration tests that capture ARIA snapshots from SPRO:

```python
"""
Exploratory tests for SPRO (Customizing - IMG) search tool.

These tests run against a real SAP system to capture YAML snapshots for
parser development. Run with SAP_LANGUAGE=DE and SAP_LANGUAGE=EN to get both.

Exploration targets:
1. SPRO initial screen
2. SAP Reference IMG tree (after clicking the button)
3. IMG search dialog (F5 / Find)
4. Search results for a known keyword (e.g., "country", "Land")
5. Empty search results
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    KeyboardResult,
    LoginResult,
    SnapshotResult,
    TransactionResult,
)

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "spro_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = YAML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        YAML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content


@pytest.mark.anyio
async def test_spro_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SPRO initial screen."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SPRO"}, TransactionResult)
    assert tx.success

    await client.call_tool("browser_wait", {"timeout": 2000})
    await capture_yaml_snapshot(sap_mcp_client, "spro_initial", overwrite=True)


@pytest.mark.anyio
async def test_spro_capture_img_tree(sap_mcp_client: ClientSession) -> None:
    """Capture IMG tree after clicking 'SAP Reference IMG' button."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SPRO"}, TransactionResult)
    assert tx.success
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click "SAP Referenz-IMG" / "SAP Reference IMG" button
    # This is typically the main button on the SPRO initial screen
    # Capture snapshot to see what the button is called
    await capture_yaml_snapshot(sap_mcp_client, "spro_before_img_click", overwrite=True)

    # Try clicking the SAP Reference IMG button
    # The actual label needs to be determined from the snapshot
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})
    await capture_yaml_snapshot(sap_mcp_client, "spro_img_tree", overwrite=True)


@pytest.mark.anyio
async def test_spro_capture_search_dialog(sap_mcp_client: ClientSession) -> None:
    """Capture the IMG search dialog."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SPRO"}, TransactionResult)
    assert tx.success
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Navigate into IMG tree first (F5 or click button - TBD from snapshots)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Open search (Ctrl+F or menu Find)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Ctrl+F"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await capture_yaml_snapshot(sap_mcp_client, "spro_search_dialog", overwrite=True)


@pytest.mark.anyio
async def test_spro_capture_search_results(sap_mcp_client: ClientSession) -> None:
    """Capture search results for a known keyword."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SPRO"}, TransactionResult)
    assert tx.success
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Navigate into IMG tree
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Open search
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Ctrl+F"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Type search keyword and execute
    # NOTE: The actual search method (dialog vs inline) needs to be determined
    # from the search dialog snapshot. This is a best-guess flow.
    from sapguimcp.models import FillFormResult
    # Try filling search field - actual field name TBD from snapshot
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
    await capture_yaml_snapshot(sap_mcp_client, "spro_search_results_country", overwrite=True)
```

**Expected outcome:** Running these tests captures snapshots that reveal the ARIA structure of SPRO's initial screen, IMG tree, search dialog, and search results. These snapshots are essential before writing the parser.

**Run command:**

```bash
SAP_LANGUAGE=DE pytest unittests/test_spro_exploration.py -v -s --no-header 2>&1 | head -100
SAP_LANGUAGE=EN pytest unittests/test_spro_exploration.py -v -s --no-header 2>&1 | head -100
```

**NOTE:** The exploration tests above are a starting point. They will likely need adjustment once the actual SPRO ARIA structure is observed. The F5/Ctrl+F key assumptions may not be correct for SPRO WebGUI. Iterate based on captured snapshots.

---

### Task 11: Analyze SPRO snapshots and design parser

After running the exploration tests, analyze the captured YAML snapshots to understand:

1. **SPRO initial screen:** What buttons are available? What's the "SAP Reference IMG" button called in ARIA?
2. **IMG tree structure:** How does the tree render in ARIA? Are nodes `treeitem` elements? How are levels indicated?
3. **Search mechanism:** Is there a search dialog? An inline search? What ARIA elements does it use?
4. **Search results:** How are results presented? Flat list? Filtered tree? What data is available per result?

**Decision point:** Based on the snapshot analysis, decide:

- What the parser needs to extract
- What navigation steps are needed in the tool
- Whether the search approach works or if an alternative is needed

**Write findings** as comments in the exploration test file or as a brief analysis doc.

---

## Phase 3: SPRO Search Implementation

> **Note:** Tasks 12–17 are templates. The exact code depends on SPRO snapshot analysis from Task 11. Parser patterns and field names will be determined after exploration.

### Task 12: Add SPRO language constants to lang.py

**Files:** Modify `src/sapguimcp/lang.py`

Add SPRO-specific constants after the SM30 section:

```python
# =============================================================================
# SPRO - Customizing (IMG)
# =============================================================================
SPRO_INITIAL_SCREEN_DE = "<TBD from snapshot>"
SPRO_INITIAL_SCREEN_EN = "<TBD from snapshot>"

SPRO_SAP_REF_IMG_DE = "<TBD from snapshot>"  # Button label for SAP Reference IMG
SPRO_SAP_REF_IMG_EN = "<TBD from snapshot>"

# Search-related labels TBD from exploration snapshots
```

---

### Task 13: Create SPRO models (spro_models.py)

**Files:** Create `src/sapguimcp/models/spro_models.py`

```python
"""
Pydantic models for SPRO (IMG Customizing) search tool.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "SPROActivity",
    "SPROSearchResult",
    "SPROFileSummary",
]


class SPROActivity(BaseModel):
    """A single IMG customizing activity from SPRO search results."""

    activity_name: str = Field(description="Name of the customizing activity (e.g., 'Define Countries')")
    parent_node: str = Field(default="", description="Immediate parent node in the IMG tree")
    area: str = Field(default="", description="Broad area/section in the IMG tree")


class SPROSearchResult(ToolResult):
    """Result of SPRO IMG search."""

    activities: list[SPROActivity] = Field(default_factory=list, description="Matching activities")
    query: str = Field(description="Search query used")
    activity_count: int = Field(default=0, description="Number of activities found")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp when data was retrieved")


class SPROFileSummary(ToolResult):
    """Summary result when SPRO output is written to file."""

    output_file: str = Field(description="Path to JSON file with full results")
    query: str = Field(description="Search query used")
    activity_count: int = Field(default=0, description="Total activities found")
    sample_activities: list[SPROActivity] = Field(default_factory=list, description="Preview of first 5 activities")
```

---

### Task 14: Create SPRO parser (spro_parser.py)

**Files:** Create `src/sapguimcp/parsers/spro_parser.py`

**NOTE:** The parser implementation depends entirely on the ARIA snapshot analysis from Task 11. The parser patterns (regex, tree walking, etc.) will be determined after exploring the actual SPRO search results structure.

Skeleton:

```python
"""
Parser for SPRO (Customizing IMG) search result ARIA snapshots.

Extracts activity names, IMG paths, and linked transaction codes
from SPRO search results.
"""

import logging
import re
from datetime import UTC, datetime

from sapguimcp.models.spro_models import SPROActivity, SPROSearchResult

logger = logging.getLogger(__name__)

__all__ = [
    "parse_spro_search_results",
]


def parse_spro_search_results(
    snapshot: str,
    query: str,
) -> SPROSearchResult:
    """
    Parse SPRO search results from ARIA snapshot.

    Args:
        snapshot: YAML accessibility snapshot from the search results screen
        query: The search keyword that was used

    Returns:
        SPROSearchResult with parsed activities
    """
    now = datetime.now(UTC)

    # TODO: Implement based on ARIA snapshot analysis from exploration tests
    # Pattern TBD after Task 11

    activities: list[SPROActivity] = []

    return SPROSearchResult(
        activities=activities,
        query=query,
        activity_count=len(activities),
        retrieved_at=now,
    )
```

---

### Task 15: Create SPRO tool (spro_tools.py)

**Files:** Create `src/sapguimcp/tools/spro_tools.py`

Follow the session-aware pattern from SLG1/SE09/SM37:

- Use `navigate_transaction(page, "SPRO")`
- Use `Page` and `Locator` types (not `Any`)
- Use `bilingual_pattern()` for DE/EN label matching
- Only write output_file on `result.success`

Navigation flow:

1. `navigate_transaction(page, "SPRO")`
2. Click "SAP Reference IMG" button (label from lang.py constants)
3. Open search (mechanism TBD from exploration)
4. Enter search keyword
5. Execute search
6. Capture ARIA snapshot
7. Parse with `parse_spro_search_results()`

---

### Task 16: Register SPRO tool and models

**Files:** Modify:

- `src/sapguimcp/models/__init__.py` — Add SPRO model imports + `__all__` entries
- `src/sapguimcp/tools/__init__.py` — Add `register_spro_tools` import + `__all__` entry
- `src/sapguimcp/server.py` — Add import and `register_spro_tools(mcp)` call

---

### Task 17: Write SPRO parser tests and integration tests

**Files:**

- Create `unittests/test_spro_parser.py` — Synthetic + real snapshot parser tests
- Create `unittests/test_spro_integration.py` — End-to-end tests against real SAP

**Parser tests** should include:

- Synthetic snapshots (work offline)
- Real snapshot tests (skip if files don't exist)
- Edge cases: no results, single result, many results

**Integration tests** should include:

- Search with a keyword that returns results (e.g., "country" or "Land")
- Search with a keyword that returns no results
- Output file parameter

---

## Summary

| Phase                        | Tasks | Effort        | Branch                  |
| ---------------------------- | ----- | ------------- | ----------------------- |
| Phase 1: SM30 Finish         | 1–9   | ~1 session    | `feat/sm30-tool`        |
| Phase 2: SPRO Exploration    | 10–11 | ~0.5 session  | `feat/spro-search-tool` |
| Phase 3: SPRO Implementation | 12–17 | ~1.5 sessions | `feat/spro-search-tool` |

### Key Dependencies

- Phase 2 (SPRO exploration) can start after Phase 1 is merged to main
- Phase 3 (SPRO implementation) depends on Phase 2 snapshot analysis
- Tasks 12–17 are templates — exact code TBD after exploration
