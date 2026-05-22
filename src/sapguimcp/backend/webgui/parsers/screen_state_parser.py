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
    - textbox "Benutzer": USER01
    - menuitemradio "System S4U (100)" [checked]:   ← ignored (system info)
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sapguimcp.models.screen_state import SelectionScreenState

__all__ = ["parse_selection_screen_state"]

# Matches: checkbox "LABEL" optionally [checked], optionally [disabled]
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
_TEXTBOX_RE = re.compile(r'-\s+textbox\s+"([^"]+)":\s*(.*)')  # - textbox "LABEL": VALUE


@dataclass
class _ParseAccumulator:
    """Mutable accumulator for parsed ARIA snapshot controls."""

    checkboxes: dict[str, bool] = field(default_factory=dict)
    radios: dict[str, bool] = field(default_factory=dict)
    fields: dict[str, str] = field(default_factory=dict)
    checkbox_labels: list[str] = field(default_factory=list)
    radio_labels: list[str] = field(default_factory=list)
    field_labels: list[str] = field(default_factory=list)


def _parse_line(line: str, acc: _ParseAccumulator) -> None:
    """Parse a single ARIA snapshot line into the accumulator."""
    cb_match = _CHECKBOX_RE.search(line)
    if cb_match:
        label, flags = cb_match.group(1), cb_match.group(2)
        if "[disabled]" not in flags:
            acc.checkboxes[label] = "[checked]" in flags
            acc.checkbox_labels.append(label)
        return

    if "menuitemradio" in line:
        return
    radio_match = _RADIO_RE.search(line)
    if radio_match:
        label, flags = radio_match.group(1), radio_match.group(2)
        if "[disabled]" not in flags:
            acc.radios[label] = "[checked]" in flags
            acc.radio_labels.append(label)
        return

    tb_match = _TEXTBOX_RE.search(line)
    if tb_match:
        label, value = tb_match.group(1), tb_match.group(2).strip()
        # Strip YAML-artifact quotes: Playwright's ARIA snapshot serializer
        # quotes values containing YAML special characters (e.g. * → "*").
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        if "[disabled]" not in line and "[readonly]" not in line:
            acc.fields[label] = value
            acc.field_labels.append(label)


def _remove_ambiguous(
    labels: list[str],
    state_dict: dict[str, Any],
    ambiguous: list[str],
) -> None:
    """Detect duplicate labels, remove them from *state_dict*, and append to *ambiguous*."""
    for label, count in Counter(labels).items():
        if count > 1:
            ambiguous.append(label)
            state_dict.pop(label, None)


def parse_selection_screen_state(
    snapshot: str,
) -> SelectionScreenState:
    """Parse checkbox, radio, and text field state from an ARIA snapshot.

    Args:
        snapshot: ARIA accessibility snapshot string (YAML-like format).

    Returns:
        SelectionScreenState with all detected controls and their current state.
        Disabled controls are excluded (they cannot be changed).
        Ambiguous labels (same label, same control type, multiple occurrences)
        are listed in ``ambiguous_labels``.
    """
    acc = _ParseAccumulator()

    for line in snapshot.splitlines():
        _parse_line(line, acc)

    ambiguous: list[str] = []
    _remove_ambiguous(acc.checkbox_labels, acc.checkboxes, ambiguous)
    _remove_ambiguous(acc.radio_labels, acc.radios, ambiguous)
    _remove_ambiguous(acc.field_labels, acc.fields, ambiguous)

    return SelectionScreenState(
        checkboxes=acc.checkboxes,
        radios=acc.radios,
        fields=acc.fields,
        ambiguous_labels=ambiguous,
    )
