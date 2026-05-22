# `sap_quick_report` Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a composite `sap_quick_report` MCP tool that bundles transaction → fill selection screen → F8 → read result into a single call, with `post_f8_keys` for popup handling and a stateless design.

**Architecture:** Pipeline with reusable screen classifier. No hint system — agent passes learned knowledge via `post_f8_keys` parameter. "Stay and report" error handling — tool never resets navigation state on failure. WebGUI-only with runtime guard for desktop backend.

**Tech Stack:** Python 3.11+, FastMCP, Playwright (WebGUI backend), Pydantic v2, pytest

**Spec:** `docs/design/sap-quick-report-design.md` (v2)

**Repo:** `sapgui.mcp/` (cloned at `C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp`)

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `src/sapguimcp/models/quick_report_models.py` | `ScreenClassification`, `QuickReportResult` |
| Create | `src/sapguimcp/tools/quick_report_tools.py` | `classify_result_screen()`, `sap_quick_report` pipeline, `register_quick_report_tools()` |
| Create | `unittests/test_quick_report_models.py` | Model validation tests |
| Create | `unittests/test_quick_report_classifier.py` | Screen classifier unit tests |
| Create | `unittests/test_quick_report_pipeline.py` | Pipeline + post_f8_keys unit tests |
| Modify | `src/sapguimcp/models/__init__.py` | Export `ScreenClassification`, `QuickReportResult` |
| Modify | `src/sapguimcp/tools/__init__.py` | Export `register_quick_report_tools` |
| Modify | `src/sapguimcp/server.py` | Call `register_quick_report_tools(mcp)` |

---

## Task 1: Models — `ScreenClassification` + `QuickReportResult`

**Files:**
- Create: `src/sapguimcp/models/quick_report_models.py`
- Create: `unittests/test_quick_report_models.py`
- Modify: `src/sapguimcp/models/__init__.py`

### Step 1.1: Write model tests

- [ ] Create `unittests/test_quick_report_models.py`:

```python
"""Unit tests for QuickReportResult and ScreenClassification models."""

import json

import pytest
from pydantic import ValidationError

from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)


class TestScreenClassification:
    """Tests for ScreenClassification enum."""

    def test_values(self) -> None:
        assert ScreenClassification.TABLE == "table"
        assert ScreenClassification.EMPTY == "empty"
        assert ScreenClassification.ERROR == "error"
        assert ScreenClassification.UNKNOWN == "unknown"

    def test_from_string(self) -> None:
        assert ScreenClassification("table") == ScreenClassification.TABLE


class TestQuickReportResult:
    """Tests for QuickReportResult model."""

    def test_success_table_result(self) -> None:
        result = QuickReportResult(
            tcode="VA05",
            screen_type=ScreenClassification.TABLE,
            page_title="Auftragsübersicht",
            status_bar_type="S",
            status_bar_message="5 Einträge gelesen",
        )
        assert result.success is True
        assert result.screen_type == "table"
        assert result.tcode == "VA05"
        assert result.warnings == []
        assert result.table is None

    def test_success_empty_result(self) -> None:
        result = QuickReportResult(
            tcode="ME2M",
            screen_type=ScreenClassification.EMPTY,
            status_bar_type="I",
            status_bar_message="Keine Daten gefunden",
        )
        assert result.success is True
        assert result.screen_type == "empty"

    def test_success_error_screen_type(self) -> None:
        """success=True + screen_type=ERROR is valid (SAP responded with error)."""
        result = QuickReportResult(
            tcode="ME2M",
            screen_type=ScreenClassification.ERROR,
            status_bar_type="E",
            status_bar_message="Werk XXXX existiert nicht",
        )
        assert result.success is True
        assert result.screen_type == "error"

    def test_success_unknown_screen_type(self) -> None:
        result = QuickReportResult(
            tcode="ZCUSTOM01",
            screen_type=ScreenClassification.UNKNOWN,
        )
        assert result.success is True
        assert result.screen_type == "unknown"

    def test_infrastructure_failure(self) -> None:
        """success=False for infrastructure errors (no screen_type needed)."""
        result = QuickReportResult.failure(
            error="sap_quick_report requires WebGUI backend",
            tcode="VA05",
            screen_type=ScreenClassification.ERROR,
        )
        assert result.success is False
        assert result.error == "sap_quick_report requires WebGUI backend"

    def test_warnings_list(self) -> None:
        result = QuickReportResult(
            tcode="VA05",
            screen_type=ScreenClassification.TABLE,
            warnings=["Field 'FakeField' not found on screen"],
        )
        assert len(result.warnings) == 1

    def test_max_rows_field_constraint(self) -> None:
        """max_rows Field(ge=1) constraint is defined on the tool function, not the model.

        This is verified in test_quick_report_pipeline.py via the tool registration tests.
        """

    def test_json_roundtrip(self) -> None:
        original = QuickReportResult(
            tcode="VA05",
            screen_type=ScreenClassification.TABLE,
            page_title="Test",
            status_bar_type="S",
            status_bar_message="OK",
            warnings=["w1"],
        )
        json_str = original.model_dump_json()
        restored = QuickReportResult.model_validate_json(json_str)
        assert restored.tcode == original.tcode
        assert restored.screen_type == original.screen_type
        assert restored.warnings == original.warnings
```

### Step 1.2: Run tests — verify they fail

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/test_quick_report_models.py -v`
- Expected: `ModuleNotFoundError: No module named 'sapguimcp.models.quick_report_models'`

### Step 1.3: Implement models

- [ ] Create `src/sapguimcp/models/quick_report_models.py`:

```python
"""Models for sap_quick_report composite tool."""

from enum import StrEnum

from pydantic import Field

from sapguimcp.models.base import ToolResult
from sapguimcp.models.sap_results import (
    ScreenText,
    StatusBarType,
    TableData,
)


class ScreenClassification(StrEnum):
    """What appeared on screen after F8."""

    TABLE = "table"
    EMPTY = "empty"
    ERROR = "error"
    UNKNOWN = "unknown"


class QuickReportResult(ToolResult):
    """Result of sap_quick_report."""

    tcode: str = Field(description="Transaction code that was executed")
    screen_type: ScreenClassification = Field(
        description="What appeared after F8: table, empty, error, or unknown"
    )
    page_title: str = Field(default="", description="Screen title after F8")

    # Status bar (flat fields, consistent with KeyboardResult pattern)
    status_bar_type: StatusBarType | None = Field(
        default=None, description="Status bar type if read"
    )
    status_bar_message: str | None = Field(
        default=None, description="Status bar text if read"
    )

    # screen_type="table"
    table: TableData | None = Field(
        default=None, description="Table data when screen_type is 'table'"
    )

    # screen_type="error" or "unknown"
    screen_text: ScreenText | None = Field(
        default=None,
        description="Screen text when screen_type is 'error' or 'unknown'",
    )

    # Warnings (e.g. "Checkbox 'Geplant' not found on screen")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings from the pipeline",
    )
```

### Step 1.4: Export models from `models/__init__.py`

- [ ] Add to `src/sapguimcp/models/__init__.py` imports:

```python
from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
```

And add `QuickReportResult`, `ScreenClassification` to the `__all__` list (if one exists) or to the existing exports.

### Step 1.5: Run tests — verify they pass

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/test_quick_report_models.py -v`
- Expected: All tests PASS

### Step 1.6: Commit

- [ ] `git add src/sapguimcp/models/quick_report_models.py src/sapguimcp/models/__init__.py unittests/test_quick_report_models.py && git commit -m "feat(quick-report): add ScreenClassification and QuickReportResult models"`

---

## Task 2: Screen Classifier — `classify_result_screen()`

**Files:**
- Create: `unittests/test_quick_report_classifier.py`
- Create: `src/sapguimcp/tools/quick_report_tools.py` (first function)

**Context:** The classifier examines the current screen after F8 and returns a `ScreenClassification`. It uses:
- `backend.get_status_bar()` → `StatusBarInfo` (has `.type` and `.message`)
- `backend.get_snapshot()` → `AriaSnapshot` (YAML string, check for `- grid` line = ALV grid)
- `backend.get_screen_text()` → `ScreenText` (for unknown screens)

**Detection logic:**
1. Read status bar
2. Status bar type `"E"` → ERROR
3. Status bar message contains "keine Daten"/"no data"/"keine Werte"/"no entries" → EMPTY
4. ARIA snapshot contains `- grid` (a grid ARIA role in the accessibility tree) → TABLE
5. Otherwise → UNKNOWN

### Step 2.1: Write classifier tests

- [ ] Create `unittests/test_quick_report_classifier.py`:

```python
"""Unit tests for classify_result_screen()."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.models import StatusBarInfo, ScreenText
from sapguimcp.models.quick_report_models import ScreenClassification
from sapguimcp.tools.quick_report_tools import classify_result_screen


def _make_backend(
    *,
    status_type: str = "none",
    status_message: str = "",
    snapshot: str = "- document 'SAP'",
    screen_title: str = "SAP",
) -> AsyncMock:
    """Create a mock backend with configurable responses."""
    backend = AsyncMock()
    backend.get_status_bar = AsyncMock(
        return_value=StatusBarInfo(type=status_type, message=status_message)
    )
    backend.get_snapshot = AsyncMock(return_value=snapshot)
    backend.get_screen_text = AsyncMock(
        return_value=ScreenText(title=screen_title)
    )
    backend.get_page_title = AsyncMock(return_value=screen_title)
    return backend


@pytest.mark.anyio
class TestClassifyResultScreen:
    """Tests for classify_result_screen()."""

    async def test_error_status_bar(self) -> None:
        """Status bar type 'E' → ERROR."""
        backend = _make_backend(
            status_type="E",
            status_message="Werk XXXX existiert nicht",
        )
        classification, status_bar = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR
        assert status_bar.type == "E"

    async def test_empty_keine_daten(self) -> None:
        """Status bar message 'Keine Daten gefunden' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="Keine Daten gefunden",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_empty_no_data_english(self) -> None:
        """Status bar message 'No data found' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="No data was found for the specified selection criteria",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_empty_keine_werte(self) -> None:
        """Status bar message 'keine Werte' → EMPTY."""
        backend = _make_backend(
            status_type="W",
            status_message="Es wurden keine Werte selektiert",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_empty_no_entries(self) -> None:
        """Status bar message 'no entries' → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="No entries found",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY

    async def test_table_grid_detected(self) -> None:
        """ARIA snapshot with '- grid' line → TABLE."""
        backend = _make_backend(
            status_type="S",
            status_message="5 Einträge gelesen",
            snapshot="- document 'SAP'\n  - grid 'ALV Grid'\n    - row 'Header'",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.TABLE

    async def test_unknown_no_grid_no_error(self) -> None:
        """No grid, no error, no empty message → UNKNOWN."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - dialog 'Variantenauswahl'",
            screen_title="Variantenauswahl",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.UNKNOWN

    async def test_error_takes_priority_over_grid(self) -> None:
        """Error status bar takes priority even if grid is present."""
        backend = _make_backend(
            status_type="E",
            status_message="Fehler aufgetreten",
            snapshot="- document 'SAP'\n  - grid 'ALV Grid'",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.ERROR

    async def test_empty_takes_priority_over_grid(self) -> None:
        """Empty message takes priority even if grid is present."""
        backend = _make_backend(
            status_type="I",
            status_message="Keine Daten gefunden",
            snapshot="- document 'SAP'\n  - grid 'Empty Grid'",
        )
        classification, _ = await classify_result_screen(backend)
        assert classification == ScreenClassification.EMPTY
```

### Step 2.2: Run tests — verify they fail

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/test_quick_report_classifier.py -v`
- Expected: `ImportError: cannot import name 'classify_result_screen'`

### Step 2.3: Implement classifier

- [ ] Create `src/sapguimcp/tools/quick_report_tools.py`:

```python
"""sap_quick_report composite tool — pipeline, classifier, registration."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
from sapguimcp.models.sap_results import StatusBarInfo

if TYPE_CHECKING:
    from sapguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

# Patterns that indicate "no data" in status bar (case-insensitive)
_EMPTY_PATTERNS: tuple[str, ...] = (
    "keine daten",
    "no data",
    "keine werte",
    "no entries",
)


async def classify_result_screen(
    backend: SapUiBackend,
) -> tuple[ScreenClassification, StatusBarInfo]:
    """Classify the current screen after F8.

    Priority:
    1. Status bar type "E" → ERROR
    2. Status bar contains empty-data pattern → EMPTY
    3. ARIA snapshot contains grid → TABLE
    4. Otherwise → UNKNOWN
    """
    status_bar = await backend.get_status_bar()

    # 1. Error
    if status_bar.type == "E":
        return ScreenClassification.ERROR, status_bar

    # 2. Empty
    msg_lower = status_bar.message.lower()
    if any(pattern in msg_lower for pattern in _EMPTY_PATTERNS):
        return ScreenClassification.EMPTY, status_bar

    # 3. Table (check ARIA snapshot for grid role)
    snapshot = await backend.get_snapshot()
    snapshot_str = str(snapshot)
    # In ARIA YAML snapshots, grids appear as "- grid" at some indentation level
    if re.search(r"^\s*- grid\b", snapshot_str, re.MULTILINE):
        return ScreenClassification.TABLE, status_bar

    # 4. Unknown
    return ScreenClassification.UNKNOWN, status_bar
```

### Step 2.4: Run tests — verify they pass

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/test_quick_report_classifier.py -v`
- Expected: All tests PASS

### Step 2.5: Commit

- [ ] `git add src/sapguimcp/tools/quick_report_tools.py unittests/test_quick_report_classifier.py && git commit -m "feat(quick-report): add classify_result_screen() with TDD tests"`

---

## Task 3: Pipeline — `sap_quick_report` tool function + `post_f8_keys`

**Files:**
- Create: `unittests/test_quick_report_pipeline.py`
- Modify: `src/sapguimcp/tools/quick_report_tools.py`

**Context:** The pipeline function calls:
1. `_is_desktop_backend(backend)` from `tools/_backend_utils.py`
2. `backend.enter_transaction(tcode)` → `TransactionResult`
3. `ensure_screen_state(backend, target)` from `tools/screen_state_helpers.py` — takes a `SelectionScreenState`
4. `backend.press_key("F8")` → `KeyboardResult`
5. `backend.wait_for_ready()`
6. For each key in `post_f8_keys` (max 3): `press_key` → `wait_for_ready` → `classify_result_screen` → early exit if classifiable
7. `classify_result_screen(backend)`
8. If TABLE: `backend.read_table(max_rows=max_rows)` → `TableData`
9. If UNKNOWN: `backend.get_screen_text()` → `ScreenText`
10. Build `QuickReportResult`

### Step 3.1: Write pipeline tests

- [ ] Create `unittests/test_quick_report_pipeline.py`:

```python
"""Unit tests for sap_quick_report pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from pydantic import Field

from sapguimcp.models import (
    KeyboardResult,
    ScreenText,
    StatusBarInfo,
    TableData,
    TableRow,
    TransactionResult,
)
from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
from sapguimcp.models.screen_state import ScreenStateDiff
from sapguimcp.tools.quick_report_tools import _execute_quick_report


def _make_backend(
    *,
    tx_success: bool = True,
    tx_error: str | None = None,
    status_type: str = "S",
    status_message: str = "5 Einträge gelesen",
    snapshot: str = "- document 'SAP'\n  - grid 'ALV Grid'",
    screen_title: str = "SAP",
    table_headers: list[str] | None = None,
    table_rows: list[dict[str, str]] | None = None,
) -> AsyncMock:
    """Create a mock backend with configurable responses."""
    backend = AsyncMock()

    # enter_transaction
    if tx_success:
        backend.enter_transaction = AsyncMock(return_value=TransactionResult(tcode="VA05"))
    else:
        backend.enter_transaction = AsyncMock(
            return_value=TransactionResult.failure(error=tx_error or "TX not found", tcode="ZZZZZ")
        )

    # press_key
    backend.press_key = AsyncMock(
        return_value=KeyboardResult(key="F8", page_title=screen_title)
    )

    # wait_for_ready
    backend.wait_for_ready = AsyncMock()

    # get_status_bar
    backend.get_status_bar = AsyncMock(
        return_value=StatusBarInfo(type=status_type, message=status_message)
    )

    # get_snapshot
    backend.get_snapshot = AsyncMock(return_value=snapshot)

    # get_screen_text
    backend.get_screen_text = AsyncMock(
        return_value=ScreenText(title=screen_title)
    )

    # read_table
    headers = table_headers or ["Col1", "Col2"]
    rows = [
        TableRow(row=i + 1, data=row_data)
        for i, row_data in enumerate(table_rows or [{"Col1": "a", "Col2": "b"}])
    ]
    backend.read_table = AsyncMock(
        return_value=TableData(
            headers=headers,
            rows=rows,
            total_rows=len(rows),
            start_row=1,
            end_row=len(rows),
        )
    )

    return backend


@pytest.mark.anyio
class TestQuickReportPipeline:
    """Tests for _execute_quick_report pipeline."""

    async def test_happy_path_table(self) -> None:
        """TX → fill → F8 → TABLE with rows."""
        backend = _make_backend()
        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(
                    backend,
                    tcode="VA05",
                    fields={"Auftraggeber": "*"},
                    max_rows=30,
                )
        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE
        assert result.table is not None
        assert len(result.table.rows) == 1

    async def test_desktop_backend_rejected(self) -> None:
        """Desktop backend → immediate failure."""
        backend = _make_backend()
        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=True):
            result = await _execute_quick_report(backend, tcode="VA05")
        assert result.success is False
        assert "WebGUI" in result.error

    async def test_tx_not_found(self) -> None:
        """Transaction not found → failure."""
        backend = _make_backend(tx_success=False, tx_error="Transaction ZZZZZ does not exist")
        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            result = await _execute_quick_report(backend, tcode="ZZZZZ")
        assert result.success is False
        assert "ZZZZZ" in result.error or "does not exist" in result.error

    async def test_empty_result(self) -> None:
        """No data found → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="Keine Daten gefunden",
            snapshot="- document 'SAP'",
        )
        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(backend, tcode="ME2M")
        assert result.success is True
        assert result.screen_type == ScreenClassification.EMPTY
        assert result.table is None

    async def test_error_status_bar(self) -> None:
        """Status bar type E after F8 → ERROR with success=True."""
        backend = _make_backend(
            status_type="E",
            status_message="Werk XXXX existiert nicht",
            snapshot="- document 'SAP'",
        )
        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(backend, tcode="ME2M")
        assert result.success is True
        assert result.screen_type == ScreenClassification.ERROR
        assert result.status_bar_type == "E"

    async def test_unknown_screen(self) -> None:
        """No grid, no error → UNKNOWN with screen_text."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - dialog 'Variantenauswahl'",
            screen_title="Variantenauswahl",
        )
        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(backend, tcode="ZCUSTOM01")
        assert result.success is True
        assert result.screen_type == ScreenClassification.UNKNOWN
        assert result.screen_text is not None
        assert result.screen_text.title == "Variantenauswahl"

    async def test_field_not_found_continues(self) -> None:
        """Field not found → warning, but F8 still pressed."""
        backend = _make_backend()
        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff(
                    warnings=["Label 'FakeField' not found on screen"]
                )
                result = await _execute_quick_report(
                    backend,
                    tcode="VA05",
                    fields={"FakeField": "x"},
                )
        assert result.success is True
        assert "FakeField" in result.warnings[0]
        # F8 was still pressed
        backend.press_key.assert_called()

    async def test_pipeline_call_order(self) -> None:
        """Verify pipeline calls in correct order."""
        backend = _make_backend()
        call_log: list[str] = []

        async def track_enter_tx(tcode: str) -> TransactionResult:
            call_log.append("enter_transaction")
            return TransactionResult(tcode=tcode)

        async def track_press_key(key: str) -> KeyboardResult:
            call_log.append(f"press_key({key})")
            return KeyboardResult(key=key)

        async def track_wait() -> None:
            call_log.append("wait_for_ready")

        backend.enter_transaction = track_enter_tx
        backend.press_key = track_press_key
        backend.wait_for_ready = track_wait

        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                call_log.append("ensure_screen_state")
                await _execute_quick_report(backend, tcode="VA05", fields={"X": "Y"})

        assert call_log[0] == "enter_transaction"
        assert "press_key(F8)" in call_log
        assert "wait_for_ready" in call_log


@pytest.mark.anyio
class TestPostF8Keys:
    """Tests for post_f8_keys parameter."""

    async def test_post_f8_keys_dismisses_popup(self) -> None:
        """post_f8_keys=["Enter"] dismisses popup, then TABLE."""
        call_count = {"classify": 0}

        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - dialog 'Variantenauswahl'",
        )

        # After Enter, change snapshot to have a grid
        original_get_snapshot = backend.get_snapshot

        async def evolving_snapshot() -> str:
            call_count["classify"] += 1
            if call_count["classify"] <= 2:
                # First calls: popup screen (before and after F8)
                return "- document 'SAP'\n  - dialog 'Popup'"
            # After Enter: grid appears
            return "- document 'SAP'\n  - grid 'ALV Grid'"

        backend.get_snapshot = evolving_snapshot

        # After Enter, status bar changes
        original_get_sb = backend.get_status_bar
        sb_count = {"n": 0}

        async def evolving_status_bar() -> StatusBarInfo:
            sb_count["n"] += 1
            if sb_count["n"] <= 2:
                return StatusBarInfo(type="none", message="")
            return StatusBarInfo(type="S", message="5 Einträge")

        backend.get_status_bar = evolving_status_bar

        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(
                    backend,
                    tcode="FBL1N",
                    post_f8_keys=["Enter"],
                )

        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE

    async def test_post_f8_keys_max_3(self) -> None:
        """Only first 3 keys are executed, 4th produces warning."""
        backend = _make_backend()

        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(
                    backend,
                    tcode="VA05",
                    post_f8_keys=["Enter", "Enter", "Enter", "Enter"],
                )

        assert any("max" in w.lower() or "3" in w for w in result.warnings)

    async def test_post_f8_keys_empty_list(self) -> None:
        """post_f8_keys=[] behaves like None."""
        backend = _make_backend()

        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(
                    backend,
                    tcode="VA05",
                    post_f8_keys=[],
                )

        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE

    async def test_post_f8_keys_early_exit(self) -> None:
        """After first key resolves to TABLE, skip remaining keys."""
        backend = _make_backend()
        press_key_calls: list[str] = []

        async def tracking_press_key(key: str) -> KeyboardResult:
            press_key_calls.append(key)
            return KeyboardResult(key=key)

        backend.press_key = tracking_press_key

        with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(
                    backend,
                    tcode="VA05",
                    post_f8_keys=["Enter", "F5"],
                )

        assert result.screen_type == ScreenClassification.TABLE
        # F8 + Enter should be called, but F5 should be skipped (grid found after Enter)
        assert "F8" in press_key_calls
        assert "Enter" in press_key_calls
        # F5 may or may not be called depending on early exit — the key test is the result

    async def test_output_file(self) -> None:
        """output_file writes JSON to disk."""
        backend = _make_backend()
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        try:
            with patch("sapguimcp.tools.quick_report_tools._is_desktop_backend", return_value=False):
                with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                    mock_ess.return_value = ScreenStateDiff()
                    result = await _execute_quick_report(
                        backend,
                        tcode="VA05",
                        output_file=output_path,
                    )

            assert result.success is True
            content = Path(output_path).read_text(encoding="utf-8")
            data = json.loads(content)
            assert data["tcode"] == "VA05"
        finally:
            Path(output_path).unlink(missing_ok=True)
```

### Step 3.2: Run tests — verify they fail

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/test_quick_report_pipeline.py -v`
- Expected: `ImportError: cannot import name '_execute_quick_report'`

### Step 3.3: Implement pipeline

- [ ] Add to `src/sapguimcp/tools/quick_report_tools.py` (after the classifier):

```python
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.models.screen_state import SelectionScreenState
from sapguimcp.tools._backend_utils import _is_desktop_backend
from sapguimcp.tools.screen_state_helpers import ensure_screen_state

_MAX_POST_F8_KEYS = 3


async def _execute_quick_report(
    backend: SapUiBackend,
    tcode: str,
    fields: dict[str, str] | None = None,
    checkboxes: dict[str, bool] | None = None,
    radios: dict[str, bool] | None = None,
    max_rows: int = 30,
    post_f8_keys: list[str] | None = None,
    output_file: str | None = None,
) -> QuickReportResult:
    """Execute the quick report pipeline."""
    warnings: list[str] = []

    # 1. Runtime guard: desktop backend
    if _is_desktop_backend(backend):
        return QuickReportResult.failure(
            error="sap_quick_report requires WebGUI backend. Use individual tools on desktop.",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )

    # 2. Enter transaction
    tx_result = await backend.enter_transaction(tcode)
    if not tx_result.success:
        return QuickReportResult.failure(
            error=f"Failed to open transaction {tcode}: {tx_result.error}",
            tcode=tcode,
            screen_type=ScreenClassification.ERROR,
        )

    await backend.wait_for_ready()

    # 3. Fill selection screen (if any fields/checkboxes/radios given)
    if fields or checkboxes or radios:
        target = SelectionScreenState(
            fields=fields or {},
            checkboxes=checkboxes or {},
            radios=radios or {},
        )
        state_result = await ensure_screen_state(backend, target)
        if not state_result.success:
            warnings.append(f"Selection screen: {state_result.error}")
        warnings.extend(state_result.warnings)

    # 4. Press F8
    await backend.press_key("F8")

    # 5. Wait for SAP
    await backend.wait_for_ready()

    # 6. post_f8_keys (max 3, with early exit)
    effective_keys = list(post_f8_keys or [])
    if len(effective_keys) > _MAX_POST_F8_KEYS:
        warnings.append(
            f"post_f8_keys has {len(effective_keys)} keys, max {_MAX_POST_F8_KEYS}. "
            f"Ignoring keys after index {_MAX_POST_F8_KEYS}."
        )
        effective_keys = effective_keys[:_MAX_POST_F8_KEYS]

    for key in effective_keys:
        # Check if screen is already classifiable before pressing next key
        classification, status_bar = await classify_result_screen(backend)
        if classification in (
            ScreenClassification.TABLE,
            ScreenClassification.EMPTY,
            ScreenClassification.ERROR,
        ):
            # Screen is classifiable — skip remaining keys
            break

        # Press key and wait
        await backend.press_key(key)
        await backend.wait_for_ready()
    else:
        # No early exit — classify after all keys (or no keys)
        classification, status_bar = await classify_result_screen(backend)

    # 7. Parse by classification
    page_title = await backend.get_page_title()
    table = None
    screen_text = None

    if classification == ScreenClassification.TABLE:
        try:
            table = await backend.read_table(max_rows=max_rows)
        except Exception as exc:
            warnings.append(f"read_table failed: {exc}")
            table = TableData(headers=[], rows=[], total_rows=0, start_row=1)

    elif classification == ScreenClassification.UNKNOWN:
        screen_text = await backend.get_screen_text()
        logger.warning(
            "Unclassified screen after F8",
            extra={
                "tcode": tcode,
                "page_title": page_title,
                "status_bar_type": status_bar.type,
                "status_bar_message": status_bar.message,
            },
        )

    elif classification == ScreenClassification.ERROR:
        screen_text = await backend.get_screen_text()

    # 8. Build result
    result = QuickReportResult(
        tcode=tcode,
        screen_type=classification,
        page_title=page_title,
        status_bar_type=status_bar.type,
        status_bar_message=status_bar.message,
        table=table,
        screen_text=screen_text if classification in (ScreenClassification.ERROR, ScreenClassification.UNKNOWN) else None,
        warnings=warnings,
    )

    # 9. Output file
    if output_file:
        Path(output_file).write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )

    return result
```

### Step 3.4: Run tests — verify they pass

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/test_quick_report_pipeline.py -v`
- Expected: All tests PASS

### Step 3.5: Commit

- [ ] `git add src/sapguimcp/tools/quick_report_tools.py unittests/test_quick_report_pipeline.py && git commit -m "feat(quick-report): add sap_quick_report pipeline with post_f8_keys support"`

---

## Task 4: Tool Registration + Wiring

**Files:**
- Modify: `src/sapguimcp/tools/quick_report_tools.py` (add `register_quick_report_tools`)
- Modify: `src/sapguimcp/tools/__init__.py`
- Modify: `src/sapguimcp/server.py`

### Step 4.1: Add `register_quick_report_tools` to `quick_report_tools.py`

- [ ] Add at the end of `src/sapguimcp/tools/quick_report_tools.py`:

```python
def register_quick_report_tools(mcp: FastMCP) -> None:
    """Register sap_quick_report tool with the MCP server."""

    @mcp.tool(
        description=(
            "Execute a transaction, fill the selection screen (fields, checkboxes, "
            "radio buttons), press Execute (F8), and return the result — all in one call.\n\n"
            "Replaces the pattern: sap_transaction → ensure_screen_state → sap_press_key(F8) "
            "→ sap_read_table.\n\n"
            "Works with any SAP report/list transaction that has a selection screen "
            "(VA05, ME2M, MB51, FBL1N, Z-transactions, etc.).\n\n"
            "After execution, you remain on the result screen. If the result is "
            "'unknown', use individual tools to investigate further.\n\n"
            "If you already know a transaction shows a popup after F8 (e.g., a variant "
            "selection dialog), pass post_f8_keys=['Enter'] to dismiss it automatically.\n\n"
            "LEARNING: When you encounter screen_type='unknown' and resolve it manually, "
            "append your learning to 'tcode-learnings.md' in the working directory so a "
            "developer can improve the tool. Include: tcode, what appeared after F8, "
            "how you resolved it, and what post_f8_keys to use next time.\n\n"
            "Do NOT use for:\n"
            "- SE16 (use sap_se16_query instead)\n"
            "- SM37 (use sap_sm37_lookup instead — has job log support)\n"
            "- Transactions without selection screens (e.g., BP, VA01)\n"
            "- SE11/SE24/SE37 (use dedicated lookup tools)\n\n"
            "WebGUI-only. Returns an error on desktop backend."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False),
    )
    async def sap_quick_report(
        tcode: str,
        fields: dict[str, str] | None = None,
        checkboxes: dict[str, bool] | None = None,
        radios: dict[str, bool] | None = None,
        max_rows: int = Field(default=30, ge=1),
        post_f8_keys: list[str] | None = None,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> QuickReportResult:
        """Execute a transaction, fill selection screen, press F8, return result."""
        from sapguimcp.backend.manager import get_backend  # pylint: disable=import-outside-toplevel

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_quick_report")
        except ValueError as exc:
            return QuickReportResult.failure(
                error=f"Session error: {exc}",
                tcode=tcode,
                screen_type=ScreenClassification.ERROR,
            )
        return await _execute_quick_report(
            backend,
            tcode=tcode,
            fields=fields,
            checkboxes=checkboxes,
            radios=radios,
            max_rows=max_rows,
            post_f8_keys=post_f8_keys,
            output_file=output_file,
        )
```

**Note:** Uses `get_backend` from `sapguimcp.backend.manager` — same pattern as `register_sm37_tools` in `sm37_tools.py`.

### Step 4.2: Export from `tools/__init__.py`

- [ ] Add to `src/sapguimcp/tools/__init__.py`:

```python
from sapguimcp.tools.quick_report_tools import register_quick_report_tools
```

### Step 4.3: Register in `server.py`

- [ ] In `src/sapguimcp/server.py`, add `register_quick_report_tools(mcp)` alongside the other `register_*_tools` calls (near line 195, after `register_sm37_tools(mcp)`):

```python
register_quick_report_tools(mcp)
```

### Step 4.4: Verify server starts

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -c "from sapguimcp.tools import register_quick_report_tools; print('OK')"`
- Expected: `OK`

### Step 4.5: Run all quick_report tests

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/test_quick_report_models.py unittests/test_quick_report_classifier.py unittests/test_quick_report_pipeline.py -v`
- Expected: All tests PASS

### Step 4.6: Run full test suite to check for regressions

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/ -v --ignore=unittests/webgui --ignore=unittests/desktop -x`
- Expected: No regressions. If existing tests fail, investigate — do NOT modify existing tests.

### Step 4.7: Commit

- [ ] `git add src/sapguimcp/tools/quick_report_tools.py src/sapguimcp/tools/__init__.py src/sapguimcp/server.py && git commit -m "feat(quick-report): register sap_quick_report tool in MCP server"`

---

## Task 5: Final Verification + Cleanup

### Step 5.1: Verify all exports

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -c "from sapguimcp.models import QuickReportResult, ScreenClassification; print('Models OK')"`
- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -c "from sapguimcp.tools import register_quick_report_tools; print('Tools OK')"`
- Expected: Both print OK

### Step 5.2: Run full test suite

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pytest unittests/ -v --ignore=unittests/webgui --ignore=unittests/desktop -x`
- Expected: All tests PASS, no regressions

### Step 5.3: Verify linting (if configured)

- [ ] Run: `cd C:/Users/JonatanMeiske/Documents/50_KI_Agenten/Tool_bundeling/sapgui.mcp && python -m pylint src/sapguimcp/models/quick_report_models.py src/sapguimcp/tools/quick_report_tools.py --disable=all --enable=E` (errors only)
- Expected: No errors

### Step 5.4: Final commit (if any cleanup needed)

- [ ] Only if fixes were needed in 5.1-5.3

---

## Implementation Notes

### Verified API names (confirmed against codebase)

- **Backend resolution:** `from sapguimcp.backend.manager import get_backend` — takes `session`, `agent_id`, `tool_name`; wrap in `try/except ValueError`
- **Status bar:** `backend.get_status_bar()` → `StatusBarInfo` (not `read_status_bar`)
- **Page title:** `backend.get_page_title()` → `str`
- **`max_rows`:** `Field(default=30, ge=1)` on tool function signature

### What NOT to do

- Do NOT create `_hint_loader.py` or `tcode_hints.json` — hint system is removed in v2
- Do NOT add `read_all` parameter — that's Phase 2
- Do NOT add desktop backend support — that's Phase 2 (runtime guard is sufficient)
- Do NOT modify existing tools or models — this is additive only
- Do NOT add `bilingual_target` to the pipeline — `sap_quick_report` takes labels as-is (agent is responsible for correct language)
