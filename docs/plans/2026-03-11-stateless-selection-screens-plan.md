# Stateless Selection Screen Transitions — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generic mechanism to read SAP selection screen state from ARIA snapshots, diff against a target, and apply minimal changes — replacing per-tool checkbox/radio hacks across all transaction tools.

**Architecture:** A pure parser extracts checkbox/radio/textbox state from ARIA snapshots. A transition helper diffs current vs. target state and applies changes via the backend protocol. Each transaction tool declares its target state declaratively. A verification re-read confirms the screen reached the target.

**Tech Stack:** Python 3.12+, Pydantic v2, Playwright (for backend implementation), pytest

**Spec:** `docs/plans/2026-03-11-stateless-selection-screens-design.md`

---

## File Structure

| File                                              | Responsibility                                                                                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/sapguimcp/models/screen_state.py`         | `SelectionScreenState`, `StateChange`, `ScreenStateDiff` Pydantic models                                                                    |
| `src/sapguimcp/parsers/screen_state_parser.py` | `parse_selection_screen_state()` — pure ARIA snapshot → state extraction                                                                    |
| `src/sapguimcp/tools/screen_state_helpers.py`  | `ensure_screen_state()`, `bilingual_target()` — transition + verify logic                                                                   |
| `src/sapguimcp/backend/protocol.py`            | Add `set_radio_button()` to `SapUiPrimitives` (line ~87)                                                                                    |
| `src/sapguimcp/backend/webgui/backend.py`      | Implement `set_radio_button()` (after `set_checkbox` at line ~595)                                                                          |
| `src/sapguimcp/models/sap_results.py`          | Add `checked: bool \| None` to `FormField` (line ~31)                                                                                       |
| `src/sapguimcp/js/detect_form_fields.js`       | Return `el.checked` for checkbox/radio (line ~113)                                                                                          |
| `src/sapguimcp/tools/sap_tools.py`             | Register `sap_set_checkbox` and `sap_set_radio_button` MCP tools                                                                            |
| `src/sapguimcp/tools/se09_tools.py`            | Replace `_set_checkbox_state`/`_try_set_checkbox`/`_set_request_type_filter`/`_set_status_filter` (lines 55-111) with `ensure_screen_state` |
| `src/sapguimcp/tools/sm37_tools.py`            | Replace `_set_status_checkboxes` (lines 50-73) + fix default-param vulnerability                                                            |
| `src/sapguimcp/tools/se11_tools.py`            | Replace `_page` radio hacks in `_wait_for_se11_table_screen`/`_wait_for_se11_structure_screen` (lines 228-289)                              |
| `unittests/test_screen_state_parser.py`           | Parser unit tests against existing + new YAML snapshots                                                                                     |
| `unittests/test_ensure_screen_state.py`           | Transition logic unit tests with mocked backend                                                                                             |
| `unittests/test_se09_exploration.py`              | New snapshot capture tests for SE09 checkbox variants                                                                                       |
| `unittests/test_sm37_exploration.py`              | New snapshot capture tests for SM37 checkbox variants                                                                                       |

---

## Chunk 1: Foundation — Models, Parser, Backend Protocol

### Task 1: Create `SelectionScreenState` and `ScreenStateDiff` models

**Files:**

- Create: `src/sapguimcp/models/screen_state.py`
- Test: `unittests/test_screen_state_parser.py` (model instantiation tests)

- [ ] **Step 1: Write model file**

```python
"""Models for SAP selection screen state parsing and transitions."""

from pydantic import BaseModel, Field

from sapguimcp.models.base import ToolResult


class SelectionScreenState(BaseModel):
    """Parsed state of a SAP selection screen.

    Represents the current (or desired target) state of all interactive
    controls on a SAP selection screen: checkboxes, radio buttons, and
    text input fields.  Parsed from ARIA snapshots where checkbox/radio
    state is encoded via the ``[checked]`` attribute and text field
    values appear after the colon (``textbox "Label": VALUE``).

    Used both for reading current screen state and for declaring the
    target state that ``ensure_screen_state()`` should transition to.
    """

    checkboxes: dict[str, bool] = Field(
        default_factory=dict,
        description="Checkbox labels mapped to their checked state (True=checked, False=unchecked)",
    )
    radios: dict[str, bool] = Field(
        default_factory=dict,
        description="Radio button labels mapped to their selected state (True=selected, False=not)",
    )
    fields: dict[str, str] = Field(
        default_factory=dict,
        description="Text field labels mapped to their current/desired value",
    )
    ambiguous_labels: list[str] = Field(
        default_factory=list,
        description="Labels that appear more than once for the same control type — unsafe to target by name",
    )


class StateChange(BaseModel):
    """A single state transition for one control.

    Records the previous and new value of a checkbox, radio button,
    or text field after ``ensure_screen_state()`` applied a change.
    """

    was: str = Field(description="Previous value before the transition")
    now: str = Field(description="New value after the transition")


class ScreenStateDiff(ToolResult):
    """Result of transitioning a SAP selection screen to a target state.

    Extends ``ToolResult`` so callers get ``success``/``error`` semantics.
    After applying all changes, ``ensure_screen_state()`` re-reads the
    ARIA snapshot and verifies every target control matches.  If any
    control did not reach its target value, ``success=False`` and
    ``mismatches`` lists the specific controls that failed.

    When ``success=True``, the screen is guaranteed to be in the
    requested target state and the tool can safely proceed.
    """

    checkboxes_changed: dict[str, StateChange] = Field(
        default_factory=dict,
        description="Checkboxes that were toggled, keyed by label",
    )
    radios_changed: dict[str, StateChange] = Field(
        default_factory=dict,
        description="Radio buttons that were changed, keyed by label",
    )
    fields_changed: dict[str, StateChange] = Field(
        default_factory=dict,
        description="Text fields that were updated, keyed by label",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Labels not found on screen (e.g. wrong-language labels)",
    )
    mismatches: list[str] = Field(
        default_factory=list,
        description="Controls that did not reach their target value after applying changes",
    )
```

- [ ] **Step 2: Write basic model tests**

Create `unittests/test_screen_state_parser.py` with initial model tests:

```python
"""Unit tests for selection screen state parsing and transition models."""

from sapguimcp.models.screen_state import (
    ScreenStateDiff,
    SelectionScreenState,
    StateChange,
)


class TestSelectionScreenStateModel:
    """Basic model instantiation tests."""

    def test_empty_state(self) -> None:
        state = SelectionScreenState()
        assert state.checkboxes == {}
        assert state.radios == {}
        assert state.fields == {}
        assert state.ambiguous_labels == []

    def test_state_with_values(self) -> None:
        state = SelectionScreenState(
            checkboxes={"Workbench": True, "Customizing": False},
            radios={"Datenbanktabelle": True},
            fields={"Benutzer": "KLEINK"},
        )
        assert state.checkboxes["Workbench"] is True
        assert state.fields["Benutzer"] == "KLEINK"


class TestScreenStateDiffModel:
    """ScreenStateDiff extends ToolResult — verify success/error semantics."""

    def test_success_diff(self) -> None:
        diff = ScreenStateDiff()
        assert diff.success is True
        assert diff.error is None

    def test_failure_diff(self) -> None:
        diff = ScreenStateDiff.failure(
            error="Checkbox 'Foo' mismatch",
            mismatches=["Checkbox 'Foo': expected True, still False"],
        )
        assert diff.success is False
        assert "mismatch" in diff.error

    def test_state_change(self) -> None:
        change = StateChange(was="False", now="True")
        assert change.was == "False"
        assert change.now == "True"
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest unittests/test_screen_state_parser.py -v -k "TestSelectionScreenStateModel or TestScreenStateDiffModel"`
Expected: 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/models/screen_state.py unittests/test_screen_state_parser.py
git commit -m "feat: add SelectionScreenState and ScreenStateDiff models"
```

---

### Task 2: Implement `parse_selection_screen_state()`

**Files:**

- Create: `src/sapguimcp/parsers/screen_state_parser.py`
- Modify: `unittests/test_screen_state_parser.py` (add parser tests)

- [ ] **Step 1: Write failing parser tests against existing snapshots**

Add to `unittests/test_screen_state_parser.py`:

```python
from pathlib import Path

import pytest

from sapguimcp.parsers.screen_state_parser import parse_selection_screen_state

TESTDATA_DIR = Path(__file__).parent / "testdata"


def _load_snapshot(relative_path: str) -> str:
    """Load a YAML snapshot from testdata/."""
    filepath = TESTDATA_DIR / relative_path
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available")
    return filepath.read_text(encoding="utf-8")


class TestParseSelectionScreenState:
    """Tests for parse_selection_screen_state against real ARIA snapshots."""

    def test_se09_initial_checkboxes(self) -> None:
        """SE09 initial screen has Customizing checked, Workbench unchecked."""
        snapshot = _load_snapshot("se09_exploration/se09_initial_de.yaml")
        state = parse_selection_screen_state(snapshot)

        assert "Customizing-Aufträge" in state.checkboxes
        assert state.checkboxes["Customizing-Aufträge"] is True
        assert "Workbench-Aufträge" in state.checkboxes
        assert state.checkboxes["Workbench-Aufträge"] is False

    def test_se09_initial_status_checkboxes(self) -> None:
        """SE09 initial screen has Änderbar and Freigegeben both checked."""
        snapshot = _load_snapshot("se09_exploration/se09_initial_de.yaml")
        state = parse_selection_screen_state(snapshot)

        assert state.checkboxes["Änderbar"] is True
        assert state.checkboxes["Freigegeben"] is True

    def test_se09_initial_textbox(self) -> None:
        """SE09 initial screen has a Benutzer textbox."""
        snapshot = _load_snapshot("se09_exploration/se09_initial_de.yaml")
        state = parse_selection_screen_state(snapshot)

        assert "Benutzer" in state.fields

    def test_se09_no_transports_disabled_checkboxes_excluded(self) -> None:
        """Disabled checkboxes should be excluded from state (can't be changed)."""
        snapshot = _load_snapshot("se09_exploration/se09_no_transports_de.yaml")
        state = parse_selection_screen_state(snapshot)

        # All checkboxes in no_transports snapshot are [disabled]
        assert len(state.checkboxes) == 0

    def test_sm37_initial_checkboxes(self) -> None:
        """SM37 initial screen has 6 status checkboxes, 5 checked + 1 unchecked."""
        snapshot = _load_snapshot("sm37_exploration/sm37_initial_de.yaml")
        state = parse_selection_screen_state(snapshot)

        assert state.checkboxes["Geplant"] is False
        assert state.checkboxes["Freigegeben"] is True
        assert state.checkboxes["Bereit"] is True
        assert state.checkboxes["Aktiv"] is True
        assert state.checkboxes["Fertig"] is True
        assert state.checkboxes["Abgebrochen"] is True

    def test_se11_initial_radio_buttons(self) -> None:
        """SE11 initial screen has radio buttons with Datenbanktabelle selected."""
        snapshot = _load_snapshot("yaml_snapshots/se11_initial_de.yaml")
        state = parse_selection_screen_state(snapshot)

        assert state.radios.get("Datenbanktabelle") is True
        # At least one other radio should be unselected
        unselected = [k for k, v in state.radios.items() if not v]
        assert len(unselected) >= 1

    def test_sm30_initial_radio_buttons(self) -> None:
        """SM30 initial screen has 3 radio buttons."""
        snapshot = _load_snapshot("sm30_exploration/sm30_initial_de.yaml")
        state = parse_selection_screen_state(snapshot)

        assert state.radios["Keine Einschränkungen"] is True
        assert state.radios["Bedingungen eingeben"] is False
        assert state.radios["Variante"] is False

    def test_menuitemradio_ignored(self) -> None:
        """menuitemradio in system info should not appear in radios dict."""
        snapshot = _load_snapshot("se09_exploration/se09_initial_de.yaml")
        state = parse_selection_screen_state(snapshot)

        # System info contains menuitemradio "System S4U (100)" — should be excluded
        assert not any("S4U" in label for label in state.radios)

    def test_empty_snapshot(self) -> None:
        """Empty snapshot returns empty state."""
        state = parse_selection_screen_state("")
        assert state.checkboxes == {}
        assert state.radios == {}
        assert state.fields == {}

    def test_ambiguous_checkbox_labels_detected(self) -> None:
        """If two checkboxes share a label, it should be flagged as ambiguous."""
        fake_snapshot = (
            '- checkbox "Status" [checked]:  Status\n'
            '- checkbox "Status":  Status\n'
        )
        state = parse_selection_screen_state(fake_snapshot)
        assert "Status" in state.ambiguous_labels
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/test_screen_state_parser.py::TestParseSelectionScreenState -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sapguimcp.parsers.screen_state_parser'`

- [ ] **Step 3: Implement the parser**

Create `src/sapguimcp/parsers/screen_state_parser.py`:

```python
"""Parse SAP selection screen state from ARIA accessibility snapshots.

Extracts checkbox, radio button, and text field states from the YAML-like
ARIA snapshot format that Playwright produces.  This is a pure function
with no SAP or browser interaction — it only processes strings.

ARIA format examples (from real SAP screens)::

    - checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge
    - checkbox "Customizing-Aufträge":  Customizing-Aufträge
    - checkbox "Änderbar" [checked] [disabled]:  Änderbar
    - radio "Datenbanktabelle" [checked]
    - radio "View"
    - textbox "Benutzer": KLEINK
    - menuitemradio "System S4U (100)" [checked]:   ← ignored (system info)
"""

import re
from collections import Counter

from sapguimcp.models.screen_state import SelectionScreenState

__all__ = ["parse_selection_screen_state"]

# Matches: checkbox "LABEL" optionally [checked], optionally [disabled]
# Captures: label, flags (everything in brackets), trailing text
_CHECKBOX_RE = re.compile(
    r'-\s+checkbox\s+"([^"]+)"'  # - checkbox "LABEL"
    r"((?:\s+\[[^\]]+\])*)"  # optional [checked] [disabled] etc.
)

# Matches: radio "LABEL" optionally [checked]
# menuitemradio is excluded by a guard before this regex runs
_RADIO_RE = re.compile(
    r'-\s+radio\s+"([^"]+)"'  # - radio "LABEL"
    r"((?:\s+\[[^\]]+\])*)"  # optional [checked] etc.
)

# Matches: textbox "LABEL": VALUE
_TEXTBOX_RE = re.compile(
    r'-\s+textbox\s+"([^"]+)":\s*(.*)'  # - textbox "LABEL": VALUE
)


def parse_selection_screen_state(snapshot: str) -> SelectionScreenState:
    """Parse checkbox, radio, and text field state from an ARIA snapshot.

    Args:
        snapshot: ARIA accessibility snapshot string (YAML-like format).

    Returns:
        SelectionScreenState with all detected controls and their current state.
        Disabled controls are excluded (they cannot be changed).
        Ambiguous labels (same label, same control type, multiple occurrences)
        are listed in ``ambiguous_labels``.
    """
    checkboxes: dict[str, bool] = {}
    radios: dict[str, bool] = {}
    fields: dict[str, str] = {}

    # Track label counts per type for ambiguity detection
    checkbox_labels: list[str] = []
    radio_labels: list[str] = []

    for line in snapshot.splitlines():
        # --- Checkboxes ---
        cb_match = _CHECKBOX_RE.search(line)
        if cb_match:
            label = cb_match.group(1)
            flags = cb_match.group(2)
            if "[disabled]" in flags:
                continue
            checkboxes[label] = "[checked]" in flags
            checkbox_labels.append(label)
            continue

        # --- Radio buttons (skip menuitemradio) ---
        if "menuitemradio" in line:
            continue
        radio_match = _RADIO_RE.search(line)
        if radio_match:
            label = radio_match.group(1)
            flags = radio_match.group(2)
            if "[disabled]" in flags:
                continue
            radios[label] = "[checked]" in flags
            radio_labels.append(label)
            continue

        # --- Text fields ---
        tb_match = _TEXTBOX_RE.search(line)
        if tb_match:
            label = tb_match.group(1)
            value = tb_match.group(2).strip()
            if "[disabled]" in line or "[readonly]" in line:
                continue
            fields[label] = value
            continue

    # Detect ambiguous labels (same label appears 2+ times for same type)
    ambiguous: list[str] = []
    for label, count in Counter(checkbox_labels).items():
        if count > 1:
            ambiguous.append(label)
    for label, count in Counter(radio_labels).items():
        if count > 1:
            ambiguous.append(label)

    return SelectionScreenState(
        checkboxes=checkboxes,
        radios=radios,
        fields=fields,
        ambiguous_labels=ambiguous,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/test_screen_state_parser.py::TestParseSelectionScreenState -v`
Expected: All tests PASS

- [ ] **Step 5: Run linting**

Run: `tox -e linting && tox -e type_check`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/parsers/screen_state_parser.py unittests/test_screen_state_parser.py
git commit -m "feat: add parse_selection_screen_state() for ARIA snapshot state extraction"
```

---

### Task 3: Add `set_radio_button()` to backend protocol and implementation

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py:86-87` (add method after `set_checkbox`)
- Modify: `src/sapguimcp/backend/webgui/backend.py:582-595` (add impl after `set_checkbox`)

- [ ] **Step 1: Add to protocol**

In `src/sapguimcp/backend/protocol.py`, after the `set_checkbox` method (line 87):

```python
    async def set_radio_button(self, label: str) -> None:
        """Select a radio button by its ARIA label. Raises ``ValueError`` if not found."""
```

- [ ] **Step 2: Implement in WebGuiBackend**

In `src/sapguimcp/backend/webgui/backend.py`, after the `set_checkbox` method (after line 595):

```python
    async def set_radio_button(self, label: str) -> None:
        """Select a radio button by its ARIA label."""
        radio = self._page.get_by_role("radio", name=label, exact=True)
        if await radio.count() == 0:
            # Fallback: case-insensitive
            radio = self._page.get_by_role(
                "radio", name=re.compile(re.escape(label), re.IGNORECASE)
            )
            if await radio.count() == 0:
                raise ValueError(f"Radio button '{label}' not found")
            radio = radio.first
        await radio.check()
        await self._page.wait_for_timeout(200)
```

- [ ] **Step 3: Run type check**

Run: `tox -e type_check`
Expected: Clean — the protocol and implementation signatures match

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py
git commit -m "feat: add set_radio_button() to backend protocol and WebGUI implementation"
```

---

### Task 4: Implement `ensure_screen_state()` with tests

**Files:**

- Create: `src/sapguimcp/tools/screen_state_helpers.py`
- Create: `unittests/test_ensure_screen_state.py`

- [ ] **Step 1: Write failing transition tests with mocked backend**

Create `unittests/test_ensure_screen_state.py`:

```python
"""Unit tests for ensure_screen_state() transition logic.

Uses a mock backend to verify that only the necessary set_checkbox /
set_radio_button / fill_field calls are made based on the diff between
current and target state.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from sapguimcp.models.screen_state import SelectionScreenState
from sapguimcp.tools.screen_state_helpers import ensure_screen_state


def _mock_backend(snapshot_before: str, snapshot_after: str) -> AsyncMock:
    """Create a mock backend that returns two snapshots (before/after apply)."""
    backend = AsyncMock()
    backend.get_snapshot = AsyncMock(side_effect=[snapshot_before, snapshot_after])
    backend.set_checkbox = AsyncMock()
    backend.set_radio_button = AsyncMock()
    backend.fill_field = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    return backend


# --- Snapshot fragments for testing ---
_SE09_WORKBENCH_ONLY = """\
- checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge
- checkbox "Customizing-Aufträge":  Customizing-Aufträge
- checkbox "Änderbar" [checked]:  Änderbar
- checkbox "Freigegeben":  Freigegeben
- textbox "Benutzer": KLEINK
"""

_SE09_BOTH_CHECKED = """\
- checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge
- checkbox "Customizing-Aufträge" [checked]:  Customizing-Aufträge
- checkbox "Änderbar" [checked]:  Änderbar
- checkbox "Freigegeben":  Freigegeben
- textbox "Benutzer": KLEINK
"""

_SE11_TABLE_SELECTED = """\
- radio "Datenbanktabelle" [checked]
- radio "View"
- radio "Datentyp"
- textbox "Datenbankrelation": T000
"""

_SE11_STRUCTURE_SELECTED = """\
- radio "Datenbanktabelle"
- radio "View"
- radio "Datentyp" [checked]
- textbox "Datenbankrelation": BAPIRET2
"""


class TestEnsureScreenStateCheckboxes:
    """Test checkbox transitions."""

    @pytest.mark.anyio
    async def test_no_changes_when_already_matching(self) -> None:
        """If current state matches target, no backend calls should be made."""
        backend = _mock_backend(_SE09_WORKBENCH_ONLY, _SE09_WORKBENCH_ONLY)
        target = SelectionScreenState(
            checkboxes={"Workbench-Aufträge": True, "Customizing-Aufträge": False},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert diff.checkboxes_changed == {}
        backend.set_checkbox.assert_not_called()

    @pytest.mark.anyio
    async def test_toggle_checkbox(self) -> None:
        """Should check Customizing and verify it stuck."""
        backend = _mock_backend(_SE09_WORKBENCH_ONLY, _SE09_BOTH_CHECKED)
        target = SelectionScreenState(
            checkboxes={"Workbench-Aufträge": True, "Customizing-Aufträge": True},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert "Customizing-Aufträge" in diff.checkboxes_changed
        backend.set_checkbox.assert_called_once_with("Customizing-Aufträge", True)
        # wait_for_ready called after checkbox change
        assert backend.wait_for_ready.call_count >= 1

    @pytest.mark.anyio
    async def test_verification_failure(self) -> None:
        """If checkbox didn't stick, return success=False with mismatch details."""
        # After applying, the screen still shows Customizing unchecked
        backend = _mock_backend(_SE09_WORKBENCH_ONLY, _SE09_WORKBENCH_ONLY)
        target = SelectionScreenState(
            checkboxes={"Customizing-Aufträge": True},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is False
        assert len(diff.mismatches) == 1
        assert "Customizing-Aufträge" in diff.mismatches[0]

    @pytest.mark.anyio
    async def test_missing_label_warning(self) -> None:
        """Labels not found on screen produce warnings, not errors."""
        backend = _mock_backend(_SE09_WORKBENCH_ONLY, _SE09_WORKBENCH_ONLY)
        target = SelectionScreenState(
            checkboxes={"NonExistentCheckbox": True},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True  # missing labels are warnings, not failures
        assert any("NonExistentCheckbox" in w for w in diff.warnings)
        backend.set_checkbox.assert_not_called()


class TestEnsureScreenStateRadios:
    """Test radio button transitions."""

    @pytest.mark.anyio
    async def test_select_different_radio(self) -> None:
        """Switch from table to structure radio."""
        backend = _mock_backend(_SE11_TABLE_SELECTED, _SE11_STRUCTURE_SELECTED)
        target = SelectionScreenState(
            radios={"Datentyp": True},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert "Datentyp" in diff.radios_changed
        backend.set_radio_button.assert_called_once_with("Datentyp")

    @pytest.mark.anyio
    async def test_radio_already_selected(self) -> None:
        """No call if radio already selected."""
        backend = _mock_backend(_SE11_TABLE_SELECTED, _SE11_TABLE_SELECTED)
        target = SelectionScreenState(
            radios={"Datenbanktabelle": True},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert diff.radios_changed == {}
        backend.set_radio_button.assert_not_called()


class TestEnsureScreenStateFields:
    """Test text field transitions."""

    @pytest.mark.anyio
    async def test_fill_field(self) -> None:
        """Should fill field when value differs."""
        after = _SE11_TABLE_SELECTED.replace("T000", "MARA")
        backend = _mock_backend(_SE11_TABLE_SELECTED, after)
        target = SelectionScreenState(
            fields={"Datenbankrelation": "MARA"},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert "Datenbankrelation" in diff.fields_changed
        backend.fill_field.assert_called_once_with("Datenbankrelation", "MARA")


class TestEnsureScreenStateAmbiguity:
    """Test that ambiguous labels are refused."""

    @pytest.mark.anyio
    async def test_refuses_ambiguous_checkbox(self) -> None:
        """Should fail if targeting an ambiguous label."""
        ambiguous_snapshot = (
            '- checkbox "Status" [checked]:  Status\n'
            '- checkbox "Status":  Status\n'
        )
        backend = _mock_backend(ambiguous_snapshot, ambiguous_snapshot)
        target = SelectionScreenState(
            checkboxes={"Status": True},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is False
        assert "ambiguous" in diff.error.lower()
        backend.set_checkbox.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/test_ensure_screen_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sapguimcp.tools.screen_state_helpers'`

- [ ] **Step 3: Implement `ensure_screen_state()` and `bilingual_target()`**

Create `src/sapguimcp/tools/screen_state_helpers.py`:

```python
"""Helpers for reading and transitioning SAP selection screen state.

The core function ``ensure_screen_state()`` reads the current screen
state from an ARIA snapshot, diffs it against a target state, applies
only the necessary changes, and verifies the screen reached the target.

``bilingual_target()`` is a convenience to merge DE/EN label variants
into a single ``SelectionScreenState``.
"""

import logging
from typing import TYPE_CHECKING

from sapguimcp.models.screen_state import (
    ScreenStateDiff,
    SelectionScreenState,
    StateChange,
)
from sapguimcp.parsers.screen_state_parser import parse_selection_screen_state

if TYPE_CHECKING:
    from sapguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

__all__ = ["bilingual_target", "ensure_screen_state"]


async def ensure_screen_state(
    backend: "SapUiBackend",
    target: SelectionScreenState,
) -> ScreenStateDiff:
    """Read current screen state, diff against target, apply changes, verify.

    Args:
        backend: SAP UI backend instance.
        target: Desired selection screen state.

    Returns:
        ScreenStateDiff with ``success=True`` if the screen reached the
        target state, or ``success=False`` with ``mismatches`` if not.
    """
    snapshot = await backend.get_snapshot()
    current = parse_selection_screen_state(snapshot)

    diff = ScreenStateDiff()

    # Refuse ambiguous labels
    ambiguous_targets = set(target.checkboxes) | set(target.radios) | set(target.fields)
    ambiguous_hits = ambiguous_targets & set(current.ambiguous_labels)
    if ambiguous_hits:
        return ScreenStateDiff.failure(
            error=f"Ambiguous labels on screen — cannot safely target: {', '.join(sorted(ambiguous_hits))}",
        )

    # --- Apply checkbox changes ---
    for label, desired in target.checkboxes.items():
        actual = current.checkboxes.get(label)
        if actual is None:
            diff.warnings.append(f"Checkbox '{label}' not found on screen")
            continue
        if actual != desired:
            try:
                await backend.set_checkbox(label, desired)
                await backend.wait_for_ready()
                diff.checkboxes_changed[label] = StateChange(
                    was=str(actual), now=str(desired),
                )
            except (ValueError, Exception) as e:  # pylint: disable=broad-exception-caught
                diff.warnings.append(f"Failed to set checkbox '{label}': {e}")

    # --- Apply radio button changes ---
    for label, desired in target.radios.items():
        actual = current.radios.get(label)
        if actual is None:
            diff.warnings.append(f"Radio '{label}' not found on screen")
            continue
        if actual != desired and desired is True:
            try:
                await backend.set_radio_button(label)
                await backend.wait_for_ready()
                diff.radios_changed[label] = StateChange(
                    was=str(actual), now=str(desired),
                )
            except (ValueError, Exception) as e:  # pylint: disable=broad-exception-caught
                diff.warnings.append(f"Failed to set radio '{label}': {e}")

    # --- Apply text field changes ---
    for label, desired in target.fields.items():
        actual = current.fields.get(label)
        if actual != desired:
            try:
                await backend.fill_field(label, desired)
                await backend.wait_for_ready()
                diff.fields_changed[label] = StateChange(
                    was=actual or "", now=desired,
                )
            except (ValueError, Exception) as e:  # pylint: disable=broad-exception-caught
                diff.warnings.append(f"Failed to fill field '{label}': {e}")

    # --- Verification: re-read snapshot and compare ---
    verify_snapshot = await backend.get_snapshot()
    actual_after = parse_selection_screen_state(verify_snapshot)

    for label, desired in target.checkboxes.items():
        actual = actual_after.checkboxes.get(label)
        if actual is not None and actual != desired:
            diff.mismatches.append(
                f"Checkbox '{label}': expected {desired}, still {actual}"
            )

    for label, desired in target.radios.items():
        if not desired:
            continue  # only verify selected radios
        actual = actual_after.radios.get(label)
        if actual is not None and actual != desired:
            diff.mismatches.append(
                f"Radio '{label}': expected selected, still unselected"
            )

    for label, desired in target.fields.items():
        actual = actual_after.fields.get(label)
        if actual is not None and actual != desired:
            diff.mismatches.append(
                f"Field '{label}': expected '{desired}', still '{actual}'"
            )

    if diff.mismatches:
        return ScreenStateDiff.failure(
            error=f"Screen state verification failed: {'; '.join(diff.mismatches)}",
            checkboxes_changed=diff.checkboxes_changed,
            radios_changed=diff.radios_changed,
            fields_changed=diff.fields_changed,
            warnings=diff.warnings,
            mismatches=diff.mismatches,
        )

    return diff


def bilingual_target(
    *,
    checkboxes_de: dict[str, bool] | None = None,
    checkboxes_en: dict[str, bool] | None = None,
    radios_de: dict[str, bool] | None = None,
    radios_en: dict[str, bool] | None = None,
    fields_de: dict[str, str] | None = None,
    fields_en: dict[str, str] | None = None,
) -> SelectionScreenState:
    """Merge DE and EN label variants into one target state.

    ``ensure_screen_state`` matches by label — if the screen is German,
    German labels match; English labels produce a "not found" warning
    (harmless).  Vice versa for English screens.
    """
    return SelectionScreenState(
        checkboxes={**(checkboxes_de or {}), **(checkboxes_en or {})},
        radios={**(radios_de or {}), **(radios_en or {})},
        fields={**(fields_de or {}), **(fields_en or {})},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/test_ensure_screen_state.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full linting + type check**

Run: `tox -e linting && tox -e type_check`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/tools/screen_state_helpers.py unittests/test_ensure_screen_state.py
git commit -m "feat: add ensure_screen_state() transition logic with verification"
```

---

### Task 5: Enrich `FormField` with `checked` state + fix JS

**Files:**

- Modify: `src/sapguimcp/models/sap_results.py:25-39`
- Modify: `src/sapguimcp/js/detect_form_fields.js:109-116`

- [ ] **Step 1: Add `checked` field to `FormField`**

In `src/sapguimcp/models/sap_results.py`, add after `current_value` (line 31):

```python
    checked: bool | None = Field(
        default=None,
        description="True/False for checkbox/radio fields, None for text/dropdown",
    )
```

- [ ] **Step 2: Fix `detect_form_fields.js` to return `el.checked`**

In `src/sapguimcp/js/detect_form_fields.js`, replace the field construction (lines 109-116):

```javascript
const field = {
    id: el.id || '',
    label: getLabel(el),
    field_type: fieldType,
    current_value: el.value || null,
    checked: fieldType === 'checkbox' || fieldType === 'radio' ? el.checked : null,
    readonly: isReadonly,
    options: null, // Will be populated separately for dropdowns if requested
};
```

- [ ] **Step 3: Add `FormField.checked` unit test**

Add a quick test (e.g., in `unittests/test_screen_state_parser.py` or a new small test file):

```python
class TestFormFieldCheckedField:
    """Verify FormField model accepts and serializes the new checked field."""

    def test_checkbox_field_checked(self) -> None:
        from sapguimcp.models.sap_results import FormField, SapFieldType
        field = FormField(id="cb1", label="Workbench", field_type=SapFieldType.CHECKBOX, checked=True)
        assert field.checked is True
        data = field.model_dump()
        assert data["checked"] is True

    def test_text_field_checked_is_none(self) -> None:
        from sapguimcp.models.sap_results import FormField, SapFieldType
        field = FormField(id="txt1", label="Name", field_type=SapFieldType.TEXT)
        assert field.checked is None
        data = field.model_dump()
        assert data["checked"] is None

    def test_radio_field_unchecked(self) -> None:
        from sapguimcp.models.sap_results import FormField, SapFieldType
        field = FormField(id="rb1", label="View", field_type=SapFieldType.RADIO, checked=False)
        assert field.checked is False
```

- [ ] **Step 4: Run tests and type check**

Run: `python -m pytest unittests/test_screen_state_parser.py -v -k "TestFormFieldCheckedField" && tox -e type_check && tox -e linting`
Expected: All clean

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/models/sap_results.py src/sapguimcp/js/detect_form_fields.js unittests/test_screen_state_parser.py
git commit -m "feat: add checked state to FormField model and detect_form_fields.js"
```

---

### Task 6: Register `sap_set_checkbox` and `sap_set_radio_button` MCP tools

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py` (add two new tool registrations)

These expose the backend's `set_checkbox` and `set_radio_button` as MCP tools so the LLM can toggle controls on unknown screens.

- [ ] **Step 1: Add `sap_set_checkbox` tool**

Add near the other form-related tools in `sap_tools.py` (after `sap_set_field`):

```python
    @mcp.tool(
        description=(
            "Set a SAP checkbox to checked or unchecked by its label text.\n\n"
            "Use sap_get_form_fields first to see available checkboxes and their current state.\n\n"
            "Args:\n"
            "- label: Checkbox label text (e.g., 'Workbench-Aufträge', 'Freigegeben')\n"
            "- checked: True to check, False to uncheck\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session'
        ),
    )
    async def sap_set_checkbox(
        label: str,
        checked: bool,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SetFieldResult:
        """Set a SAP checkbox to checked or unchecked."""
        if not label:
            return SetFieldResult.failure("label cannot be empty", label="", value=str(checked))

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_set_checkbox")
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value=str(checked))

        try:
            popup = await backend.check_popup()
            if popup:
                return SetFieldResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    label=label, value=str(checked), popup=popup,
                )
            await backend.set_checkbox(label, checked)
            return SetFieldResult(label=label, value=str(checked))
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value=str(checked))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Setting checkbox")
            return SetFieldResult.failure(f"Error setting checkbox: {e}", label=label, value=str(checked))
```

- [ ] **Step 2: Add `sap_set_radio_button` tool**

```python
    @mcp.tool(
        description=(
            "Select a SAP radio button by its label text.\n\n"
            "Use sap_get_form_fields first to see available radio buttons and which is selected.\n\n"
            "Args:\n"
            "- label: Radio button label text (e.g., 'Datenbanktabelle', 'Database table')\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session'
        ),
    )
    async def sap_set_radio_button(
        label: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SetFieldResult:
        """Select a SAP radio button."""
        if not label:
            return SetFieldResult.failure("label cannot be empty", label="", value="")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_set_radio_button")
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value="selected")

        try:
            popup = await backend.check_popup()
            if popup:
                return SetFieldResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    label=label, value="selected", popup=popup,
                )
            await backend.set_radio_button(label)
            return SetFieldResult(label=label, value="selected")
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value="selected")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Setting radio button")
            return SetFieldResult.failure(f"Error setting radio button: {e}", label=label, value="selected")
```

- [ ] **Step 3: Run linting and type check**

Run: `tox -e linting && tox -e type_check`
Expected: Clean

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py
git commit -m "feat: expose sap_set_checkbox and sap_set_radio_button as MCP tools"
```

---

## Chunk 2: Snapshot Collection + Migrate SE09

### Task 7: Collect SE09 selection screen snapshots for different checkbox states

**Files:**

- Modify: `unittests/test_se09_exploration.py` (add snapshot capture tests)

The goal is to capture snapshots with different checkbox combinations, to use as test fixtures for snapshot-pair transition tests. These tests require a live SAP system (they are `@pytest.mark.anyio` exploration tests).

- [ ] **Step 1: Add SE09 checkbox-variant snapshot capture tests**

Add to `unittests/test_se09_exploration.py`:

```python
@pytest.mark.anyio
async def test_se09_capture_workbench_only_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SE09 with Workbench=checked, Customizing=unchecked."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Explicitly set checkboxes to desired state
    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Workbench-Aufträge", "checked": True}, SetFieldResult,
    )
    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Customizing-Aufträge", "checked": False}, SetFieldResult,
    )

    await capture_yaml_snapshot(sap_mcp_client, "se09_workbench_only", overwrite=True)


@pytest.mark.anyio
async def test_se09_capture_customizing_only_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SE09 with Workbench=unchecked, Customizing=checked."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Workbench-Aufträge", "checked": False}, SetFieldResult,
    )
    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Customizing-Aufträge", "checked": True}, SetFieldResult,
    )

    await capture_yaml_snapshot(sap_mcp_client, "se09_customizing_only", overwrite=True)


@pytest.mark.anyio
async def test_se09_capture_both_types_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SE09 with both Workbench and Customizing checked."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Workbench-Aufträge", "checked": True}, SetFieldResult,
    )
    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Customizing-Aufträge", "checked": True}, SetFieldResult,
    )

    await capture_yaml_snapshot(sap_mcp_client, "se09_both_types", overwrite=True)


@pytest.mark.anyio
async def test_se09_capture_released_only_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SE09 with Änderbar=unchecked, Freigegeben=checked."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Änderbar", "checked": False}, SetFieldResult,
    )
    await call_tool_typed(
        sap_mcp_client, "sap_set_checkbox",
        {"label": "Freigegeben", "checked": True}, SetFieldResult,
    )

    await capture_yaml_snapshot(sap_mcp_client, "se09_released_only", overwrite=True)
```

Note: `SetFieldResult` must be imported at the top of the file. These tests depend on Task 6 (`sap_set_checkbox` MCP tool).

- [ ] **Step 2: Run exploration tests against live SAP**

Run: `SAP_LANGUAGE=DE pytest unittests/test_se09_exploration.py -v -s -k "capture"`
Expected: 4 new YAML snapshots in `unittests/testdata/se09_exploration/`

- [ ] **Step 3: Add snapshot-pair parser tests**

Add to `unittests/test_screen_state_parser.py`:

```python
class TestSnapshotPairTransitions:
    """Test state parsing across snapshot pairs to validate transitions."""

    def test_se09_workbench_to_customizing(self) -> None:
        """Parsing workbench-only and customizing-only should show opposite states."""
        wb = _load_snapshot("se09_exploration/se09_workbench_only_de.yaml")
        cust = _load_snapshot("se09_exploration/se09_customizing_only_de.yaml")

        state_wb = parse_selection_screen_state(wb)
        state_cust = parse_selection_screen_state(cust)

        assert state_wb.checkboxes["Workbench-Aufträge"] is True
        assert state_wb.checkboxes["Customizing-Aufträge"] is False
        assert state_cust.checkboxes["Workbench-Aufträge"] is False
        assert state_cust.checkboxes["Customizing-Aufträge"] is True

    def test_se09_both_types_has_both_checked(self) -> None:
        """Both-types snapshot should have both checkboxes checked."""
        both = _load_snapshot("se09_exploration/se09_both_types_de.yaml")
        state = parse_selection_screen_state(both)

        assert state.checkboxes["Workbench-Aufträge"] is True
        assert state.checkboxes["Customizing-Aufträge"] is True
```

- [ ] **Step 4: Run parser tests**

Run: `python -m pytest unittests/test_screen_state_parser.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add unittests/test_se09_exploration.py unittests/testdata/se09_exploration/ unittests/test_screen_state_parser.py
git commit -m "feat: collect SE09 selection screen snapshots and add snapshot-pair parser tests"
```

---

### Task 8: Migrate SE09 to `ensure_screen_state()`

**Files:**

- Modify: `src/sapguimcp/tools/se09_tools.py:55-111` (replace 4 helper functions)
- Modify: `src/sapguimcp/tools/se09_tools.py:282-286` (replace filter calls in `_lookup_transports`)

**Note:** This changes the checkbox labels from substring (`"Workbench"`) to exact ARIA labels (`"Workbench-Aufträge"`). The `set_checkbox` backend method uses `exact=True` first, so exact labels are more robust and skip the case-insensitive fallback path.

- [ ] **Step 1: Replace SE09 checkbox helpers with `ensure_screen_state`**

In `src/sapguimcp/tools/se09_tools.py`:

1. Remove functions `_set_checkbox_state` (lines 55-63), `_set_request_type_filter` (lines 65-80), `_try_set_checkbox` (lines 82-91), `_set_status_filter` (lines 94-111).

2. Add import at top:

```python
from sapguimcp.tools.screen_state_helpers import bilingual_target, ensure_screen_state
```

3. Replace the filter section in `_lookup_transports` (lines 274-281) with:

```python
    # Build target state for selection screen
    target = bilingual_target(
        checkboxes_de={
            "Workbench-Aufträge": request_type in ("all", "workbench"),
            "Customizing-Aufträge": request_type in ("all", "customizing"),
            "Änderbar": status in ("all", "modifiable"),
            "Freigegeben": status in ("all", "released"),
        },
        checkboxes_en={
            "Workbench Requests": request_type in ("all", "workbench"),
            "Customizing Requests": request_type in ("all", "customizing"),
            "Modifiable": status in ("all", "modifiable"),
            "Released": status in ("all", "released"),
        },
        fields_de={"Benutzer": username.upper()} if username else {},
        fields_en={"User": username.upper()} if username else {},
    )
    state_result = await ensure_screen_state(backend, target)
    if not state_result.success:
        return TransportListResult.failure(
            error=f"Failed to set SE09 selection screen: {state_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )
```

Also remove the separate `_fill_user_field` call (line 275-276) since the user field is now part of the target state.

- [ ] **Step 2: Remove unused imports**

Remove imports that are no longer needed: `SE09_USER_FIELD_DE`, `SE09_USER_FIELD_EN`, `SE09_MODIFIABLE_DE`, `SE09_MODIFIABLE_EN`, `SE09_RELEASED_DE`, `SE09_RELEASED_EN` from the `lang` import.

- [ ] **Step 3: Run existing SE09 integration tests**

Run: `python -m pytest unittests/test_se09_integration.py -v`
Expected: All existing tests PASS (behavior unchanged, only internals refactored)

- [ ] **Step 4: Run linting + type check**

Run: `tox -e linting && tox -e type_check`
Expected: Clean

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/tools/se09_tools.py
git commit -m "refactor: migrate SE09 to ensure_screen_state(), remove ad-hoc checkbox helpers"
```

---

## Chunk 3: Migrate SM37 + SE11

### Task 9: Collect SM37 snapshot variants + migrate SM37

**Files:**

- Modify: `src/sapguimcp/tools/sm37_tools.py:50-112`
- Add exploration test or script to capture SM37 snapshots

- [ ] **Step 1: Collect SM37 snapshots (exploration test)**

Add SM37 snapshot capture tests (similar pattern to SE09 in Task 7). Capture at minimum:

- `sm37_all_statuses_de.yaml` — all 6 checkboxes checked
- `sm37_finished_only_de.yaml` — only "Fertig" checked
- `sm37_active_only_de.yaml` — only "Aktiv" checked

Run against live SAP: `SAP_LANGUAGE=DE pytest unittests/test_sm37_exploration.py -v -s -k "capture"`

- [ ] **Step 2: Add SM37 snapshot-pair parser tests**

Add to `unittests/test_screen_state_parser.py`:

```python
    def test_sm37_all_vs_finished_only(self) -> None:
        """SM37 all-statuses vs finished-only should differ in 5 checkboxes."""
        all_snap = _load_snapshot("sm37_exploration/sm37_all_statuses_de.yaml")
        fin_snap = _load_snapshot("sm37_exploration/sm37_finished_only_de.yaml")

        state_all = parse_selection_screen_state(all_snap)
        state_fin = parse_selection_screen_state(fin_snap)

        # All statuses should be checked
        for label in ["Geplant", "Freigegeben", "Bereit", "Aktiv", "Fertig", "Abgebrochen"]:
            assert state_all.checkboxes[label] is True, f"{label} should be checked in all-statuses"

        # Only Fertig should be checked
        assert state_fin.checkboxes["Fertig"] is True
        unchecked = [k for k, v in state_fin.checkboxes.items() if not v and k != "Fertig"]
        assert len(unchecked) == 5
```

- [ ] **Step 3: Migrate SM37 to `ensure_screen_state()`**

In `src/sapguimcp/tools/sm37_tools.py`:

1. Remove `_set_status_checkboxes` function (lines 50-73).

2. Add import:

```python
from sapguimcp.tools.screen_state_helpers import bilingual_target, ensure_screen_state
```

3. In `_fill_selection_screen` (line ~76), replace the status checkbox block (lines 109-112) with:

```python
    # Build target for status checkboxes — always explicitly set all 6
    effective_statuses = set(statuses) if statuses else set(_ALL_STATUSES)
    target = bilingual_target(
        checkboxes_de={
            "Geplant": "scheduled" in effective_statuses,
            "Freigegeben": "released" in effective_statuses,
            "Bereit": "ready" in effective_statuses,
            "Aktiv": "active" in effective_statuses,
            "Fertig": "finished" in effective_statuses,
            "Abgebrochen": "canceled" in effective_statuses,
        },
        checkboxes_en={
            "Scheduled": "scheduled" in effective_statuses,
            "Released": "released" in effective_statuses,
            "Ready": "ready" in effective_statuses,
            "Active": "active" in effective_statuses,
            "Finished": "finished" in effective_statuses,
            "Canceled": "canceled" in effective_statuses,
        },
    )
    state_result = await ensure_screen_state(backend, target)
    if not state_result.success:
        errors.append(f"Failed to set status checkboxes: {state_result.error}")
    errors.extend(state_result.warnings)
```

This fixes the default-parameter vulnerability: when `statuses` is `None`, we now explicitly check all 6 boxes instead of skipping.

- [ ] **Step 4: Run SM37 integration tests**

Run: `python -m pytest unittests/test_sm37_integration.py -v`
Expected: All PASS

- [ ] **Step 5: Run linting + type check**

Run: `tox -e linting && tox -e type_check`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/tools/sm37_tools.py unittests/
git commit -m "refactor: migrate SM37 to ensure_screen_state(), fix default-param checkbox vulnerability"
```

---

### Task 10: Migrate SE11 radio buttons to backend protocol

**Files:**

- Modify: `src/sapguimcp/tools/se11_tools.py:228-289`

- [ ] **Step 1: Replace `_wait_for_se11_table_screen` radio hack**

Replace lines 228-257 of `se11_tools.py`. The function currently accesses `backend._page` directly for radio buttons. Replace with `backend.set_radio_button()`:

```python
async def _wait_for_se11_table_screen(backend: SapUiBackend, name: str) -> SE11Error | None:
    """Wait for SE11 table screen and select the table radio. Returns error or None."""
    now = datetime.now(UTC)

    # Wait for the screen to load by checking snapshot for radio presence
    for _ in range(20):  # 20 * 500ms = 10s max
        snapshot = await backend.get_snapshot()
        if "Datenbanktabelle" in snapshot or "Database table" in snapshot:
            break
        await asyncio.sleep(0.5)
    else:
        return SE11Error(
            name=name,
            object_type="table",
            error=(
                "SE11 screen did not load. "
                "Could not find 'Database table' / 'Datenbanktabelle' radio button. "
                "This tool currently supports German (DE) and English (EN) SAP languages."
            ),
            retrieved_at=now,
        )

    # Select the table radio button via backend protocol
    for label in [SE11_DATABASE_TABLE_DE, SE11_DATABASE_TABLE_EN]:
        try:
            await backend.set_radio_button(label)
            # Verify the radio click stuck
            verify_snap = await backend.get_snapshot()
            if f'radio "{label}" [checked]' in verify_snap:
                return None
            logger.warning("Radio '%s' click did not stick", label)
        except ValueError:
            continue

    return SE11Error(
        name=name,
        object_type="table",
        error="Could not select 'Database table' / 'Datenbanktabelle' radio button",
        retrieved_at=now,
    )
```

- [ ] **Step 2: Replace `_wait_for_se11_structure_screen` radio hack**

Same pattern for lines 260-289, using `SE11_DATA_TYPE_DE` / `SE11_DATA_TYPE_EN`:

```python
async def _wait_for_se11_structure_screen(backend: SapUiBackend, name: str) -> SE11Error | None:
    """Wait for SE11 structure screen and select the data type radio. Returns error or None."""
    now = datetime.now(UTC)

    for _ in range(20):
        snapshot = await backend.get_snapshot()
        if "Datentyp" in snapshot or "Data type" in snapshot:
            break
        await asyncio.sleep(0.5)
    else:
        return SE11Error(
            name=name,
            object_type="structure",
            error=(
                "SE11 screen did not load. "
                "Could not find 'Data type' / 'Datentyp' radio button. "
                "This tool currently supports German (DE) and English (EN) SAP languages."
            ),
            retrieved_at=now,
        )

    for label in [SE11_DATA_TYPE_DE, SE11_DATA_TYPE_EN]:
        try:
            await backend.set_radio_button(label)
            verify_snap = await backend.get_snapshot()
            if f'radio "{label}" [checked]' in verify_snap:
                return None
            logger.warning("Radio '%s' click did not stick", label)
        except ValueError:
            continue

    return SE11Error(
        name=name,
        object_type="structure",
        error="Could not select 'Data type' / 'Datentyp' radio button",
        retrieved_at=now,
    )
```

- [ ] **Step 3: Remove unused imports**

Remove `from playwright.async_api import TimeoutError as PlaywrightTimeout` (no longer needed in these functions). Remove `bilingual_pattern` import if no longer used elsewhere in the file.

- [ ] **Step 4: Run SE11 integration tests**

Run: `python -m pytest unittests/test_se11_integration.py -v`
Expected: All PASS

- [ ] **Step 5: Run linting + type check**

Run: `tox -e linting && tox -e type_check`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/tools/se11_tools.py
git commit -m "refactor: replace SE11 raw _page radio hacks with backend.set_radio_button()"
```

---

## Chunk 4: Cleanup + Documentation

### Task 11: Update `sap_knowledge.md` with the new pattern

**Files:**

- Modify: `src/sapguimcp/data/sap_knowledge.md`

- [ ] **Step 1: Add selection screen state management section**

Add a section to `sap_knowledge.md` (near the existing "Stateful Selection Screens" section):

```markdown
## Selection Screen State Management

SAP selection screens persist checkbox, radio button, and text field state per user.
Transaction-specific tools use `ensure_screen_state()` to always explicitly set the
desired state before executing. This reads the ARIA snapshot, diffs against the target,
applies only necessary changes, and verifies the result.

For general-purpose exploration of unknown screens:

- Use `sap_get_form_fields` to see all controls including checkbox/radio `checked` state
- Use `sap_set_checkbox(label, checked)` to toggle a checkbox
- Use `sap_set_radio_button(label)` to select a radio button
- These tools are safer than raw `browser_evaluate` for SAP form controls
```

- [ ] **Step 2: Commit**

```bash
git add src/sapguimcp/data/sap_knowledge.md
git commit -m "docs: update sap_knowledge.md with selection screen state management pattern"
```

---

### Task 12: Final verification

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest unittests/test_screen_state_parser.py unittests/test_ensure_screen_state.py -v`
Expected: All PASS

- [ ] **Step 2: Run all integration tests**

Run: `python -m pytest unittests/test_se09_integration.py unittests/test_sm37_integration.py unittests/test_se11_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Full linting + type check + formatting**

Run: `tox -e linting && tox -e type_check && black --check src/ unittests/ && isort --check src/ unittests/`
Expected: All clean

- [ ] **Step 4: Run spell check**

Run: `tox -e spell_check` (if available)
Expected: Clean

---

## Deferred: Future Migration Tasks

The following tools have selection screen controls but are lower risk or lower priority. They should be migrated to `ensure_screen_state()` in follow-up work after the foundation is proven stable:

| Tool     | Controls                                                                            | Current Risk                                      | Notes                                                 |
| -------- | ----------------------------------------------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------- |
| **SM30** | 3 radio buttons ("Keine Einschränkungen", "Bedingungen eingeben", "Variante")       | Low — tool doesn't interact with radios currently | Migrate when SM30 needs radio button management       |
| **SE38** | Radio buttons (Source Code / Variants / Attributes / Text Elements / Documentation) | Low — tool uses display mode only                 | Migrate if/when edit workflow needs radio selection   |
| **SLG1** | Text fields only (Object, Subobject, Date range)                                    | Low — no checkboxes/radios                        | Migrate for consistency, but no statefulness bug risk |

Each migration follows the same pattern: declare target state with `bilingual_target()`, call `ensure_screen_state()`, check `success`.
