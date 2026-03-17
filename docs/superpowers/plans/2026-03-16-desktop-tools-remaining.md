# Desktop Tools — Remaining Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete desktop backend support for ALL transaction tools — remove all `skip` markers and error stubs.

**Architecture:** Each tool has an `_is_desktop_backend()` check that routes to a desktop-specific code path. Desktop paths use protocol methods (`read_table`, `discover_fields`, `fill_field`, `set_checkbox`, etc.) instead of ARIA parsing. Same return models as WebGUI.

**Tech Stack:** Python 3.11+, pywin32 (COM), pydantic, pytest

**Tracks:** GitHub issue #377

---

## Key Design Decisions & Lessons Learned

These were discovered during implementation and live testing against HF S/4 (S4U, client 100).
Future implementers MUST read these before writing code.

### COM Threading

- All COM calls MUST run on a dedicated background thread (`ComThread`) with its own `CoInitialize()`. Cross-apartment calls cause `Windows fatal exception 0x800401f0`.
- Use `concurrent.futures.Future` + `asyncio.wrap_future` for cross-thread dispatch.
- Test teardown must close connections VIA the COM thread (`await com.run(lambda: conn.CloseConnection())`), not from the main thread.
- `faulthandler.disable()` around `com.shutdown()` suppresses COM finalization noise.

### SAP GUI COM Quirks

- `send_command("/nEX")` blocks indefinitely on COM. Use `connection.CloseConnection()` instead.
- `FindById` returns COM objects with broken dispatch typing for shell controls. `NumberOfLines`, `GetLineText` etc. may fail with `AttributeError`. Try both wrapper and raw COM (`shell.com.NumberOfLines`) as fallback.
- SAP GUI leaves "ghost connections" (0 sessions) after closing. Must clean up via `CloseConnection()`.
- `AriaSnapshot` doesn't exist for desktop. We use `ComTreeSnapshot` (a `str` subclass) — parsers must NOT assume ARIA format.

### Element Finding

- SAP labels and fields share name suffixes: `lblMATNR` → `txtMATNR` / `ctxtMATNR`. This is the fastest lookup strategy.
- Fields may be nested in `GuiSimpleContainer`, `GuiScrollContainer`, or other subcontainers — don't assume flat `wnd[0]/usr/` children.
- Extract the container path from the label's ID to handle nested fields correctly.
- Exact text match before substring match to avoid "Name" matching "Company Name".
- `LogRecord` reserves `"name"` as a key — never use `extra={"name": ...}` in logging. Use `"field_name"` instead.

### ALV Grid Location

- SE16N places its ALV grid in `wnd[0]/shellcont/shell` (a dock shell), NOT under `wnd[0]/usr`. `read_table` and `click_table_cell` must search the full `wnd[0]` tree with `max_depth=5`.

### Login & Session Management

- Connection = separate TCP link with its own login (`open_connection`). Session/Mode = window within a connection (`create_session` / `/o`). Never confuse these.
- The "multiple logon" popup (`radMULTI_LOGON_OPT2`) default radio selection is NOT stable. Always explicitly select OPT2.
- Login screen is program `SAPMSYST`, screen 20. Field IDs: `txtRSYST-MANDT`, `txtRSYST-BNAME`, `pwdRSYST-BCODE`, `txtRSYST-LANGU` — standard on ALL systems.
- `DisabledByServer=True` means scripting is disabled on the server. Fix via RZ11: `sapgui/user_scripting=TRUE`.

### Tool Implementation Pattern

- Check `_is_desktop_backend(backend)` at the top of the main tool function.
- Route to `_*_desktop()` function with same return model.
- Never modify WebGUI code paths.
- Use `focus_and_type(field_name, value)` for filling fields by SAP field name.
- Use `fill_field(label, value)` for filling by label text (language-dependent).
- Try both DE and EN labels in loops for language independence.
- Always navigate back after tool execution (`press_key("F3")` × N).

### Testing

- Integration tests must exercise the actual desktop tool function, not just backend methods.
- Each test must verify: result model type, non-empty data, `model_dump_json()` roundtrip.
- SAP is stateful — don't assert on specific default values or button labels.
- Test teardown must close ALL connections (not just the backend's session) to prevent ghost windows.
- Each transaction gets its own test file, matching the WebGUI structure.

---

## Current State (after PR #379)

### Working desktop tools

| Tool | Status        | Gaps                                                        |
| ---- | ------------- | ----------------------------------------------------------- |
| SE16 | Works         | Filters not implemented                                     |
| SM37 | Works         | Status/date filters work, `include_log` not supported       |
| SM30 | Works         | Basic view display                                          |
| SE09 | Works (basic) | `request_type`, `status`, `include_objects` filters ignored |
| SLG1 | Works         | Date filters work, `subobject`/`external_id` not tested     |
| ST22 | Partial       | Dump list works, dump detail stubbed                        |

### Stub tools (return error)

SE93, SE24, SE37, SPRO

### Skipped integration tests (5 total)

- `test_se16_single_filter` — SE16 desktop filters not implemented
- `test_se16_multiple_filters` — SE16 desktop filters not implemented
- `test_se09_workbench_only` — SE09 request_type filter not implemented
- `test_se09_released_only` — SE09 status filter not implemented
- `test_se09_no_results_fake_user` — SE09 user filter not implemented

---

## Task 1: SE09 Filter Support

**Priority:** High (15% → ~80% test coverage)
**Effort:** Small

### What to implement

In `_lookup_transports_desktop()` in `se09_tools.py`:

1. **request_type filter**: SE09 has checkboxes for "Workbench" and "Customizing" on the selection screen. Toggle them based on `request_type` parameter:
    - `"workbench"` → check Workbench, uncheck Customizing
    - `"customizing"` → uncheck Workbench, check Customizing
    - `"all"` → check both (default)

2. **status filter**: SE09 has radio buttons for "Modifiable" and "Released":
    - `"modifiable"` → select Modifiable radio
    - `"released"` → select Released radio
    - `"all"` → need to check how to show all (might need a different approach)

3. **include_objects**: After getting transport list, expand each transport node to get object list. Use `session.find_by_id` to navigate tree control.

### Steps

- [ ] Explore SE09 screen via COM to find checkbox/radio IDs
- [ ] Implement checkbox toggling in `_lookup_transports_desktop`
- [ ] Implement radio button selection for status
- [ ] Unskip `test_se09_workbench_only`, `test_se09_released_only`, `test_se09_no_results_fake_user`
- [ ] Add more tests: `test_se09_customizing_only`, `test_se09_all_status`
- [ ] Run integration tests against live SAP
- [ ] Commit

---

## Task 2: SE16 Filter Support

**Priority:** High (most-used tool)
**Effort:** Medium

### What to implement

In `_execute_se16_query_desktop()` in `se16_tools.py`:

SE16N has a selection criteria grid (ALV) where each row represents a field filter. To set a filter:

1. Find the row for the field name in the grid
2. Set the "From-Value" cell to the filter value

The grid has columns: Feldname/Field Name, Option, Von-Wert/From-Value, Bis-Wert/To-Value, Mehr/More, Ausgabe/Output, Technischer Name/Technical Name.

### Steps

- [ ] Explore SE16N selection grid via COM — find how to identify rows by field name
- [ ] Implement: after filling table name and pressing Enter (to load field list), iterate grid rows to find matching field, set From-Value
- [ ] Handle single filter (`{"TCODE": "SE16"}`)
- [ ] Handle multiple filters
- [ ] Handle wildcard filters (e.g., `{"TCODE": "SE*"}`)
- [ ] Unskip `test_se16_single_filter`, `test_se16_multiple_filters`
- [ ] Add tests matching WebGUI: `test_se16_filter_with_special_chars`, `test_se16_query_bug_report_filters`
- [ ] Run integration tests
- [ ] Commit

---

## Task 3: ST22 Dump Detail

**Priority:** Medium
**Effort:** Small

### What to implement

In `_st22_lookup_desktop()` in `st22_tools.py`:

When `dump_index` is provided:

1. Read the dump list via `read_table`
2. Double-click the specified row (using `click_table_cell` with action `"dblclick"`)
3. Read the detail screen fields via `discover_fields` + `get_screen_text`
4. Return `ST22DumpDetailResult`

### Steps

- [ ] Explore ST22 dump detail screen via COM
- [ ] Implement double-click on dump row
- [ ] Read detail screen fields
- [ ] Add tests: `test_st22_dump_detail`, `test_st22_dump_index_out_of_range`
- [ ] Commit

---

## Task 4: SE93 — Transaction Code Lookup

**Priority:** Medium
**Effort:** Small

### What to implement

New `_lookup_transaction_desktop()` in `se93_tools.py`:

1. `enter_transaction("SE93")`
2. `fill_field("Transaktionscode"/"Transaction code", tcode)`
3. Click Display button
4. Read screen fields: transaction type, program, screen number, description
5. Return `SE93Result`

### Steps

- [ ] Explore SE93 display screen via COM
- [ ] Implement `_lookup_transaction_desktop`
- [ ] Remove stub, add desktop path
- [ ] Add tests: `test_se93_lookup_se16`, `test_se93_lookup_nonexistent`
- [ ] Commit

---

## Task 5: SPRO — IMG Tree Search

**Priority:** Low
**Effort:** Medium

### What to implement

New desktop path in `spro_tools.py`:

1. `enter_transaction("SPRO")`
2. Click "SAP Reference IMG" button
3. Search tree for query text
4. Read tree nodes as activities
5. Return `SPROSearchResult`

Requires reading GuiTree control — `get_all_node_keys`, `get_node_text_by_key`, etc.

### Steps

- [ ] Explore SPRO tree control via COM
- [ ] Implement tree reading
- [ ] Remove stub
- [ ] Add tests
- [ ] Commit

---

## Task 6: SE24 — Class Builder Reader

**Priority:** Low
**Effort:** Large

### What to implement

New desktop path in `se24_tools.py`:

1. `enter_transaction("SE24")`
2. `fill_field("Object Type"/"Objekttyp", class_name)`
3. Click Display
4. Navigate tabs: Methods, Attributes, Interfaces
5. Read each tab's table/fields
6. Return `SE24Result`

Complex: requires tab navigation, table reading per tab, handling the language dialog.

### Steps

- [ ] Explore SE24 screen structure via COM (tabs, fields, tables)
- [ ] Implement tab-by-tab reading
- [ ] Remove stub
- [ ] Add comprehensive tests matching WebGUI coverage
- [ ] Commit

---

## Task 7: SE37 — Function Module Reader

**Priority:** Low
**Effort:** Large

### What to implement

New desktop path in `se37_tools.py`:

1. `enter_transaction("SE37")`
2. `fill_field("Function Module"/"Funktionsbaustein", fm_name)`
3. Click Display
4. Navigate tabs: Import, Export, Changing, Tables, Exceptions
5. Read each tab's parameters
6. Return `SE37Result`

Similar complexity to SE24 — multi-tab navigation.

### Steps

- [ ] Explore SE37 screen structure via COM
- [ ] Implement tab-by-tab reading
- [ ] Remove stub
- [ ] Add tests
- [ ] Commit
