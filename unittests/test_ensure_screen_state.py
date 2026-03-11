"""Unit tests for ensure_screen_state() transition logic.

Uses a mock backend to verify that only the necessary set_checkbox /
set_radio_button / fill_field calls are made based on the diff between
current and target state.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from sapwebguimcp.models.screen_state import SelectionScreenState
from sapwebguimcp.tools.screen_state_helpers import ensure_screen_state


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


class TestEnsureScreenStateCombined:
    """Test combined checkbox + radio + field transitions in a single call."""

    @pytest.mark.anyio
    async def test_combined_transition(self) -> None:
        """All three control types should be applied and verified in one call."""
        before = (
            '- checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge\n'
            '- checkbox "Customizing-Aufträge":  Customizing-Aufträge\n'
            '- radio "Datenbanktabelle" [checked]\n'
            '- radio "View"\n'
            '- textbox "Benutzer": KLEINK\n'
        )
        after = (
            '- checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge\n'
            '- checkbox "Customizing-Aufträge" [checked]:  Customizing-Aufträge\n'
            '- radio "Datenbanktabelle"\n'
            '- radio "View" [checked]\n'
            '- textbox "Benutzer": ADMIN\n'
        )
        backend = _mock_backend(before, after)
        target = SelectionScreenState(
            checkboxes={"Workbench-Aufträge": True, "Customizing-Aufträge": True},
            radios={"View": True},
            fields={"Benutzer": "ADMIN"},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert "Customizing-Aufträge" in diff.checkboxes_changed
        assert "View" in diff.radios_changed
        assert "Benutzer" in diff.fields_changed
        backend.set_checkbox.assert_called_once_with("Customizing-Aufträge", True)
        backend.set_radio_button.assert_called_once_with("View")
        backend.fill_field.assert_called_once_with("Benutzer", "ADMIN")
