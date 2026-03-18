# `sap_quick_report` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a composite `sap_quick_report` MCP tool that bundles transaction → fill selection screen → F8 → read result into a single call, with a learnable hint system for handling unknown screens.

**Architecture:** Pipeline with reusable screen classifier. Hint system with two-layer merge (shipped JSON baseline + user-local JSON). "Stay and report" error handling — tool never resets navigation state on failure.

**Tech Stack:** Python 3.11+, FastMCP, Playwright (WebGUI backend), Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-03-18-sap-quick-report-design.md`

**Repo:** `sapwebgui.mcp/` (cloned at `C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapwebgui.mcp`)

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `src/sapwebguimcp/models/quick_report_models.py` | `ScreenClassification`, `QuickReportResult`, `TCodeHint`, `PopupHint`, `TCodeHintSuggestion`, `SaveHintResult` |
| Create | `src/sapwebguimcp/tools/_hint_loader.py` | `load_hints()`, `save_hint()`, two-layer JSON merge |
| Create | `src/sapwebguimcp/tools/quick_report_tools.py` | `sap_quick_report` tool, `sap_save_tcode_hint` tool, `classify_result_screen()`, pipeline |
| Create | `src/sapwebguimcp/data/tcode_hints.json` | Shipped baseline hints for standard transactions |
| Modify | `src/sapwebguimcp/models/__init__.py` | Export new models |
| Modify | `src/sapwebguimcp/tools/__init__.py` | Export `register_quick_report_tools` |
| Modify | `src/sapwebguimcp/server.py:207` | Register quick_report_tools (WebGUI-only block) |
| Create | `unittests/test_quick_report_models.py` | Model validation tests |
| Create | `unittests/test_hint_loader.py` | Hint loading + merge tests |
| Create | `unittests/test_quick_report_tools.py` | Pipeline + classifier tests with mock backend |

---

## Task 1: Pydantic Models

**Files:**
- Create: `src/sapwebguimcp/models/quick_report_models.py`
- Test: `unittests/test_quick_report_models.py`

- [ ] **Step 1: Write failing test for ScreenClassification enum**

```python
# unittests/test_quick_report_models.py
"""Unit tests for quick report models."""

import pytest
from pydantic import ValidationError

from sapwebguimcp.models.quick_report_models import (
    PopupHint,
    QuickReportResult,
    SaveHintResult,
    ScreenClassification,
    TCodeHint,
    TCodeHintSuggestion,
)


class TestScreenClassification:
    def test_values(self) -> None:
        assert ScreenClassification.TABLE == "table"
        assert ScreenClassification.EMPTY == "empty"
        assert ScreenClassification.ERROR == "error"
        assert ScreenClassification.UNKNOWN == "unknown"

    def test_from_string(self) -> None:
        assert ScreenClassification("table") == ScreenClassification.TABLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_models.py::TestScreenClassification -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sapwebguimcp.models.quick_report_models'`

- [ ] **Step 3: Implement ScreenClassification**

```python
# src/sapwebguimcp/models/quick_report_models.py
"""Pydantic models for sap_quick_report composite tool."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from sapwebguimcp.models.base import ToolResult
from sapwebguimcp.models.sap_results import StatusBarType, TableData, ScreenText


class ScreenClassification(StrEnum):
    """What appeared on screen after F8."""

    TABLE = "table"
    EMPTY = "empty"
    ERROR = "error"
    UNKNOWN = "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_models.py::TestScreenClassification -v`
Expected: PASS

- [ ] **Step 5: Write failing test for PopupHint and TCodeHint**

Add to `unittests/test_quick_report_models.py`:

```python
class TestPopupHint:
    def test_defaults(self) -> None:
        hint = PopupHint(text_pattern="Variante")
        assert hint.text_pattern == "Variante"
        assert hint.action == "Enter"

    def test_custom_action(self) -> None:
        hint = PopupHint(text_pattern="Drucken", action="Escape")
        assert hint.action == "Escape"


class TestTCodeHint:
    def test_defaults(self) -> None:
        hint = TCodeHint(tcode="SM37")
        assert hint.post_f8 == ScreenClassification.TABLE
        assert hint.known_popups == []
        assert hint.notes == ""

    def test_with_popups(self) -> None:
        hint = TCodeHint(
            tcode="FBL1N",
            known_popups=[PopupHint(text_pattern="Variante")],
            notes="Kreditorenposten",
        )
        assert len(hint.known_popups) == 1
        assert hint.known_popups[0].text_pattern == "Variante"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_models.py::TestPopupHint unittests/test_quick_report_models.py::TestTCodeHint -v`
Expected: FAIL

- [ ] **Step 7: Implement PopupHint and TCodeHint**

Add to `src/sapwebguimcp/models/quick_report_models.py`:

```python
class PopupHint(BaseModel):
    """A known popup that can appear after F8."""

    text_pattern: str = Field(description="Substring to match in popup text (case-insensitive)")
    action: str = Field(default="Enter", description="Key to press to dismiss the popup")


class TCodeHint(BaseModel):
    """Expectations for a transaction after F8."""

    tcode: str = Field(description="Transaction code")
    post_f8: ScreenClassification = Field(
        default=ScreenClassification.TABLE,
        description="Expected screen type after F8",
    )
    known_popups: list[PopupHint] = Field(
        default_factory=list,
        description="Known popups that may appear after F8",
    )
    notes: str = Field(default="", description="Free-text notes for developers/agents")
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_models.py::TestPopupHint unittests/test_quick_report_models.py::TestTCodeHint -v`
Expected: PASS

- [ ] **Step 9: Write failing test for TCodeHintSuggestion**

Add to `unittests/test_quick_report_models.py`:

```python
class TestTCodeHintSuggestion:
    def test_creation(self) -> None:
        suggestion = TCodeHintSuggestion(
            tcode="ZCUSTOM01",
            observed_screen_type="unknown",
            status_bar_type="none",
            status_bar_message="",
            page_title="Variantenauswahl",
            dom_roles=["dialog", "listbox"],
        )
        assert suggestion.tcode == "ZCUSTOM01"
        assert suggestion.dom_roles == ["dialog", "listbox"]
```

- [ ] **Step 10: Implement TCodeHintSuggestion**

Add to `src/sapwebguimcp/models/quick_report_models.py`:

```python
class TCodeHintSuggestion(BaseModel):
    """Tool-generated suggestion for a new hint."""

    tcode: str = Field(description="Transaction code")
    observed_screen_type: str = Field(description="What the classifier observed")
    status_bar_type: str = Field(description="Status bar type after F8")
    status_bar_message: str = Field(description="Status bar message after F8")
    page_title: str = Field(description="Page title after F8")
    dom_roles: list[str] = Field(
        default_factory=list,
        description="Unique ARIA roles found in DOM (e.g. ['dialog', 'listbox'])",
    )
```

- [ ] **Step 11: Run test to verify it passes**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_models.py::TestTCodeHintSuggestion -v`
Expected: PASS

- [ ] **Step 12: Write failing test for QuickReportResult**

Add to `unittests/test_quick_report_models.py`:

```python
class TestQuickReportResult:
    def test_success_table(self) -> None:
        result = QuickReportResult(
            tcode="SM37",
            screen_type=ScreenClassification.TABLE,
            page_title="Job Overview",
            table=TableData(headers=["Job"], rows=[], total_rows=0),
        )
        assert result.success is True
        assert result.screen_type == "table"
        assert result.table is not None

    def test_error(self) -> None:
        result = QuickReportResult.failure(
            error="Transaction not found",
            tcode="ZNOTEXIST",
            screen_type=ScreenClassification.ERROR,
        )
        assert result.success is False
        assert result.screen_type == "error"

    def test_unknown_with_hint_suggestion(self) -> None:
        suggestion = TCodeHintSuggestion(
            tcode="ZCUSTOM",
            observed_screen_type="unknown",
            status_bar_type="none",
            status_bar_message="",
            page_title="Popup",
            dom_roles=["dialog"],
        )
        result = QuickReportResult(
            tcode="ZCUSTOM",
            screen_type=ScreenClassification.UNKNOWN,
            hint_suggestion=suggestion,
        )
        assert result.hint_suggestion is not None
        assert result.hint_suggestion.dom_roles == ["dialog"]

    def test_warnings_collected(self) -> None:
        result = QuickReportResult(
            tcode="SM37",
            screen_type=ScreenClassification.TABLE,
            warnings=["Checkbox 'Geplant' not found on screen"],
        )
        assert len(result.warnings) == 1
```

- [ ] **Step 13: Implement QuickReportResult and SaveHintResult**

Add to `src/sapwebguimcp/models/quick_report_models.py`:

```python
class QuickReportResult(ToolResult):
    """Result from sap_quick_report tool."""

    tcode: str = Field(description="Transaction code executed")
    screen_type: ScreenClassification = Field(description="What appeared after F8")
    page_title: str = Field(default="", description="Screen title after execution")

    # Status bar (always populated if available)
    status_bar_type: StatusBarType | None = Field(
        default=None, description="Status bar type after F8"
    )
    status_bar_message: str | None = Field(
        default=None, description="Status bar text after F8"
    )

    # When screen_type="table"
    table: TableData | None = Field(default=None, description="Table data if grid found")

    # When screen_type="error" or "unknown"
    screen_text: ScreenText | None = Field(
        default=None, description="Screen text for non-table results"
    )

    # When screen_type="unknown": learning hint
    hint_suggestion: TCodeHintSuggestion | None = Field(
        default=None, description="Suggested hint for this tcode"
    )

    # Warnings (non-fatal issues during execution)
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings collected during execution"
    )


class SaveHintResult(ToolResult):
    """Result from sap_save_tcode_hint tool."""

    tcode: str = Field(description="Transaction code the hint was saved for")
    hint_file: str = Field(description="Path to the hints file that was written")
```

- [ ] **Step 14: Run all model tests**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_models.py -v`
Expected: ALL PASS

- [ ] **Step 15: Commit**

```bash
cd sapwebgui.mcp
git add src/sapwebguimcp/models/quick_report_models.py unittests/test_quick_report_models.py
git commit -m "feat: add Pydantic models for sap_quick_report

Add ScreenClassification enum, QuickReportResult, TCodeHint,
PopupHint, TCodeHintSuggestion, and SaveHintResult models."
```

---

## Task 2: Hint Loader (Two-Layer JSON Merge)

**Files:**
- Create: `src/sapwebguimcp/tools/_hint_loader.py`
- Create: `src/sapwebguimcp/data/tcode_hints.json`
- Test: `unittests/test_hint_loader.py`

- [ ] **Step 1: Write failing test for loading shipped hints**

```python
# unittests/test_hint_loader.py
"""Unit tests for TCode hint loader."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sapwebguimcp.models.quick_report_models import (
    PopupHint,
    ScreenClassification,
    TCodeHint,
)
from sapwebguimcp.tools._hint_loader import (
    USER_HINTS_PATH,
    load_hint,
    load_hints,
    merge_hints,
    save_hint,
)


class TestLoadHints:
    def test_load_shipped_hints(self) -> None:
        """Shipped hints file must exist and be parseable."""
        hints = load_hints()
        assert isinstance(hints, dict)
        # SM37 must be in shipped baseline
        assert "SM37" in hints
        assert hints["SM37"].post_f8 == ScreenClassification.TABLE

    def test_load_hint_known_tcode(self) -> None:
        hint = load_hint("SM37")
        assert hint is not None
        assert hint.tcode == "SM37"

    def test_load_hint_unknown_tcode(self) -> None:
        hint = load_hint("ZZZNOTEXIST999")
        assert hint is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_hint_loader.py::TestLoadHints -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create shipped baseline `tcode_hints.json`**

```json
{
  "SM37": {
    "tcode": "SM37",
    "post_f8": "table",
    "known_popups": [],
    "notes": "Job overview, always ALV grid"
  },
  "VA05": {
    "tcode": "VA05",
    "post_f8": "table",
    "known_popups": [],
    "notes": "Sales order list"
  },
  "ME2M": {
    "tcode": "ME2M",
    "post_f8": "table",
    "known_popups": [],
    "notes": "Purchase orders by material"
  },
  "MB51": {
    "tcode": "MB51",
    "post_f8": "table",
    "known_popups": [],
    "notes": "Material document list"
  },
  "FBL1N": {
    "tcode": "FBL1N",
    "post_f8": "table",
    "known_popups": [
      {"text_pattern": "Variante", "action": "Enter"}
    ],
    "notes": "Vendor line items, may ask for display variant"
  },
  "FBL3N": {
    "tcode": "FBL3N",
    "post_f8": "table",
    "known_popups": [
      {"text_pattern": "Variante", "action": "Enter"}
    ],
    "notes": "G/L account line items"
  },
  "FBL5N": {
    "tcode": "FBL5N",
    "post_f8": "table",
    "known_popups": [
      {"text_pattern": "Variante", "action": "Enter"}
    ],
    "notes": "Customer line items"
  }
}
```

Write to: `src/sapwebguimcp/data/tcode_hints.json`

- [ ] **Step 4: Implement `_hint_loader.py`**

```python
# src/sapwebguimcp/tools/_hint_loader.py
"""Two-layer TCode hint loader: shipped baseline + user-local overrides."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sapwebguimcp.models.quick_report_models import PopupHint, TCodeHint

logger = logging.getLogger(__name__)

__all__ = ["load_hint", "load_hints", "merge_hints", "save_hint", "USER_HINTS_PATH"]

# Shipped baseline (read-only, packaged with the project)
_SHIPPED_HINTS_PATH = Path(__file__).resolve().parent.parent / "data" / "tcode_hints.json"

# User-local overrides (read-write)
USER_HINTS_PATH = Path.home() / ".sapwebguimcp" / "tcode_hints.json"


def _load_json_hints(path: Path) -> dict[str, TCodeHint]:
    """Load hints from a JSON file, returning empty dict on missing/invalid file."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: TCodeHint(**v) for k, v in raw.items()}
    except (json.JSONDecodeError, PermissionError, ValueError) as exc:
        logger.warning("Failed to load hints from %s: %s", path, exc)
        return {}


def merge_hints(
    base: dict[str, TCodeHint], override: dict[str, TCodeHint]
) -> dict[str, TCodeHint]:
    """Merge two hint dicts. Override wins for post_f8/notes; popups are unioned by text_pattern."""
    merged = dict(base)
    for tcode, user_hint in override.items():
        if tcode not in merged:
            merged[tcode] = user_hint
            continue
        repo_hint = merged[tcode]
        # Union known_popups, deduplicate by text_pattern (user action wins)
        popup_map: dict[str, PopupHint] = {}
        for p in repo_hint.known_popups:
            popup_map[p.text_pattern.lower()] = p
        for p in user_hint.known_popups:
            popup_map[p.text_pattern.lower()] = p  # user wins on conflict
        merged[tcode] = TCodeHint(
            tcode=tcode,
            post_f8=user_hint.post_f8,
            known_popups=list(popup_map.values()),
            notes=user_hint.notes if user_hint.notes else repo_hint.notes,
        )
    return merged


def load_hints() -> dict[str, TCodeHint]:
    """Load and merge shipped + user-local hints."""
    shipped = _load_json_hints(_SHIPPED_HINTS_PATH)
    user = _load_json_hints(USER_HINTS_PATH)
    return merge_hints(shipped, user)


def load_hint(tcode: str) -> TCodeHint | None:
    """Load hint for a specific tcode, or None if not found."""
    hints = load_hints()
    return hints.get(tcode.upper())


def save_hint(hint: TCodeHint) -> Path:
    """Save a hint to the user-local hints file. Creates file/dir if needed."""
    USER_HINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_json_hints(USER_HINTS_PATH)
    existing[hint.tcode.upper()] = hint
    data = {k: v.model_dump(mode="json") for k, v in existing.items()}
    USER_HINTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return USER_HINTS_PATH
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_hint_loader.py::TestLoadHints -v`
Expected: PASS

- [ ] **Step 6: Write failing test for merge logic**

Add to `unittests/test_hint_loader.py`:

```python
class TestMergeHints:
    def test_user_overrides_post_f8(self) -> None:
        base = {"SM37": TCodeHint(tcode="SM37", post_f8=ScreenClassification.TABLE)}
        override = {"SM37": TCodeHint(tcode="SM37", post_f8=ScreenClassification.UNKNOWN)}
        merged = merge_hints(base, override)
        assert merged["SM37"].post_f8 == ScreenClassification.UNKNOWN

    def test_user_adds_new_tcode(self) -> None:
        base = {"SM37": TCodeHint(tcode="SM37")}
        override = {"ZCUSTOM": TCodeHint(tcode="ZCUSTOM", notes="Custom tx")}
        merged = merge_hints(base, override)
        assert "ZCUSTOM" in merged
        assert "SM37" in merged

    def test_popup_union_dedup_by_pattern(self) -> None:
        base = {
            "FBL1N": TCodeHint(
                tcode="FBL1N",
                known_popups=[PopupHint(text_pattern="Variante", action="Enter")],
            )
        }
        override = {
            "FBL1N": TCodeHint(
                tcode="FBL1N",
                known_popups=[
                    PopupHint(text_pattern="Variante", action="Escape"),  # override action
                    PopupHint(text_pattern="Drucken", action="Enter"),  # new popup
                ],
            )
        }
        merged = merge_hints(base, override)
        popups = {p.text_pattern.lower(): p for p in merged["FBL1N"].known_popups}
        assert popups["variante"].action == "Escape"  # user wins
        assert "drucken" in popups  # new popup added

    def test_user_notes_override(self) -> None:
        base = {"SM37": TCodeHint(tcode="SM37", notes="Original")}
        override = {"SM37": TCodeHint(tcode="SM37", notes="Updated")}
        merged = merge_hints(base, override)
        assert merged["SM37"].notes == "Updated"

    def test_empty_user_notes_keeps_repo(self) -> None:
        base = {"SM37": TCodeHint(tcode="SM37", notes="Original")}
        override = {"SM37": TCodeHint(tcode="SM37", notes="")}
        merged = merge_hints(base, override)
        assert merged["SM37"].notes == "Original"
```

- [ ] **Step 7: Run merge tests**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_hint_loader.py::TestMergeHints -v`
Expected: PASS (implementation already handles this)

- [ ] **Step 8: Write failing test for save_hint**

Add to `unittests/test_hint_loader.py`:

```python
class TestSaveHint:
    def test_save_and_reload(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        hints_file = tmp_path / "tcode_hints.json"
        import sapwebguimcp.tools._hint_loader as loader_mod

        monkeypatch.setattr(loader_mod, "USER_HINTS_PATH", hints_file)

        hint = TCodeHint(
            tcode="ZCUSTOM",
            known_popups=[PopupHint(text_pattern="Test")],
            notes="Test hint",
        )
        result_path = save_hint(hint)
        assert result_path == hints_file
        assert hints_file.exists()

        # Reload and verify
        data = json.loads(hints_file.read_text(encoding="utf-8"))
        assert "ZCUSTOM" in data
        assert data["ZCUSTOM"]["known_popups"][0]["text_pattern"] == "Test"

    def test_save_preserves_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        hints_file = tmp_path / "tcode_hints.json"
        hints_file.write_text('{"EXISTING": {"tcode": "EXISTING", "post_f8": "table"}}')
        import sapwebguimcp.tools._hint_loader as loader_mod

        monkeypatch.setattr(loader_mod, "USER_HINTS_PATH", hints_file)

        save_hint(TCodeHint(tcode="NEW", notes="New hint"))
        data = json.loads(hints_file.read_text(encoding="utf-8"))
        assert "EXISTING" in data
        assert "NEW" in data
```

- [ ] **Step 9: Run save tests**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_hint_loader.py::TestSaveHint -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
cd sapwebgui.mcp
git add src/sapwebguimcp/tools/_hint_loader.py src/sapwebguimcp/data/tcode_hints.json unittests/test_hint_loader.py
git commit -m "feat: add two-layer TCode hint loader with JSON merge

Shipped baseline in data/tcode_hints.json covers SM37, VA05, ME2M,
MB51, FBL1N, FBL3N, FBL5N. User-local hints in ~/.sapwebguimcp/
override per tcode-key, popups union by text_pattern."
```

---

## Task 3: Screen Classifier

**Files:**
- Modify: `src/sapwebguimcp/tools/quick_report_tools.py` (will be created here)
- Test: `unittests/test_quick_report_tools.py`

- [ ] **Step 1: Write failing test for classify_result_screen**

```python
# unittests/test_quick_report_tools.py
"""Unit tests for sap_quick_report pipeline and screen classifier."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapwebguimcp.models.quick_report_models import (
    ScreenClassification,
    TCodeHint,
    PopupHint,
)
from sapwebguimcp.models.sap_results import StatusBarInfo


def _make_mock_backend(
    status_bar_type: str = "none",
    status_bar_message: str = "",
    has_grid: bool = False,
    has_tree: bool = False,
    page_title: str = "Test Screen",
) -> AsyncMock:
    """Create a mock SapUiBackend for testing the classifier."""
    backend = AsyncMock()
    backend.get_status_bar = AsyncMock(
        return_value=StatusBarInfo(
            type=status_bar_type,
            message=status_bar_message,
        )
    )

    # Simulate DOM role check via evaluate_javascript
    async def mock_evaluate(script: str, arg: Any = None) -> Any:
        if "role='grid'" in script or "role=\"grid\"" in script:
            return has_grid
        if "role='tree'" in script or "role=\"tree\"" in script:
            return has_tree
        return None

    backend.evaluate_javascript = AsyncMock(side_effect=mock_evaluate)
    backend.get_page_title = AsyncMock(return_value=page_title)
    return backend


class TestClassifyResultScreen:
    @pytest.mark.asyncio
    async def test_error_status_bar(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import classify_result_screen

        backend = _make_mock_backend(status_bar_type="E", status_bar_message="Table not found")
        classification, status_bar = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR

    @pytest.mark.asyncio
    async def test_empty_no_data(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import classify_result_screen

        backend = _make_mock_backend(
            status_bar_type="I", status_bar_message="Keine Daten gefunden"
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    @pytest.mark.asyncio
    async def test_empty_no_entries(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import classify_result_screen

        backend = _make_mock_backend(
            status_bar_type="W", status_bar_message="No entries found"
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    @pytest.mark.asyncio
    async def test_table_grid_found(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import classify_result_screen

        backend = _make_mock_backend(has_grid=True)
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.TABLE

    @pytest.mark.asyncio
    async def test_unknown_fallback(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import classify_result_screen

        backend = _make_mock_backend()  # no grid, no error, no empty
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.UNKNOWN

    @pytest.mark.asyncio
    async def test_error_takes_priority_over_grid(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import classify_result_screen

        backend = _make_mock_backend(status_bar_type="E", status_bar_message="Error", has_grid=True)
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_tools.py::TestClassifyResultScreen -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement classify_result_screen**

```python
# src/sapwebguimcp/tools/quick_report_tools.py
"""
Composite sap_quick_report tool: transaction → fill → F8 → classify → result.

WebGUI-only (Phase 1). Uses pipeline architecture with reusable screen classifier.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sapwebguimcp.models.quick_report_models import ScreenClassification
from sapwebguimcp.models.sap_results import StatusBarInfo

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import SapUiBackend
    from sapwebguimcp.models.quick_report_models import TCodeHint

logger = logging.getLogger(__name__)

__all__ = ["register_quick_report_tools"]

# Substrings indicating "no data found" (DE + EN)
_EMPTY_PATTERNS = [
    "keine daten",
    "no data",
    "keine werte",
    "no entries",
    "keine einträge",
    "no values",
]


async def classify_result_screen(
    backend: "SapUiBackend",
    hint: "TCodeHint | None" = None,
) -> tuple[ScreenClassification, StatusBarInfo]:
    """
    Classify the current screen after F8.

    Priority:
    1. Status bar type "E" → ERROR
    2. Status bar contains empty-data patterns → EMPTY
    3. DOM has [role='grid'] → TABLE
    4. Fallback → UNKNOWN
    """
    status_bar = await backend.get_status_bar()

    # 1. Error status bar takes priority
    if status_bar.type == "E":
        return ScreenClassification.ERROR, status_bar

    # 2. Empty data patterns in status bar
    msg_lower = (status_bar.message or "").lower()
    if any(pattern in msg_lower for pattern in _EMPTY_PATTERNS):
        return ScreenClassification.EMPTY, status_bar

    # 3. Check for ALV grid in DOM
    has_grid = await backend.evaluate_javascript(
        "() => document.querySelector(\"[role='grid']\") !== null"
    )
    if has_grid:
        return ScreenClassification.TABLE, status_bar

    # 4. Fallback
    return ScreenClassification.UNKNOWN, status_bar
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_tools.py::TestClassifyResultScreen -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd sapwebgui.mcp
git add src/sapwebguimcp/tools/quick_report_tools.py unittests/test_quick_report_tools.py
git commit -m "feat: add screen classifier for post-F8 result detection

Classifies screens as TABLE/EMPTY/ERROR/UNKNOWN based on status bar
and DOM inspection. Reusable for future composite tools."
```

---

## Task 4: Pipeline + `sap_quick_report` Tool

**Files:**
- Modify: `src/sapwebguimcp/tools/quick_report_tools.py`
- Test: `unittests/test_quick_report_tools.py`

- [ ] **Step 1: Write failing test for pipeline — happy path (TABLE)**

Add to `unittests/test_quick_report_tools.py`:

```python
from sapwebguimcp.models.sap_results import (
    ScreenText,
    TableData,
    TableRow,
    TransactionResult,
)
from sapwebguimcp.models.quick_report_models import QuickReportResult
from sapwebguimcp.models.screen_state import ScreenStateDiff


def _make_pipeline_backend(
    tx_success: bool = True,
    status_bar_type: str = "S",
    status_bar_message: str = "7 entries found",
    has_grid: bool = True,
    table_data: TableData | None = None,
    screen_text: ScreenText | None = None,
    page_title: str = "Job Overview",
) -> AsyncMock:
    """Create a mock backend for full pipeline tests."""
    backend = _make_mock_backend(
        status_bar_type=status_bar_type,
        status_bar_message=status_bar_message,
        has_grid=has_grid,
        page_title=page_title,
    )
    backend.enter_transaction = AsyncMock(
        return_value=TransactionResult(
            success=tx_success,
            tcode="SM37",
            page_title=page_title,
            **({"error": "TX not found"} if not tx_success else {}),
        )
    )
    backend.wait_for_ready = AsyncMock()
    backend.press_key = AsyncMock(return_value=MagicMock(
        status_bar_type=status_bar_type,
        status_bar_message=status_bar_message,
    ))
    backend.fill_form = AsyncMock()
    backend.read_table = AsyncMock(
        return_value=table_data or TableData(
            headers=["Job", "Status"],
            rows=[TableRow(row=1, data={"Job": "TEST", "Status": "Finished"})],
            total_rows=1,
        )
    )
    backend.get_screen_text = AsyncMock(
        return_value=screen_text or ScreenText(title=page_title)
    )
    return backend


class TestQuickReportPipeline:
    @pytest.mark.asyncio
    async def test_happy_path_table(self) -> None:
        from unittest.mock import patch
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report
        from sapwebguimcp.models.screen_state import ScreenStateDiff

        backend = _make_pipeline_backend()
        # Patch ensure_screen_state to avoid needing a real ARIA snapshot
        mock_diff = ScreenStateDiff()
        with patch(
            "sapwebguimcp.tools.quick_report_tools.ensure_screen_state",
            return_value=mock_diff,
        ):
            result = await _execute_quick_report(
                backend=backend,
                tcode="SM37",
                fields={"Jobname": "*"},
                checkboxes=None,
                radios=None,
                max_rows=30,
                read_all=False,
            )
        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE
        assert result.table is not None
        assert result.table.total_rows == 1
        # Verify pipeline order: transaction → F8 → wait → classify → read
        backend.enter_transaction.assert_called_once_with("SM37")
        backend.press_key.assert_called()

    @pytest.mark.asyncio
    async def test_transaction_fails(self) -> None:
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report

        backend = _make_pipeline_backend(tx_success=False)
        result = await _execute_quick_report(
            backend=backend,
            tcode="ZNOTEXIST",
            fields=None,
            checkboxes=None,
            radios=None,
            max_rows=30,
            read_all=False,
        )
        assert result.success is False
        assert result.screen_type == ScreenClassification.ERROR

    @pytest.mark.asyncio
    async def test_error_status_bar_after_f8(self) -> None:
        """fields=None intentionally skips ensure_screen_state (guard: if fields or checkboxes or radios)."""
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report

        backend = _make_pipeline_backend(
            status_bar_type="E",
            status_bar_message="Authorization error",
            has_grid=False,
        )
        result = await _execute_quick_report(
            backend=backend,
            tcode="SM37",
            fields=None,
            checkboxes=None,
            radios=None,
            max_rows=30,
            read_all=False,
        )
        assert result.screen_type == ScreenClassification.ERROR
        assert result.screen_text is not None

    @pytest.mark.asyncio
    async def test_unknown_screen_generates_hint_suggestion(self) -> None:
        """fields=None intentionally skips ensure_screen_state (guard: if fields or checkboxes or radios)."""
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report

        backend = _make_pipeline_backend(
            status_bar_type="none",
            status_bar_message="",
            has_grid=False,
            page_title="Variantenauswahl",
        )
        # Mock DOM roles for hint suggestion
        backend.evaluate_javascript = AsyncMock(return_value=False)
        result = await _execute_quick_report(
            backend=backend,
            tcode="ZCUSTOM",
            fields=None,
            checkboxes=None,
            radios=None,
            max_rows=30,
            read_all=False,
        )
        assert result.screen_type == ScreenClassification.UNKNOWN
        assert result.hint_suggestion is not None
        assert result.hint_suggestion.tcode == "ZCUSTOM"

    @pytest.mark.asyncio
    async def test_ensure_screen_state_warnings_flow_to_result(self) -> None:
        from unittest.mock import patch
        from sapwebguimcp.tools.quick_report_tools import _execute_quick_report
        from sapwebguimcp.models.screen_state import ScreenStateDiff

        backend = _make_pipeline_backend()
        mock_diff = ScreenStateDiff(warnings=["Checkbox 'Geplant' not found on screen"])
        with patch(
            "sapwebguimcp.tools.quick_report_tools.ensure_screen_state",
            return_value=mock_diff,
        ):
            result = await _execute_quick_report(
                backend=backend,
                tcode="SM37",
                fields={"Jobname": "*"},
                checkboxes={"Geplant": True},
                radios=None,
                max_rows=30,
                read_all=False,
            )
        assert "Checkbox 'Geplant' not found on screen" in result.warnings
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_tools.py::TestQuickReportPipeline -v`
Expected: FAIL — `_execute_quick_report` not found

- [ ] **Step 3: Implement `_execute_quick_report` pipeline**

Add to `src/sapwebguimcp/tools/quick_report_tools.py`:

```python
from sapwebguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
    TCodeHint,
    TCodeHintSuggestion,
)
from sapwebguimcp.models.sap_results import ScreenText, StatusBarInfo, TableData
from sapwebguimcp.models.screen_state import SelectionScreenState
from sapwebguimcp.tools._hint_loader import load_hint
from sapwebguimcp.tools.screen_state_helpers import ensure_screen_state


async def _check_popup(
    backend: "SapUiBackend",
    hint: TCodeHint | None,
) -> list[str]:
    """Check for known popups and dismiss them. Returns warnings."""
    if not hint or not hint.known_popups:
        return []

    warnings: list[str] = []
    for attempt in range(2):  # max 1 retry
        try:
            screen = await backend.get_screen_text()
            all_text = " ".join([screen.title] + screen.main_content + screen.labels + screen.buttons)
            screen_lower = all_text.lower()
        except Exception as exc:
            warnings.append(f"Could not read screen text for popup check: {exc}")
            break

        matched = False
        for popup_hint in hint.known_popups:
            if popup_hint.text_pattern.lower() in screen_lower:
                logger.info(
                    "Popup matched hint",
                    extra={"pattern": popup_hint.text_pattern, "action": popup_hint.action, "attempt": attempt},
                )
                await backend.press_key(popup_hint.action)
                await backend.wait_for_ready()
                matched = True
                break

        if not matched:
            break

    return warnings


async def _collect_dom_roles(backend: "SapUiBackend") -> list[str]:
    """Collect unique ARIA roles from top-level containers in the DOM."""
    try:
        roles = await backend.evaluate_javascript(
            """() => {
                const roles = new Set();
                document.querySelectorAll('[role]').forEach(el => {
                    roles.add(el.getAttribute('role'));
                });
                return [...roles];
            }"""
        )
        return roles if isinstance(roles, list) else []
    except Exception:
        return []


async def _execute_quick_report(
    backend: "SapUiBackend",
    tcode: str,
    fields: dict[str, str] | None,
    checkboxes: dict[str, bool] | None,
    radios: dict[str, bool] | None,
    max_rows: int,
    read_all: bool,
) -> QuickReportResult:
    """Core pipeline for sap_quick_report. Separated for testability."""
    warnings: list[str] = []

    # Step 1: Load hint
    hint = load_hint(tcode)

    # Step 2: Enter transaction
    tx_result = await backend.enter_transaction(tcode)
    if not tx_result.success:
        return QuickReportResult.failure(
            error=f"Failed to enter transaction {tcode}: {tx_result.error}",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )
    await backend.wait_for_ready()

    # Step 3: Fill selection screen (if any fields/checkboxes/radios given)
    if fields or checkboxes or radios:
        target = SelectionScreenState(
            fields=fields or {},
            checkboxes=checkboxes or {},
            radios=radios or {},
        )
        state_diff = await ensure_screen_state(backend, target)
        if not state_diff.success:
            warnings.append(f"Selection screen: {state_diff.error}")
        warnings.extend(state_diff.warnings)

    # Step 4+5: Press F8 and wait
    await backend.press_key("F8")
    await backend.wait_for_ready()

    # Step 6: Check known popups
    popup_warnings = await _check_popup(backend, hint)
    warnings.extend(popup_warnings)

    # Step 7: Classify result screen
    classification, status_bar = await classify_result_screen(backend, hint)

    # Step 8: Get page title
    page_title = await backend.get_page_title()

    # Step 9: Parse by classification
    table: TableData | None = None
    screen_text: ScreenText | None = None
    hint_suggestion: TCodeHintSuggestion | None = None

    if classification == ScreenClassification.TABLE:
        try:
            if read_all:
                # TODO: Phase 2 — use alv_collect_all_rows for full pagination.
                # For now, use max_rows as upper bound and warn.
                warnings.append(
                    "read_all=True is not yet fully implemented; "
                    "returning up to max_rows rows only"
                )
            table = await backend.read_table(start_row=1, max_rows=max_rows)
        except Exception as exc:
            warnings.append(f"Failed to read table: {exc}")
            table = TableData(headers=[], rows=[], total_rows=0)

    elif classification == ScreenClassification.ERROR:
        try:
            screen_text = await backend.get_screen_text()
        except Exception:
            pass

    elif classification == ScreenClassification.UNKNOWN:
        try:
            screen_text = await backend.get_screen_text()
        except Exception:
            pass
        dom_roles = await _collect_dom_roles(backend)
        hint_suggestion = TCodeHintSuggestion(
            tcode=tcode,
            observed_screen_type="unknown",
            status_bar_type=status_bar.type,
            status_bar_message=status_bar.message or "",
            page_title=page_title,
            dom_roles=dom_roles,
        )
        logger.warning(
            "Unclassified screen after F8",
            extra={
                "tcode": tcode,
                "page_title": page_title,
                "status_bar_type": status_bar.type,
                "status_bar_message": status_bar.message,
                "dom_roles": dom_roles,
            },
        )

    return QuickReportResult(
        tcode=tcode,
        screen_type=classification,
        page_title=page_title,
        status_bar_type=status_bar.type,
        status_bar_message=status_bar.message or "",
        table=table,
        screen_text=screen_text,
        hint_suggestion=hint_suggestion,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run pipeline tests**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_quick_report_tools.py::TestQuickReportPipeline -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd sapwebgui.mcp
git add src/sapwebguimcp/tools/quick_report_tools.py unittests/test_quick_report_tools.py
git commit -m "feat: add sap_quick_report pipeline with popup handling

Pipeline: enter_transaction → ensure_screen_state → F8 → wait →
check_popups → classify → parse. Stays on current screen on failure."
```

---

## Task 5: MCP Tool Registration (`sap_quick_report` + `sap_save_tcode_hint`)

**Files:**
- Modify: `src/sapwebguimcp/tools/quick_report_tools.py` — add `register_quick_report_tools()`
- Modify: `src/sapwebguimcp/tools/__init__.py` — export
- Modify: `src/sapwebguimcp/server.py:207` — register in WebGUI-only block
- Modify: `src/sapwebguimcp/models/__init__.py` — export new models

- [ ] **Step 1: Add `register_quick_report_tools` to `quick_report_tools.py`**

Add at the end of `src/sapwebguimcp/tools/quick_report_tools.py`:

```python
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models.quick_report_models import SaveHintResult
from sapwebguimcp.tools._hint_loader import save_hint as _save_hint


def register_quick_report_tools(mcp: FastMCP) -> None:
    """Register quick report tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        description=(
            "Execute a transaction, fill the selection screen (fields, checkboxes, "
            "radio buttons), press Execute (F8), and return the result — all in one call.\n\n"
            "Replaces the pattern: sap_transaction → ensure_screen_state → sap_keyboard(F8) "
            "→ sap_read_table.\n\n"
            "Works with any SAP report/list transaction that has a selection screen "
            "(SM37, VA05, ME2M, MB51, FBL1N, Z-transactions, etc.).\n\n"
            "After execution, you remain on the result screen. If the result is "
            "'unknown', use individual tools to investigate further.\n\n"
            "Do NOT use for:\n"
            "- SE16 (use sap_se16_query instead)\n"
            "- Transactions without selection screens (e.g., BP, VA01)\n"
            "- SE11/SE24/SE37 (use dedicated lookup tools)"
        ),
    )
    async def sap_quick_report(
        tcode: str,
        fields: dict[str, str] | None = None,
        checkboxes: dict[str, bool] | None = None,
        radios: dict[str, bool] | None = None,
        max_rows: int = 30,
        read_all: bool = False,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> QuickReportResult:
        try:
            backend = await get_backend(
                session=session, agent_id=agent_id, tool_name="sap_quick_report"
            )
        except ValueError as e:
            return QuickReportResult.failure(
                error=f"Session error: {e}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
            )
        result = await _execute_quick_report(
            backend=backend,
            tcode=tcode,
            fields=fields,
            checkboxes=checkboxes,
            radios=radios,
            max_rows=max_rows,
            read_all=read_all,
        )
        if output_file and result.success:
            import json
            from pathlib import Path

            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
            logger.info("Wrote quick report results path=%s", str(output_path))
        return result

    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False),
        description=(
            "Save a TCode hint to the user-local hints file "
            "(~/.sapwebguimcp/tcode_hints.json). "
            "Use this after sap_quick_report returned screen_type='unknown' "
            "and you have identified what the screen was. "
            "The hint will be used automatically on the next call."
        ),
    )
    async def sap_save_tcode_hint(
        tcode: str,
        post_f8: str = "table",
        known_popups: list[dict[str, str]] | None = None,
        notes: str = "",
    ) -> SaveHintResult:
        from sapwebguimcp.models.quick_report_models import PopupHint, TCodeHint

        popup_list = [PopupHint(**p) for p in (known_popups or [])]
        hint = TCodeHint(
            tcode=tcode.upper(),
            post_f8=ScreenClassification(post_f8),
            known_popups=popup_list,
            notes=notes,
        )
        hint_file = _save_hint(hint)
        return SaveHintResult(
            tcode=tcode.upper(),
            hint_file=str(hint_file),
        )
```

- [ ] **Step 2: Add export to `tools/__init__.py`**

Add to imports in `src/sapwebguimcp/tools/__init__.py`:

```python
from sapwebguimcp.tools.quick_report_tools import register_quick_report_tools
```

Add `"register_quick_report_tools"` to the `__all__` list.

- [ ] **Step 3: Register in `server.py` (WebGUI-only block)**

In `src/sapwebguimcp/server.py`, after line 209 (`register_abapgit_tools(mcp)`), add:

```python
    register_quick_report_tools(mcp)
```

This places it in the `if _backend == "webgui":` block since the screen classifier relies on DOM inspection.

- [ ] **Step 4: Add model exports to `models/__init__.py`**

Add import block to `src/sapwebguimcp/models/__init__.py` (after the workflow imports, around line 160):

```python
from sapwebguimcp.models.quick_report_models import (
    PopupHint,
    QuickReportResult,
    SaveHintResult,
    ScreenClassification,
    TCodeHint,
    TCodeHintSuggestion,
)
```

Add to the `__all__` list (after the SM37 models section, around line 280):

```python
    # Quick report models
    "PopupHint",
    "QuickReportResult",
    "SaveHintResult",
    "ScreenClassification",
    "TCodeHint",
    "TCodeHintSuggestion",
```

- [ ] **Step 5: Run existing tests to verify nothing is broken**

Run: `cd sapwebgui.mcp && python -m pytest unittests/test_server.py unittests/test_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd sapwebgui.mcp
git add src/sapwebguimcp/tools/quick_report_tools.py src/sapwebguimcp/tools/__init__.py src/sapwebguimcp/server.py src/sapwebguimcp/models/__init__.py
git commit -m "feat: register sap_quick_report and sap_save_tcode_hint tools

Both tools registered in WebGUI-only block. sap_quick_report supports
output_file parameter for JSON export consistency with SE16/SM37."
```

---

## Task 6: Linting, Formatting, Full Test Suite

**Files:**
- All new files

- [ ] **Step 1: Run formatting**

Run: `cd sapwebgui.mcp && tox -e formatting 2>&1 | tail -20`
Expected: PASS (or fix any issues)

- [ ] **Step 2: Run linting**

Run: `cd sapwebgui.mcp && tox -e linting 2>&1 | tail -20`
Expected: PASS (or fix any issues)

- [ ] **Step 3: Run type checking**

Run: `cd sapwebgui.mcp && tox -e type_check 2>&1 | tail -20`
Expected: PASS (or fix any issues)

- [ ] **Step 4: Run full test suite**

Run: `cd sapwebgui.mcp && python -m pytest unittests/ -v --tb=short 2>&1 | tail -40`
Expected: ALL PASS

- [ ] **Step 5: Fix any issues and commit**

```bash
cd sapwebgui.mcp
git add -A
git commit -m "chore: fix linting/formatting/type issues for quick_report"
```

---

## Task 7: README Documentation for Hint PR Workflow

**Files:**
- Modify: `src/sapwebguimcp/data/README.md` (or project `README.md` — check which exists)

- [ ] **Step 1: Check which README to modify**

Look at the project root for `README.md`. The hint workflow documentation should go there.

- [ ] **Step 2: Add "Contributing TCode Hints" section**

Add before the end of the README:

```markdown
## Contributing TCode Hints

When `sap_quick_report` encounters an unknown screen, the agent can save
a hint via `sap_save_tcode_hint`. These hints are stored locally in
`~/.sapwebguimcp/tcode_hints.json`.

To contribute your hints back to the project:

1. Open your local hints file:
   ```bash
   cat ~/.sapwebguimcp/tcode_hints.json
   ```
2. Copy the relevant entries into `src/sapwebguimcp/data/tcode_hints.json`
3. Open a PR with your additions

Alternatively, export only new hints with a one-liner:
```bash
python -c "
import json
from pathlib import Path
repo = json.loads(Path('src/sapwebguimcp/data/tcode_hints.json').read_text())
user = json.loads(Path.home().joinpath('.sapwebguimcp/tcode_hints.json').read_text())
new = {k: v for k, v in user.items() if k not in repo}
print(json.dumps(new, indent=2, ensure_ascii=False))
"
```

Hints for standard SAP transactions (SM37, VA05, etc.) are welcome.
Customer-specific Z-transactions should remain in your local hints file.
```

- [ ] **Step 3: Commit**

```bash
cd sapwebgui.mcp
git add README.md
git commit -m "docs: add Contributing TCode Hints section to README"
```
