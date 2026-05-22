"""Unit tests for ensure_screen_state() transition logic.

Uses a mock backend to verify that only the necessary set_checkbox /
set_radio_button / fill_field calls are made based on the diff between
current and target state.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from sapguimcp.models.screen_state import SelectionScreenState
from sapguimcp.tools.screen_state_helpers import bilingual_target, ensure_screen_state


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

    @pytest.mark.anyio
    async def test_radio_desired_false_is_noop(self) -> None:
        """radios={label: False} should be a no-op — you cannot deselect a radio."""
        backend = _mock_backend(_SE11_TABLE_SELECTED, _SE11_TABLE_SELECTED)
        target = SelectionScreenState(
            radios={"Datenbanktabelle": False, "View": False},
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
        ambiguous_snapshot = '- checkbox "Status" [checked]:  Status\n' '- checkbox "Status":  Status\n'
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


class TestEnsureScreenStateResilience:
    """Test that exceptions in one control don't block others."""

    @pytest.mark.anyio
    async def test_checkbox_exception_does_not_block_radio(self) -> None:
        """If set_checkbox raises, radio should still be applied."""
        before = (
            '- checkbox "Workbench-Aufträge":  Workbench-Aufträge\n'
            '- radio "Datenbanktabelle" [checked]\n'
            '- radio "View"\n'
        )
        after = (
            '- checkbox "Workbench-Aufträge":  Workbench-Aufträge\n'
            '- radio "Datenbanktabelle"\n'
            '- radio "View" [checked]\n'
        )
        backend = _mock_backend(before, after)
        backend.set_checkbox = AsyncMock(side_effect=ValueError("element detached"))

        target = SelectionScreenState(
            checkboxes={"Workbench-Aufträge": True},
            radios={"View": True},
        )

        diff = await ensure_screen_state(backend, target)

        # Checkbox failed but radio succeeded
        assert any("Workbench-Aufträge" in w for w in diff.warnings)
        backend.set_radio_button.assert_called_once_with("View")
        assert "View" in diff.radios_changed

    @pytest.mark.anyio
    async def test_missing_field_label_produces_warning(self) -> None:
        """Fields not found on screen should produce warnings, not backend calls."""
        backend = _mock_backend(_SE09_WORKBENCH_ONLY, _SE09_WORKBENCH_ONLY)
        target = SelectionScreenState(
            fields={"NonExistentField": "value"},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert any("NonExistentField" in w for w in diff.warnings)
        backend.fill_field.assert_not_called()


class TestEnsureScreenStateTransitions:
    """Test realistic state A → state B transitions with mock backend."""

    @pytest.mark.anyio
    async def test_uncheck_all_checkboxes(self) -> None:
        """Transition from multiple checked to all unchecked."""
        before = (
            '- checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge\n'
            '- checkbox "Customizing-Aufträge" [checked]:  Customizing-Aufträge\n'
            '- checkbox "Änderbar" [checked]:  Änderbar\n'
            '- checkbox "Freigegeben" [checked]:  Freigegeben\n'
        )
        after = (
            '- checkbox "Workbench-Aufträge":  Workbench-Aufträge\n'
            '- checkbox "Customizing-Aufträge":  Customizing-Aufträge\n'
            '- checkbox "Änderbar":  Änderbar\n'
            '- checkbox "Freigegeben":  Freigegeben\n'
        )
        backend = _mock_backend(before, after)
        target = SelectionScreenState(
            checkboxes={
                "Workbench-Aufträge": False,
                "Customizing-Aufträge": False,
                "Änderbar": False,
                "Freigegeben": False,
            },
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert len(diff.checkboxes_changed) == 4
        assert backend.set_checkbox.call_count == 4
        # Each checkbox should be called with False
        for label in target.checkboxes:
            backend.set_checkbox.assert_any_call(label, False)

    @pytest.mark.anyio
    async def test_partial_checkbox_toggle(self) -> None:
        """Only checkboxes that differ from target should be changed."""
        before = (
            '- checkbox "Geplant" [checked]:  Geplant\n'
            '- checkbox "Freigegeben":  Freigegeben\n'
            '- checkbox "Bereit":  Bereit\n'
            '- checkbox "Aktiv":  Aktiv\n'
            '- checkbox "Fertig" [checked]:  Fertig\n'
            '- checkbox "Abgebrochen":  Abgebrochen\n'
        )
        # Target: check all statuses — Geplant and Fertig already match
        after = (
            '- checkbox "Geplant" [checked]:  Geplant\n'
            '- checkbox "Freigegeben" [checked]:  Freigegeben\n'
            '- checkbox "Bereit" [checked]:  Bereit\n'
            '- checkbox "Aktiv" [checked]:  Aktiv\n'
            '- checkbox "Fertig" [checked]:  Fertig\n'
            '- checkbox "Abgebrochen" [checked]:  Abgebrochen\n'
        )
        backend = _mock_backend(before, after)
        target = SelectionScreenState(
            checkboxes={
                "Geplant": True,
                "Freigegeben": True,
                "Bereit": True,
                "Aktiv": True,
                "Fertig": True,
                "Abgebrochen": True,
            },
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        # Only 4 changed (Freigegeben, Bereit, Aktiv, Abgebrochen)
        assert len(diff.checkboxes_changed) == 4
        assert "Geplant" not in diff.checkboxes_changed
        assert "Fertig" not in diff.checkboxes_changed
        assert backend.set_checkbox.call_count == 4

    @pytest.mark.anyio
    async def test_radio_switch_with_field_change(self) -> None:
        """Switch radio and change text field in one transition."""
        before = (
            '- radio "Datenbanktabelle" [checked]\n'
            '- radio "View"\n'
            '- radio "Datentyp"\n'
            '- textbox "Datenbankrelation": T000\n'
        )
        after = (
            '- radio "Datenbanktabelle"\n'
            '- radio "View" [checked]\n'
            '- radio "Datentyp"\n'
            '- textbox "Datenbankrelation": ZSOMEVIEW\n'
        )
        backend = _mock_backend(before, after)
        target = SelectionScreenState(
            radios={"View": True},
            fields={"Datenbankrelation": "ZSOMEVIEW"},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert "View" in diff.radios_changed
        assert "Datenbankrelation" in diff.fields_changed
        backend.set_radio_button.assert_called_once_with("View")
        backend.fill_field.assert_called_once_with("Datenbankrelation", "ZSOMEVIEW")

    @pytest.mark.anyio
    async def test_field_already_matching_not_touched(self) -> None:
        """If field already has the target value, fill_field should not be called."""
        backend = _mock_backend(_SE11_TABLE_SELECTED, _SE11_TABLE_SELECTED)
        target = SelectionScreenState(
            fields={"Datenbankrelation": "T000"},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        assert diff.fields_changed == {}
        backend.fill_field.assert_not_called()

    @pytest.mark.anyio
    async def test_sm37_full_selection_screen_transition(self) -> None:
        """Simulate SM37 selection screen: set job name, user, and toggle statuses."""
        before = (
            '- checkbox "Geplant":  Geplant\n'
            '- checkbox "Freigegeben":  Freigegeben\n'
            '- checkbox "Bereit":  Bereit\n'
            '- checkbox "Aktiv":  Aktiv\n'
            '- checkbox "Fertig" [checked]:  Fertig\n'
            '- checkbox "Abgebrochen":  Abgebrochen\n'
            '- textbox "Jobname": *\n'
            '- textbox "Benutzername": KLEINK\n'
        )
        after = (
            '- checkbox "Geplant":  Geplant\n'
            '- checkbox "Freigegeben":  Freigegeben\n'
            '- checkbox "Bereit":  Bereit\n'
            '- checkbox "Aktiv":  Aktiv\n'
            '- checkbox "Fertig" [checked]:  Fertig\n'
            '- checkbox "Abgebrochen" [checked]:  Abgebrochen\n'
            '- textbox "Jobname": ZBILLING*\n'
            '- textbox "Benutzername": *\n'
        )
        backend = _mock_backend(before, after)
        target = SelectionScreenState(
            checkboxes={"Fertig": True, "Abgebrochen": True},
            fields={"Jobname": "ZBILLING*", "Benutzername": "*"},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        # Only Abgebrochen changed (Fertig was already True)
        assert len(diff.checkboxes_changed) == 1
        assert "Abgebrochen" in diff.checkboxes_changed
        # Both fields changed
        assert "Jobname" in diff.fields_changed
        assert "Benutzername" in diff.fields_changed

    @pytest.mark.anyio
    async def test_bilingual_target_de_screen_ignores_en_labels(self) -> None:
        """On a DE screen, EN labels produce warnings but don't fail."""
        de_screen = (
            '- checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge\n'
            '- checkbox "Customizing-Aufträge":  Customizing-Aufträge\n'
        )
        target = bilingual_target(
            checkboxes_de={"Workbench-Aufträge": True, "Customizing-Aufträge": True},
            checkboxes_en={"Workbench Requests": True, "Customizing Requests": True},
        )
        after = (
            '- checkbox "Workbench-Aufträge" [checked]:  Workbench-Aufträge\n'
            '- checkbox "Customizing-Aufträge" [checked]:  Customizing-Aufträge\n'
        )
        backend = _mock_backend(de_screen, after)

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        # EN labels not found → warnings
        assert any("Workbench Requests" in w for w in diff.warnings)
        assert any("Customizing Requests" in w for w in diff.warnings)
        # DE label changed
        assert "Customizing-Aufträge" in diff.checkboxes_changed
        # Only 1 backend call (Customizing-Aufträge was False → True)
        backend.set_checkbox.assert_called_once_with("Customizing-Aufträge", True)

    @pytest.mark.anyio
    async def test_bilingual_target_en_screen_ignores_de_labels(self) -> None:
        """On an EN screen, DE labels produce warnings but don't fail."""
        en_screen = (
            '- checkbox "Workbench Requests" [checked]:  Workbench Requests\n'
            '- checkbox "Customizing Requests":  Customizing Requests\n'
        )
        target = bilingual_target(
            checkboxes_de={"Workbench-Aufträge": True, "Customizing-Aufträge": True},
            checkboxes_en={"Workbench Requests": True, "Customizing Requests": True},
        )
        after = (
            '- checkbox "Workbench Requests" [checked]:  Workbench Requests\n'
            '- checkbox "Customizing Requests" [checked]:  Customizing Requests\n'
        )
        backend = _mock_backend(en_screen, after)

        diff = await ensure_screen_state(backend, target)

        assert diff.success is True
        # DE labels not found → warnings
        assert any("Workbench-Aufträge" in w for w in diff.warnings)
        assert any("Customizing-Aufträge" in w for w in diff.warnings)
        # EN label changed
        assert "Customizing Requests" in diff.checkboxes_changed
        # Only 1 backend call (Customizing Requests was False → True)
        backend.set_checkbox.assert_called_once_with("Customizing Requests", True)

    @pytest.mark.anyio
    async def test_radio_verification_failure(self) -> None:
        """If radio didn't stick after apply, return failure with mismatch."""
        # Backend says it applied, but verification snapshot still shows old state
        backend = _mock_backend(_SE11_TABLE_SELECTED, _SE11_TABLE_SELECTED)
        target = SelectionScreenState(
            radios={"View": True},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is False
        assert any("View" in m for m in diff.mismatches)

    @pytest.mark.anyio
    async def test_field_verification_failure(self) -> None:
        """If field value didn't stick, return failure with mismatch."""
        backend = _mock_backend(_SE11_TABLE_SELECTED, _SE11_TABLE_SELECTED)
        target = SelectionScreenState(
            fields={"Datenbankrelation": "MARA"},
        )

        diff = await ensure_screen_state(backend, target)

        assert diff.success is False
        assert any("Datenbankrelation" in m for m in diff.mismatches)


class TestBilingualTarget:
    """Test bilingual_target() merging logic."""

    def test_merges_de_en_checkboxes(self) -> None:
        target = bilingual_target(
            checkboxes_de={"Werkbank": True},
            checkboxes_en={"Workbench": True},
        )
        assert target.checkboxes == {"Werkbank": True, "Workbench": True}

    def test_merges_de_en_radios(self) -> None:
        target = bilingual_target(
            radios_de={"Datenbanktabelle": True},
            radios_en={"Database table": True},
        )
        assert target.radios == {"Datenbanktabelle": True, "Database table": True}

    def test_merges_de_en_fields(self) -> None:
        target = bilingual_target(
            fields_de={"Benutzer": "KLEINK"},
            fields_en={"User": "KLEINK"},
        )
        assert target.fields == {"Benutzer": "KLEINK", "User": "KLEINK"}

    def test_none_inputs_produce_empty(self) -> None:
        target = bilingual_target()
        assert target.checkboxes == {}
        assert target.radios == {}
        assert target.fields == {}

    def test_partial_inputs(self) -> None:
        target = bilingual_target(checkboxes_de={"Foo": True})
        assert target.checkboxes == {"Foo": True}
        assert target.radios == {}
        assert target.fields == {}
