# Popup Rework: Active Window Model

**Date**: 2026-04-04
**Issues**: #600, #609, #601
**Branch**: `feat/popup-rework`

## Problem

The desktop backend treats all popup windows (`wnd[1]`, `wnd[2]`) as obstacles.
Every interaction tool checks for popups before acting and refuses to work if one
is present. Meanwhile, the field discovery and snapshot tools are hardcoded to
`wnd[0]` and cannot see popup content at all.

This makes it impossible to automate SAP workflows that involve modal dialogs:
package creation (SE21), report properties (SE38), transport prompts, etc.

### Confirmed behavior (integration tests on `feat/popup-rework`)

- SE21: F5 opens "Paket anlegen" at `wnd[1]` with 7 inputs, 1 dropdown,
  1 checkbox. `get_form_fields()` returns 0 fields. `discover_fields()` returns
  0 fields. `get_snapshot()` dumps only `wnd[0]`.
- SE38: F5 opens report properties at `wnd[1]` with 8 text fields, 4 dropdowns,
  2 checkboxes. Same blindness.
- 9 locations in `sap_tools.py` return `"Popup blocking: ..."` failures.

## Design

### Core principle

**A popup is just a window.** `wnd[1]` has a user area, fields, buttons, and a
toolbar — exactly like `wnd[0]`. Tools should operate on whichever window is
topmost. No special-casing.

### Multi-session safety

Window paths (`wnd[0]`, `wnd[1]`) are **relative to the GuiSession COM object**,
not global. Each session has its own independent window hierarchy. When parallel
agents work on different sessions (s1, s2), `session.find_by_id("wnd[1]")` on s1
only sees s1's popup — never s2's. Session isolation is enforced by the
`_current_session_id` context variable set per-agent/per-task.

This means `_active_window_id()` is safe in multi-session scenarios. No risk of
cross-session popup contamination.

### Active window detection

Introduce a helper that returns the topmost open window:

```python
def _active_window_id(session) -> str:
    """Return the element ID of the topmost open window.

    SAP GUI enforces strict modal stacking: wnd[2] cannot exist without wnd[1].
    We scan top-down to find the highest existing window.
    Extends to wnd[3] to cover nested modals (e.g. F4 help inside a transport
    dialog inside a save dialog).
    """
    for i in (3, 2, 1):
        if session.find_by_id(f"wnd[{i}]", raise_error=False) is not None:
            return f"wnd[{i}]"
    return "wnd[0]"
```

All backend methods that currently hardcode `wnd[0]` switch to this.

### Methods to update in `backend/desktop/__init__.py`

| Method | Current target | New target |
|--------|---------------|------------|
| `discover_fields()` | `wnd[0]/usr` | `{active}/usr` |
| `get_form_fields()` | `wnd[0]/usr` | `{active}/usr` |
| `get_snapshot()` | `wnd[0]` | `{active}` |
| `discover_buttons()` | `wnd[0]` | `{active}` |
| `fill_form()` | `wnd[0]/usr` | `{active}/usr` (via element finder) |
| `press_key()` / `send_v_key()` | `wnd[0]` | `{active}` |
| `take_screenshot()` | `wnd[0]` | `{active}` |
| `get_window_title()` | `wnd[0]` | `{active}` |
| `type_text()` | `wnd[0].focused_element` | `{active}.focused_element` |
| `fill_accessible_name()` | `wnd[0]/usr/...` | `{active}/usr/...` |
| `find_code_editor()` | `wnd[0]/usr` | `{active}/usr` |
| `get_screen_info()` (status bar) | `wnd[0]/sbar` | `{active}/sbar` |

### Functions to update in `backend/desktop/_element_finder.py`

This file has 11 hardcoded `wnd[0]` references across 7 functions. All field
lookup, button search, checkbox/radio discovery, and tab navigation goes through
these. They **must** accept a `wnd_id` parameter:

| Function | Current | New |
|----------|---------|-----|
| `_find_by_name_prefix()` | `path_prefix="wnd[0]/usr/"` | `path_prefix=f"{wnd_id}/usr/"` |
| `_find_by_label_text()` | `session.find_by_id("wnd[0]/usr")` | `session.find_by_id(f"{wnd_id}/usr")` |
| `_find_by_readonly_textfield_label()` | `session.find_by_id("wnd[0]/usr")` | same pattern |
| `_find_by_sap_name()` | `session.find_by_id("wnd[0]/usr")` | same pattern |
| `find_button_by_label()` | `session.find_by_id("wnd[0]")` | `session.find_by_id(wnd_id)` |
| `find_checkbox_by_label()` | `session.find_by_id("wnd[0]/usr")` | same pattern |
| `find_radio_by_label()` | `session.find_by_id("wnd[0]/usr")` | same pattern |
| `find_tab_by_label()` | `session.find_by_id("wnd[0]")` | `session.find_by_id(wnd_id)` |
| `_extract_container_path()` | fallback `"wnd[0]/usr/"` | fallback `f"{wnd_id}/usr/"` |

Approach: Each function gains an optional `wnd_id: str = "wnd[0]"` parameter.
The backend methods in `__init__.py` pass `_active_window_id(session)` when
calling these functions.

### Result enrichment

All tool results gain:

```python
active_window: str | None  # e.g. "wnd[1]" — which window was operated on
```

This is the agent's signal that a dialog is open. The agent monitors
`active_window` across calls:

1. `sap_press_key(key="F5")` -> `active_window="wnd[1]"` (dialog opened)
2. `sap_discover_fields()` -> fields from `wnd[1]`
3. `sap_fill_form(...)` -> fills fields in `wnd[1]`
4. `sap_press_key(key="Enter")` -> `active_window="wnd[0]"` (dialog closed)

**Post-action re-detection**: For tools that change screen state (`press_key`,
`fill_form`, `click_button`), `active_window` in the result reflects the state
**after** the action, not before. This means:
- `press_key("F5")` sends VKey to the pre-action active window, waits, then
  re-checks `_active_window_id()` for the result.
- `press_key("Enter")` on `wnd[1]` may close the popup; result shows `wnd[0]`.

### Remove popup blocking from tool layer

Delete all 9 "popup blocking" pre-checks in `sap_tools.py`:

- `sap_transaction`: Keep a check only **before** OkCode entry (navigating away
  with a dialog open is genuinely wrong — SAP ignores OkCode input to `wnd[0]`
  while a modal is active). Return the popup info in the failure so the agent
  knows what to dismiss. Remove post-navigation popup failures.
- `sap_press_key`: Remove pre-check and post-check blocking. Keystroke goes to
  active window. Post-keystroke popup appearance is reported via `active_window`.
- `sap_fill_form`: Remove pre-check. Field search happens in active window.
- `sap_set_field` (text, checkbox, radio): Remove pre-check. Same reasoning.

### `sap_close_popup` becomes "close active window"

Semantically: close whichever window is topmost. If `wnd[1]` is open, close it.
If only `wnd[0]` is open, no-op (or error).

Default dismissal uses `send_v_key(12)` (Escape/Cancel) rather than Enter, since
Escape is safer for dismissing dialogs without side effects. Explicit button
label still available for confirming dialogs.

### `check_popup()` stays as internal utility

The backend method `check_popup()` remains available for internal use (e.g.,
abapgit error detection). It is no longer called as a gate in the tool layer.

### Drop `PopupInfo` from action tool results

Action tools (`sap_press_key`, `sap_fill_form`, `sap_set_field`) no longer attach
`popup: PopupInfo(...)` to their results. The `active_window` field is sufficient.

`sap_get_screen_info` keeps popup info — it is the "what's going on" tool where
richer context (popup type, button labels, message text) is genuinely useful.

## Impact on existing code

### abapgit_tools.py

`_check_for_error_popup_desktop()` uses `get_snapshot()` and looks for `wnd[1]`
in the text. After this change, `get_snapshot()` returns the **active** window's
tree, so the element IDs will naturally contain `wnd[1]` when a popup is active.
However, the string-search approach is fragile. Update to use `check_popup()`
directly (it stays as a backend method) or check `_active_window_id()`.

The "Inaktive Objekte" popup detection also uses snapshot — needs the same
update.

`_handle_popup_error()` calls `check_popup()` via the error detection path and
then `press_key("Enter")` to dismiss. This still works because `press_key` now
targets the active window (which is the popup).

### Transaction-specific edit tools (SE38, SE24, SE37)

These call backend methods directly, not through the tool layer. They already
handle popups explicitly via `check_popup()` and `dismiss_popup()`. Mostly
unaffected, but verify that:
- `press_key` sending to active window doesn't break their internal flow
  (they assume `press_key` targets `wnd[0]` for navigation)
- Transport popup handling still works (they check for wnd[1] explicitly)

### WebGUI backend

The popup-blocking logic lives in the shared tool layer (`sap_tools.py`), so
removing those 9 checks affects both backends.

**Phase 1 (this spec)**: Desktop-only changes. For the tool-layer check removal,
guard with a backend type check: only remove blocking for desktop backend. WebGUI
keeps the current behavior until its own active-window logic is implemented.

**Phase 2 (separate spec)**: Implement WebGUI active-window detection:
- Detect popup overlay in DOM -> read fields from popup instead of main page
- The JS scripts (`check_popup.js`, `discover_fields.js`, `detect_form_fields.js`)
  need popup-aware variants

### Server instructions / sap_knowledge.md

Add guidance:
- "After actions that change screen state, check `active_window` in the result.
  If it changed to `wnd[1]` or higher, a dialog opened."
- "Use `sap_discover_fields` to see what's in the active window, fill fields,
  then confirm or cancel."
- "Use `sap_close_popup` to dismiss dialogs you don't need."

## Testing strategy

### Existing exploration tests (already written)

`test_popup_rework_exploration.py` on `feat/popup-rework` branch:
- `test_02_se21_trigger_popup`: Confirms wnd[1] has fields, tools return 0
- `test_03_se38_create_popup`: Same pattern with SE38
- These become regression tests — after the fix, assertions flip:
  `get_form_fields` should return >0 fields when popup is open.
- Autouse cleanup fixture dismisses popups and returns to Easy Access.

### New integration tests

- **test_fill_popup_fields**: SE21 -> create -> fill popup fields -> verify
  values were set -> close popup
- **test_keyboard_targets_active_window**: Open popup -> press Enter -> verify
  it targets wnd[1] and the popup closes -> active_window returns to wnd[0]
- **test_snapshot_shows_active_window**: Open popup -> snapshot should show
  wnd[1] content -> close popup -> snapshot shows wnd[0]
- **test_active_window_in_result**: Verify all tool results include
  `active_window` field
- **test_abapgit_pull_still_handles_errors**: End-to-end abapgit pull with
  error popup -> verify error detection still works
- **test_abapgit_pull_inactive_objects**: Pull that triggers "Inaktive Objekte"
  popup -> verify it's still dismissed correctly

### Unit tests

- `_active_window_id()` with mock sessions (wnd[0] only, wnd[1] present,
  wnd[2] present, wnd[3] present)
- Element finder functions accept `wnd_id` parameter
- Result models have `active_window` field

## Files to modify

| File | Change |
|------|--------|
| `backend/desktop/__init__.py` | Add `_active_window_id()`, update ~12 methods |
| `backend/desktop/_element_finder.py` | Add `wnd_id` param to 7 functions + `_extract_container_path()` |
| `tools/sap_tools.py` | Remove 9 popup-blocking checks (desktop only), add `active_window` to results |
| `models/base.py` | Add `active_window: str \| None` to `ToolResult` |
| `tools/abapgit_tools.py` | Update `_check_for_error_popup_desktop()` and inactive objects detection |
| `data/sap_knowledge.md` | Add active window guidance |
| `backend/protocol.py` | No change needed (methods stay the same) |
| `unittests/desktop/test_popup_rework_exploration.py` | Flip assertions, add new tests |
| `unittests/desktop/test_popup_rework_unit.py` | New: unit tests for `_active_window_id()` and element finder |

## Out of scope (Phase 2)

- WebGUI popup handling (separate spec, same principle, different implementation)
- Renaming `sap_close_popup` (cosmetic, can do later)
