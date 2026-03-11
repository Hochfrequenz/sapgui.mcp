# Stateless Selection Screen Transitions — Design Document

**Date:** 2026-03-11
**Status:** Draft

## Problem

SAP selection screens are **stateful per user** — checkboxes, radio buttons, and text fields persist whatever the user last set, across sessions and logins. This causes flaky tool behavior: tools that assume default state (e.g., "Workbench is checked by default in SE09") silently produce wrong results when the SAP-side state doesn't match.

The SE09 checkbox fix (v0.5.2) patched this for one tool. But the same problem exists across all transaction tools with selection screens: SM37 (6 status checkboxes — vulnerable when called with default parameters, since it skips checkbox setup entirely), SE11 (7 radio buttons — currently uses raw `_page` access bypassing the backend protocol), SM30 (3 radio buttons on its selection screen, not currently managed by the tool), SE38 (radio buttons), and potentially any future tool.

Additionally, the LLM-facing `sap_get_form_fields` tool does not return checkbox/radio checked state — the AI is blind to this dimension when exploring unknown screens.

## Goals

- **Generic mechanism** to read current selection screen state and transition to a target state, reusable across all transaction tools
- **No per-tool reinvention** — each tool declares its target state; the mechanism handles the rest
- **LLM visibility** — `sap_get_form_fields` returns checkbox `checked` and radio `selected` state
- **Backend protocol gap closed** — add `set_radio_button()` to the backend protocol
- **Trivially testable** — state parsing is pure string processing on ARIA snapshots; transition logic is unit-testable with mocked backends

## Non-Goals

- Changing MCP tool signatures visible to the AI (internal refactoring only)
- Handling non-selection-screen statefulness (e.g., ALV grid scroll positions, tree expansion state)
- Changing how `enter_transaction()` works — the state transition is a separate step after navigation

## Key Insight: ARIA Snapshots Already Contain State

The Playwright ARIA snapshot format already encodes checkbox and radio state:

```yaml
- checkbox "Customizing-Aufträge" [checked]:  Customizing-Aufträge
- checkbox "Workbench-Aufträge":  Workbench-Aufträge
- radio "Datenbanktabelle" [checked]
- radio "View"
- textbox "Benutzer": KLEINK
```

`[checked]` = checked/selected, absence = unchecked/unselected, `textbox "Label": VALUE` = current text value.

No additional JavaScript or DOM queries needed for reading state — just parse the snapshot.

## Architecture

### Component 1: `SelectionScreenState` Model

```python
from pydantic import BaseModel

class SelectionScreenState(BaseModel):
    """Parsed state of a SAP selection screen."""
    checkboxes: dict[str, bool] = {}   # label -> checked
    radios: dict[str, bool] = {}       # label -> selected
    fields: dict[str, str] = {}        # label -> value
```

### Component 2: `parse_selection_screen_state(snapshot: str) -> SelectionScreenState`

Pure function. Parses the ARIA snapshot string using regex to extract:
- `checkbox "LABEL" [checked]` → `{"LABEL": True}`
- `checkbox "LABEL"` (no `[checked]`) → `{"LABEL": False}`
- `radio "LABEL" [checked]` → `{"LABEL": True}`
- `radio "LABEL"` → `{"LABEL": False}`
- `textbox "LABEL": VALUE` → `{"LABEL": "VALUE"}`

Filters out `[disabled]` elements (they can't be changed anyway).
Ignores `menuitemradio` (system info dropdowns, not selection screen controls).

**Format notes:**
- Checkboxes may have trailing text after a colon: `checkbox "Label" [checked]:  Label` — the parser only needs the part up to `[checked]`
- Radio buttons use simpler format: `radio "Label" [checked]` (no trailing colon/text)
- The parser must handle both shapes

**Unit-testable** against every existing YAML snapshot in `unittests/testdata/`.

### Component 3: `ensure_screen_state(backend, target: SelectionScreenState) -> ScreenStateDiff`

The core transition function:

```python
async def ensure_screen_state(
    backend: SapUiBackend,
    target: SelectionScreenState,
) -> ScreenStateDiff:
    """Read current screen state from ARIA snapshot, diff against target, apply changes."""
    snapshot = await backend.get_snapshot()
    current = parse_selection_screen_state(snapshot)

    diff = ScreenStateDiff()

    # Transition checkboxes
    for label, desired in target.checkboxes.items():
        actual = current.checkboxes.get(label)
        if actual is None:
            diff.warnings.append(f"Checkbox '{label}' not found on screen")
            continue
        if actual != desired:
            await backend.set_checkbox(label, desired)
            await backend.wait_for_ready()
            diff.checkboxes_changed[label] = (actual, desired)

    # Transition radio buttons
    for label, desired in target.radios.items():
        actual = current.radios.get(label)
        if actual is None:
            diff.warnings.append(f"Radio '{label}' not found on screen")
            continue
        if actual != desired and desired is True:
            # Radio buttons: can only select, not deselect (selecting another deselects)
            await backend.set_radio_button(label)
            await backend.wait_for_ready()
            diff.radios_changed[label] = (actual, desired)

    # Transition text fields
    for label, desired in target.fields.items():
        actual = current.fields.get(label)
        if actual != desired:
            await backend.fill_field(label, desired)
            await backend.wait_for_ready()  # SAP text fields can trigger field-exit events
            diff.fields_changed[label] = (actual or "", desired)

    return diff
```

Key behaviors:
- **Only applies diffs** — if the screen already matches target, zero SAP interactions
- **`wait_for_ready()` after each checkbox/radio change** — SAP may trigger partial page reloads
- **Radio buttons only need `select`** — selecting one auto-deselects others in the group
- **Warnings for missing labels** — handles DE/EN differences gracefully; callers can provide both labels
- **Returns diff** for logging/debugging

### Component 4: `ScreenStateDiff` Model

```python
class StateChange(BaseModel):
    """A single state transition."""
    was: str
    now: str

class ScreenStateDiff(BaseModel):
    """What changed during ensure_screen_state."""
    checkboxes_changed: dict[str, StateChange] = {}  # label -> change
    radios_changed: dict[str, StateChange] = {}
    fields_changed: dict[str, StateChange] = {}
    warnings: list[str] = []
```

### Component 5: `set_radio_button()` Backend Protocol Method

New method on `SapUiPrimitives`:

```python
async def set_radio_button(self, label: str) -> None:
    """Select a radio button by its ARIA label. Raises ValueError if not found."""
```

Implementation in `WebGuiBackend`:
```python
async def set_radio_button(self, label: str) -> None:
    radio = self._page.get_by_role("radio", name=label, exact=True)
    if not await radio.count():
        raise ValueError(f"Radio button '{label}' not found")
    await radio.check()
```

This replaces the raw `page.get_by_role("radio")` hacks currently in SE11 (`_page` access with `# type: ignore[attr-defined]` and `# pylint: disable=protected-access`) and SPRO tools, eliminating protocol violations.

### Component 6: Enriched `FormField` for LLM Visibility

Add `checked` field to the `FormField` model:

```python
class FormField(BaseModel):
    id: str
    label: str
    field_type: SapFieldType
    current_value: str | None = None
    checked: bool | None = Field(default=None, description="True/False for checkbox/radio, None for text/dropdown")
    readonly: bool = False
    options: list[str] | None = None
```

Fix `detect_form_fields.js` to return `el.checked` for checkboxes and radio buttons:

```javascript
const field = {
    id: el.id || '',
    label: getLabel(el),
    field_type: fieldType,
    current_value: el.value || null,
    checked: (fieldType === 'checkbox' || fieldType === 'radio') ? el.checked : null,  // NEW
    readonly: isReadonly,
    options: null,
};
```

### Component 7: DE/EN Label Handling

Transaction tools need to work in both languages. The target state can use a helper for bilingual labels:

```python
def bilingual_target(
    checkboxes_de: dict[str, bool] | None = None,
    checkboxes_en: dict[str, bool] | None = None,
    radios_de: dict[str, bool] | None = None,
    radios_en: dict[str, bool] | None = None,
    fields_de: dict[str, str] | None = None,
    fields_en: dict[str, str] | None = None,
) -> SelectionScreenState:
    """Merge DE and EN label variants into one target state.

    ensure_screen_state matches by label — if the screen is German,
    the German labels will match; English labels won't be found (and
    generate ignorable warnings). Vice versa for English screens.
    """
    return SelectionScreenState(
        checkboxes={**(checkboxes_de or {}), **(checkboxes_en or {})},
        radios={**(radios_de or {}), **(radios_en or {})},
        fields={**(fields_de or {}), **(fields_en or {})},
    )
```

**Warning suppression:** `ensure_screen_state` only warns for labels that have NO match at all. Labels from the non-active language that have a matching counterpart (same target value in the other language dict) are silently skipped. This avoids noisy logs in production while still catching genuine missing-label issues.

**Note:** SM37 currently uses a language-gated strategy (`settings.sap_language`) to pick DE or EN labels. The bilingual approach replaces this — it's simpler and works without config access. But if the configured language is available, `bilingual_target` can optionally accept a `language` parameter to filter to only the matching labels, avoiding any unnecessary label lookups.

## How Transaction Tools Change

### Before (SE09, ad-hoc):
```python
async def _set_request_type_filter(backend, request_type):
    if request_type == "all":
        await _set_checkbox_state(backend, "Workbench", True)
        await _set_checkbox_state(backend, "Customizing", True)
    elif request_type == "workbench":
        await _set_checkbox_state(backend, "Workbench", True)
        await _set_checkbox_state(backend, "Customizing", False)
    # ... custom checkbox logic, custom wait_for_ready calls
```

### After (generic):
```python
async def _lookup_transports(backend, username, request_type, status, ...):
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
        fields_de={"Benutzer": username} if username else {},
        fields_en={"User": username} if username else {},
    )
    await ensure_screen_state(backend, target)
    # ... click Display, parse results
```

### SM37 (currently vulnerable):
```python
target = bilingual_target(
    checkboxes_de={
        "Geplant": scheduled, "Freigegeben": released,
        "Bereit": ready, "Aktiv": active,
        "Fertig": finished, "Abgebrochen": cancelled,
    },
    checkboxes_en={
        "Scheduled": scheduled, "Released": released,
        "Ready": ready, "Active": active,
        "Finished": finished, "Cancelled": cancelled,
    },
    fields_de={"Jobname": job_name, "Benutzername": username},
    fields_en={"Job name": job_name, "Username": username},
)
await ensure_screen_state(backend, target)
```

### SE11 (radio buttons):
```python
target = bilingual_target(
    radios_de={"Datenbanktabelle": object_type == "table", "Datentyp": object_type == "structure"},
    radios_en={"Database table": object_type == "table", "Data type": object_type == "structure"},
    fields_de={"Datenbankrelation": object_name},
    fields_en={"Table name": object_name},
)
await ensure_screen_state(backend, target)
```

## File Layout

| File | Purpose |
|------|---------|
| `src/sapwebguimcp/models/screen_state.py` | `SelectionScreenState`, `ScreenStateDiff` models |
| `src/sapwebguimcp/parsers/screen_state_parser.py` | `parse_selection_screen_state()` — pure ARIA snapshot parsing |
| `src/sapwebguimcp/tools/screen_state_helpers.py` | `ensure_screen_state()`, `bilingual_target()` — transition logic |
| `src/sapwebguimcp/backend/protocol.py` | Add `set_radio_button()` to `SapUiPrimitives` |
| `src/sapwebguimcp/backend/webgui/backend.py` | Implement `set_radio_button()` |
| `src/sapwebguimcp/models/sap_results.py` | Add `checked` field to `FormField` |
| `src/sapwebguimcp/js/detect_form_fields.js` | Return `el.checked` for checkbox/radio |
| `unittests/test_screen_state_parser.py` | Parser unit tests against existing YAML snapshots |
| `unittests/test_ensure_screen_state.py` | Transition logic unit tests with mocked backend |

## Migration Plan

### Phase 1: Foundation (no tool changes)
1. Add `SelectionScreenState` and `ScreenStateDiff` models
2. Implement `parse_selection_screen_state()` with unit tests against existing snapshots
3. Add `set_radio_button()` to backend protocol + WebGUI implementation
4. Implement `ensure_screen_state()` with unit tests (mocked backend)
5. Add `checked` to `FormField` + fix `detect_form_fields.js`

### Phase 2: Migrate transaction tools (one at a time)
6. SE09 — replace ad-hoc checkbox logic with `ensure_screen_state()`
7. SM37 — fix the existing vulnerability + migrate
8. SE11 — replace raw `page.get_by_role("radio")` with `ensure_screen_state()`
9. SM30 — add radio button state management
10. SE38 — add radio button state management (if applicable to its tools)
11. SLG1 — migrate text field filling (lower risk, but consistency)

### Phase 3: Cleanup
12. Remove SE09's `_set_checkbox_state`, `_try_set_checkbox`, `_set_request_type_filter`, `_set_status_filter`
13. Remove SE11's raw `page.get_by_role("radio")` usage
14. Update `sap_knowledge.md` with the new pattern

## Testing Strategy

- **Parser unit tests**: Test `parse_selection_screen_state()` against every existing YAML snapshot in `unittests/testdata/` — SE09, SM37, SE11, SM30 initial screens all have checkboxes/radios
- **Transition unit tests**: Mock backend, verify `ensure_screen_state()` calls only the necessary `set_checkbox`/`set_radio_button`/`fill_field` methods based on diff
- **Integration tests**: For each migrated tool, run the same transition tests as SE09 (e.g., "customizing then workbench", "released then modifiable") to verify no state bleeding

## Known Limitations

- **Single snapshot read**: `ensure_screen_state` reads the snapshot once and applies diffs. If a checkbox change triggers a SAP page reload that adds/removes other controls, the pre-read state may become stale. A post-change verification read could catch mismatches — worth adding if we encounter this in practice.
- **SE09 uses substring label matching**: The current SE09 code matches "Workbench" inside "Workbench-Aufträge". The migration to exact ARIA labels is more robust but is a behavioral change that needs testing.

## Risks

- **ARIA snapshot format changes**: If Playwright changes the `[checked]` format, the parser breaks. Mitigated by pinning Playwright version and having comprehensive parser tests.
- **DE/EN label mismatches**: The bilingual approach generates harmless warnings for the non-matching language. If this is noisy, we can add a "paired labels" concept to suppress expected mismatches.
- **Radio button groups**: `set_radio_button()` only selects; it relies on SAP's native radio group behavior to deselect others. If SAP has independent radio buttons (unlikely for selection screens), this would need adjustment.
