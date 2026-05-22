# Design: ABAP Breakpoint Management Tools

**Date:** 2026-04-30
**Repo:** https://github.com/Hochfrequenz/sapgui.mcp
**Type:** Feature Design
**Backend:** Desktop only (SAP GUI COM)

---

## Context & Motivation

An AI agent investigating runtime behavior often needs to verify whether a specific method,
program, or function module is executed during a given action (e.g. a device change). The
standard human workflow is: set an external breakpoint on the relevant code, trigger the
action, and observe whether the ABAP Debugger fires.

This design enables that workflow for agents.

---

## Desktop Backend Only

**WebGUI (SAPGUI for HTML) does not support external breakpoints.**

Verified empirically: pressing Ctrl+Shift+F9 in the WebGUI source editor returns:

> "Aktion im 'SAPGUI for HTML' nicht möglich. Externes Debugging verwenden."

All three tools in this design require the desktop backend (`BACKEND_TYPE=desktop`).
Calling them on a WebGUI session must return an immediate `success=False` with a clear error:

> "External breakpoints are not supported on the WebGUI backend. Use BACKEND_TYPE=desktop."

---

## Tools

### `sap_breakpoint_set`

Sets an external breakpoint on a specific line of a program, class method, or function module.

```
sap_breakpoint_set(
    object_type: Literal["PROG", "CLAS", "FUGR"],
    object_name: str,
    line_number: int | None = None,
    match_pattern: str | None = None,
    method_name: str | None = None,
    session: str | None = None,
    agent_id: str | None = None,
) -> BreakpointSetResult
```

Exactly one of `line_number` or `match_pattern` must be provided.

### `sap_breakpoint_delete`

Deletes an external breakpoint on a specific line.

```
sap_breakpoint_delete(
    object_type: Literal["PROG", "CLAS", "FUGR"],
    object_name: str,
    line_number: int | None = None,
    match_pattern: str | None = None,
    method_name: str | None = None,
    session: str | None = None,
    agent_id: str | None = None,
) -> BreakpointDeleteResult
```

### `sap_breakpoint_list`

Lists all external breakpoints set for the current user on a given object.

```
sap_breakpoint_list(
    object_type: Literal["PROG", "CLAS", "FUGR"],
    object_name: str,
    method_name: str | None = None,
    session: str | None = None,
    agent_id: str | None = None,
) -> BreakpointListResult
```

---

## Parameters

| Parameter | Required for | Notes |
|-----------|-------------|-------|
| `object_type` | all | `"PROG"`, `"CLAS"`, or `"FUGR"` |
| `object_name` | all | Program name, class name, or function group name |
| `method_name` | CLAS, FUGR | Method name (CLAS) or FM name (FUGR); None for PROG |
| `line_number` | set/delete | 1-indexed SAP display line number |
| `match_pattern` | set/delete | Substring/regex; resolved to a line number before GUI navigation |

---

## Data Models

New file: `src/sapguimcp/models/breakpoint_models.py`

```python
class BreakpointEntry(BaseModel):
    line_number: int        # 1-indexed SAP display line
    source_line: str        # source code text at that line

class BreakpointSetResult(ToolResult):
    success: bool
    object_type: str
    object_name: str
    method_name: str | None
    line_number: int        # resolved line (also when set via match_pattern)
    action: Literal["set", "deleted_instead"]  # SAP toggle may delete if already set
    status_message: str     # raw SAP status bar message
    error: str | None

class BreakpointDeleteResult(ToolResult):
    success: bool
    object_type: str
    object_name: str
    method_name: str | None
    line_number: int
    action: Literal["deleted", "was_not_set"]
    status_message: str
    error: str | None

class BreakpointListResult(ToolResult):
    success: bool
    object_type: str
    object_name: str
    method_name: str | None
    breakpoints: list[BreakpointEntry]
    error: str | None
```

---

## Verified COM Mechanism (Desktop)

All findings verified live against S4 system.

### Cursor Positioning

```python
shell.SelectRange(line_number, 0, line_number, 0)
```

- Shell path: `wnd[0]/usr/cntlEDITOR/shellcont/shell` (SE38)
- `line_number` is **1-indexed** (matches SAP "Ze N" display)
- `SelectRange(6, 0, 6, 0)` positions cursor at Ze=6
- `SetCursorPosition`, `GotoLine`, `CurrentRow` are **not** available through the
  SAP GUI Scripting `FindById` wrapper — only accessible via raw COM in the Python backend

### Setting/Deleting Breakpoints

```python
session.SendVKey(45)   # on wnd[0]
```

- VKey 45 = Ctrl+Shift+F9 = "Externen Breakpoint setzen/löschen"
- VKey 46 = Ctrl+Shift+F10 = "Session-Breakpoint setzen/löschen" (not used here)
- `sap_press_key(key="Control+Shift+F9")` does **not** work on the desktop backend

### Toggle Behavior

VKey 45 **toggles**: sets if not set, deletes if already set.

**Consequence:** The tool must check the status bar after VKey 45 to determine what
actually happened:

| Status bar contains | Meaning |
|---------------------|---------|
| `"gesetzt"` | Breakpoint was set |
| `"gelöscht"` | Breakpoint was deleted (was already set) |

For `sap_breakpoint_set`: if result is `"gelöscht"`, the breakpoint was already present
and SAP deleted it. The tool re-applies VKey 45 once to restore it, then reports
`action="set"`. If this second attempt also fails, return `success=False`.

For `sap_breakpoint_delete`: if result is `"gesetzt"`, the line had no breakpoint and
SAP set one. The tool re-applies VKey 45 to remove it again, then reports
`action="was_not_set"`. If the second attempt also fails, return `success=False`.

### Continuation Lines

Verified: setting a breakpoint on a continuation line (e.g. an `EXPORTING` parameter
line inside a `CALL FUNCTION`) toggles the breakpoint of the parent statement.

Example — program RSINCL00:
```
6: CALL FUNCTION 'RS_CROSSREFERENCE'   ← breakpoint lives here
7:     EXPORTING
8:         PROGRAMM = PROGRAM           ← cursor here → toggles line 6 breakpoint
```

The tool does not try to detect this automatically. It reports whatever SAP actually
did via `line_number` (from `SelectRange` arg) and `status_message` (from status bar).
The agent is responsible for choosing executable lines.

### Listing Breakpoints

Via `Hilfsmittel > Breakpoints > Anzeigen...` menu in the source editor (menu index
`wnd[0]/mbar/menu[3]/menu[7]/menu[0]`). This opens a modal dialog on SAPLBREA/600
containing a `SAPGUI.GridViewCtrl.1` at `wnd[1]/usr/cntlG_BP_CONTAINER/shellcont/shell`.

**Verified workflow (live against S/4):**

1. Navigate to the program in SE38/SE24/SE37 (same as set/delete)
2. Select `wnd[0]/mbar/menu[3]/menu[7]/menu[0]` to open the dialog
3. The initial view shows only breakpoints for the current editor object. Click
   `wnd[1]/tbar[0]/btn[5]` ("Alle anzeigen") to expand to all breakpoints for the user
4. Read `RowCount` on the grid shell
5. For each row `i` in `range(RowCount)`, call:
   - `GetCellValue(i, "INCLUDE_DIS")` → include/program name
   - `GetCellValue(i, "SOURCE_LINE")` → line number as string (parse to int)
   - `GetCellValue(i, "SOURCE")` → source text at that line
   - `GetCellValue(i, "MAINPROGRAM_DIS")` → function group / main program name
6. Filter rows where `INCLUDE_DIS` matches the requested object/method
7. Close dialog with `wnd[1].SendVKey(12)` (F12 = Abbrechen)

**Verified column names** (from `FORM prepare_alv_bp` in `LBREAF10`):

| col_pos | FIELDNAME | Label | Content |
|---------|-----------|-------|---------|
| 1 | `ICON` | Typ | icon (use `GetCellIcon`, not `GetCellValue`) |
| 2 | `MAINPROGRAM_DIS` | Rahmenprogramm | function group / main program (e.g. `"BREA"`) |
| 3 | `INCLUDE_DIS` | Include | include or program name (e.g. `"LBREAO10"`) |
| 4 | `SOURCE_LINE` | Zeile | line number as string (e.g. `"18"`) |
| 5 | `SOURCE` | Quelltext | source text (e.g. `"IF reset_flag NE space."`) |

All four text columns verified live with `GetCellValue` returning correct values.

**Filter logic for `sap_breakpoint_list`:**
- For PROG: filter rows where `INCLUDE_DIS == object_name`
- For CLAS: filter rows where `MAINPROGRAM_DIS == class_name` (SAP stores class
  breakpoints in generated method includes but sets `MAINPROGRAM_DIS` to the class name;
  all breakpoints for the class are returned regardless of method)
- For FUGR: filter rows where `MAINPROGRAM_DIS == object_name` (function group name);
  all breakpoints in the function group are returned (SAP uses numbered includes per FM)

---

## Navigation Flow per Object Type

| Type | Transaction | Open | Navigate to code |
|------|------------|------|-----------------|
| PROG | SE38 | Click "Anzeigen" (F5 fails on desktop; button click works) | — |
| CLAS | SE24 | Click "Anzeigen" button | Methods tab → click "Quelltext" button (`btnPUSH_EDITOR`) |
| FUGR | SE37 | Click "Anzeigen" button | Opens directly on "Quelltext" tab; click tab `tabpSOURCE` to activate |

All navigation uses existing patterns from `se38_edit_tools.py` /
`se24_edit_tools.py` / `se37_edit_tools.py`.

## Verified Shell Paths per Transaction

The `AbapEditor` COM shell path varies per transaction. The implementation must
use the correct path for each object type rather than hardcoding a single path.

| Transaction | Shell path (relative to `wnd[0]`) |
|-------------|-----------------------------------|
| SE38 | `usr/cntlEDITOR/shellcont/shell` |
| SE24 | `usr/subEDITORSUBSCREEN:SAPLEDITOR_START:8430/cntlEDITOR/shellcont/shell` |
| SE37 | `usr/tabsFUNC_TAB_STRIP/tabpSOURCE/ssubSCREEN_HEADER:SAPLEDITOR_START:8430/cntlEDITOR/shellcont/shell` |

All three paths verified live:
- `GetLineCount` / `GetLineText` work identically on all three
- `SelectRange(n, 0, n, 0)` is 1-indexed on all three (matching SAP display "Ze N")
- `SendVKey(45)` on `wnd[0]` sets/deletes external breakpoints on all three

The `SAPLEDITOR_START:8430` token in SE24/SE37 paths is the subscreen dynpro
number. It is constant for these transactions on this S/4 system (verified), but
the implementation may optionally scan the COM tree for the `AbapEditor` shell
as a fallback if the path changes on other systems or releases.

---

## Pattern-to-Line Resolution

When `match_pattern` is provided instead of `line_number`:

1. Read the source using the existing read-source mechanism
   (`GetLineCount` / `GetLineText` via raw COM, already in the desktop backend)
2. Find the first line (1-indexed) matching the substring or regex
3. Use that line number for `SelectRange` and `SendVKey`

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| WebGUI backend | `success=False`, explain desktop-only limitation |
| Object not found | `success=False`, report SE38/SE24/SE37 navigation error |
| `match_pattern` not found in source | `success=False`, "Pattern not found" |
| Line number out of range | `success=False`, "Line N exceeds source length (M lines)" |
| Toggle resulted in opposite action (double-toggle failed) | `success=False`, report status messages |
| `method_name` missing for CLAS/FUGR | `success=False`, "method_name required for CLAS/FUGR" |
| Navigation failed (wrong screen after transaction) | `success=False` + status bar text |

---

## Files

### New files
- `src/sapguimcp/tools/breakpoint_tools.py`
- `src/sapguimcp/models/breakpoint_models.py`

### Modified files
- `src/sapguimcp/tools/__init__.py` — add `register_breakpoint_tools`
- `src/sapguimcp/server.py` — register tool

### Tests
- `unittests/test_breakpoint_models.py` — unit tests for model validation
- `unittests/desktop/test_breakpoint_tools.py` — integration tests
  (marked `@pytest.mark.integration`, skipped in CI without SAP access)

---

## Open Questions

~~1. **Listing via dialog vs. raw COM**: The `Hilfsmittel > Breakpoints > Anzeigen...`
   dialog approach needs a live prototype to confirm the dialog structure.~~
   **Resolved**: Dialog verified live. Use `Alle anzeigen` (btn[5]) + `GetCellValue` with
   columns `INCLUDE_DIS`, `SOURCE_LINE`, `SOURCE`, `MAINPROGRAM_DIS`. No fallback needed.

~~2. **SE24 method navigation**: Multi-step (class → Methods tab → method → source view).~~
   **Resolved**: Use Methods tab → click `btnPUSH_EDITOR` ("Quelltext") button.
   Shell path verified: `usr/subEDITORSUBSCREEN:SAPLEDITOR_START:8430/cntlEDITOR/shellcont/shell`.

~~3. **SelectRange index on SE24/SE37**: Verified only for SE38. Expected to be identical~~
   **Resolved**: Verified live on SE24 and SE37 — identical 1-indexed behavior.
