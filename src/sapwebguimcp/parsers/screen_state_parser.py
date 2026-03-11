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

from sapwebguimcp.models.screen_state import SelectionScreenState

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
_TEXTBOX_RE = re.compile(
    r'-\s+textbox\s+"([^"]+)":\s*(.*)'  # - textbox "LABEL": VALUE
)


def parse_selection_screen_state(snapshot: str) -> SelectionScreenState:  # pylint: disable=too-many-locals,too-many-branches
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
    field_labels: list[str] = []

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
            field_labels.append(label)
            continue

    # Detect ambiguous labels (same label appears 2+ times for same type)
    # and exclude them from the state dicts — the value would be unreliable
    # (last-writer-wins) and ensure_screen_state refuses to act on them anyway.
    ambiguous: list[str] = []
    for label, count in Counter(checkbox_labels).items():
        if count > 1:
            ambiguous.append(label)
            checkboxes.pop(label, None)
    for label, count in Counter(radio_labels).items():
        if count > 1:
            ambiguous.append(label)
            radios.pop(label, None)
    for label, count in Counter(field_labels).items():
        if count > 1:
            ambiguous.append(label)
            fields.pop(label, None)

    return SelectionScreenState(
        checkboxes=checkboxes,
        radios=radios,
        fields=fields,
        ambiguous_labels=ambiguous,
    )
