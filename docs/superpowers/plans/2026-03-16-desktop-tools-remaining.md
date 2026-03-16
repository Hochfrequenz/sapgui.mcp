# Desktop Tools — Remaining Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete desktop backend support for ALL transaction tools — remove all `skip` markers and error stubs.

**Architecture:** Each tool has an `_is_desktop_backend()` check that routes to a desktop-specific code path. Desktop paths use protocol methods (`read_table`, `discover_fields`, `fill_field`, `set_checkbox`, etc.) instead of ARIA parsing. Same return models as WebGUI.

**Tech Stack:** Python 3.11+, pywin32 (COM), pydantic, pytest

**Tracks:** GitHub issue #377

---

## Current State (after PR #379)

### Working desktop tools
| Tool | Status | Gaps |
|------|--------|------|
| SE16 | Works | Filters not implemented |
| SM37 | Works | Status/date filters work, `include_log` not supported |
| SM30 | Works | Basic view display |
| SE09 | Works (basic) | `request_type`, `status`, `include_objects` filters ignored |
| SLG1 | Works | Date filters work, `subobject`/`external_id` not tested |
| ST22 | Partial | Dump list works, dump detail stubbed |

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
