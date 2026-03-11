"""Unit tests for selection screen state parsing and transition models."""

from pathlib import Path

import pytest

from sapwebguimcp.models.screen_state import (
    ScreenStateDiff,
    SelectionScreenState,
    StateChange,
)
from sapwebguimcp.parsers.screen_state_parser import parse_selection_screen_state

TESTDATA_DIR = Path(__file__).parent / "testdata"


def _load_snapshot(relative_path: str) -> str:
    """Load a YAML snapshot from testdata/."""
    filepath = TESTDATA_DIR / relative_path
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available")
    return filepath.read_text(encoding="utf-8")


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
