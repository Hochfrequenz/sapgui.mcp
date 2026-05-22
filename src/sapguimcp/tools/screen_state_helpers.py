"""Helpers for reading and transitioning SAP selection screen state.

The core function ``ensure_screen_state()`` reads the current screen
state from an ARIA snapshot, diffs it against a target state, applies
only the necessary changes, and verifies the screen reached the target.

``bilingual_target()`` is a convenience to merge DE/EN label variants
into a single ``SelectionScreenState``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sapguimcp.backend.webgui.parsers.screen_state_parser import parse_selection_screen_state
from sapguimcp.models.screen_state import (
    ScreenStateDiff,
    SelectionScreenState,
    StateChange,
)

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend

logger = logging.getLogger(__name__)

__all__ = ["bilingual_target", "ensure_screen_state"]


async def _apply_changes(
    backend: WebGuiBackend | DesktopBackend,
    current: SelectionScreenState,
    target: SelectionScreenState,
    diff: ScreenStateDiff,
) -> None:
    """Apply checkbox, radio, and field changes; mutates *diff* in-place."""
    for label, desired in target.checkboxes.items():
        cb_actual = current.checkboxes.get(label)
        if cb_actual is None:
            diff.warnings.append(f"Checkbox '{label}' not found on screen")
            continue
        if cb_actual != desired:
            try:
                await backend.set_checkbox(label, desired)
                await backend.wait_for_ready()
                diff.checkboxes_changed[label] = StateChange(
                    was=str(cb_actual),
                    now=str(desired),
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                diff.warnings.append(f"Failed to set checkbox '{label}': {exc}")

    for label, desired in target.radios.items():
        radio_actual = current.radios.get(label)
        if radio_actual is None:
            diff.warnings.append(f"Radio '{label}' not found on screen")
            continue
        if radio_actual != desired and desired is True:
            try:
                await backend.set_radio_button(label)
                await backend.wait_for_ready()
                diff.radios_changed[label] = StateChange(
                    was=str(radio_actual),
                    now=str(desired),
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                diff.warnings.append(f"Failed to set radio '{label}': {exc}")

    for label, desired_val in target.fields.items():
        field_actual = current.fields.get(label)
        if field_actual is None:
            diff.warnings.append(f"Field '{label}' not found on screen")
            continue
        if field_actual != desired_val:
            try:
                await backend.fill_field(label, desired_val)
                await backend.wait_for_ready()
                diff.fields_changed[label] = StateChange(
                    was=field_actual or "",
                    now=desired_val,
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                diff.warnings.append(f"Failed to fill field '{label}': {exc}")


def _verify_state(
    actual_after: SelectionScreenState,
    target: SelectionScreenState,
    diff: ScreenStateDiff,
) -> None:
    """Compare actual screen state against target; appends to *diff.mismatches*."""
    for label, desired in target.checkboxes.items():
        cb_val = actual_after.checkboxes.get(label)
        if cb_val is not None and cb_val != desired:
            diff.mismatches.append(f"Checkbox '{label}': expected {desired}, still {cb_val}")

    for label, desired in target.radios.items():
        if not desired:
            continue  # only verify selected radios
        radio_val = actual_after.radios.get(label)
        if radio_val is not None and radio_val != desired:
            diff.mismatches.append(f"Radio '{label}': expected selected, still unselected")

    for label, desired_val in target.fields.items():
        field_val = actual_after.fields.get(label)
        if field_val is not None and field_val != desired_val:
            diff.mismatches.append(f"Field '{label}': expected '{desired_val}', still '{field_val}'")


async def ensure_screen_state(
    backend: WebGuiBackend | DesktopBackend,
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

    # Refuse ambiguous labels
    ambiguous_targets = set(target.checkboxes) | set(target.radios) | set(target.fields)
    ambiguous_hits = ambiguous_targets & set(current.ambiguous_labels)
    if ambiguous_hits:
        return ScreenStateDiff.failure(
            error=f"Ambiguous labels on screen — cannot safely target: " f"{', '.join(sorted(ambiguous_hits))}",
        )

    diff = ScreenStateDiff()
    await _apply_changes(backend, current, target, diff)

    # Verification: re-read snapshot and compare
    verify_snapshot = await backend.get_snapshot()
    actual_after = parse_selection_screen_state(verify_snapshot)
    _verify_state(actual_after, target, diff)

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


def bilingual_target(  # pylint: disable=too-many-arguments
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
