# sap_se16_query: fail on filter fields that cannot be applied (#907)

## Problem

`sap_se16_query` fills the SE16N selection criteria before running the query. If a requested
filter field cannot be applied, the error is only stored in `filter_warnings` and the query
runs anyway. The result looks like a valid answer:

1. **Unknown field, no matching rows.** SE16N reports "no values found". The error result
   comes from `_empty_failure`, which drops `filter_warnings`, so the caller sees a genuine
   "not found" with no warning at all.
2. **Unknown field, populated table.** Rows come back unfiltered with `success=true`, and only
   a warning that is easy to miss.
3. **A field that exists in the table but is not offered as an SE16N selection field.** Same as
   case 2.

Agents use the tool for existence checks, so a typo in a field name gives them a confident
wrong answer either way.

## Decision

If **any** filter cannot be applied, the tool fails **before the query runs**. There is no
opt-out flag: a caller who wants fewer filters omits them. This applies to both the desktop and
the WebGUI backend.

Validating the fields up front (via SE11/DDIC) was rejected. It costs an extra round trip and
cannot detect case 3, which depends on SE16N.

## Design

### Where the check happens

- **Desktop:** `_execute_se16_query_desktop`, right after `_fill_se16n_filters_desktop`
  (`src/sapguimcp/tools/se16_tools.py`, around line 707).
- **WebGUI:** `_execute_se16_query`, right after `_fill_se16n_filters` (around line 830).

If the fill step returns any error, the function returns a failure result and does not execute
the query. Any other fill error (for example "selection criteria table control not found") is
treated the same way.

### Failure result

- `success=false`, `total_hits=0`, no rows.
- `filter_warnings`: the individual per-field messages, as today.
- `error`:

    > Filter field(s) 'X', 'Y' not available as SE16N selection criteria for table T.
    > Offered fields: A, B, C, …. A field can exist in the table without being an SE16N selection
    > field; use sap-adt `run_query` if available.

    The offered-fields list is capped at 50 names, followed by "… (+N more)". If the list is not
    known, the "Offered fields" sentence is left out. Errors that are not about a field (such as a
    missing table control) are reported as they are, not with the template above.

### Collecting the offered fields

- **Desktop:** the scan in `_apply_filters` and `_set_filter_with_scrolling` already walks the
  selection rows. It also records the technical field names it sees and returns them together
  with the errors. A full walk only happens when a field was not found, so the success path
  costs nothing extra.
- **WebGUI:** the offered fields are the keys of the existing `field_order` mapping (from SE11).
  When that metadata is unavailable, the list is omitted.

### Side fix

`_empty_failure` gets an optional `filter_warnings` parameter, so no exit path drops warnings.

### Docs

The `sap_se16_query` tool description states that a filter field that is unknown, or not
offered by SE16N, makes the call fail and lists the fields that are offered.

## Tests

### Reproducible integration tests (required)

They are written first and must **fail on current main**, then pass after the fix. They use only
standard SAP tables present on every system, with no namespaced objects and no system-specific
values.

- **Case 1:** on a populated standard table (e.g. `T000`), a valid filter that matches nothing
  plus a made-up field. Today this returns "no values found" with empty `filter_warnings`.
  Expected: `success=false`, the made-up field named in `error`, and a non-empty offered-fields
  list.
- **Case 2:** a populated standard table with only a made-up field. Today this returns unfiltered
  rows with `success=true`. Expected: `success=false` and no rows.
- **Case 3:** a real column of a standard table that SE16N does not offer as a selection field,
  for example a long string column. The implementer identifies a suitable standard table on the
  live system. If none is reliably available, this case is covered by unit tests only, and the
  reason is noted in the test file.

These tests run on the desktop backend and the WebGUI backend, following each backend's existing
SE16 integration test pattern. As usual, the live tests run one at a time.

### Unit tests

- For both backends, with the fill function mocked:
    - a fill error means the query is never executed, and the error contains the field name and
      the offered list;
    - no fill error leaves the behaviour unchanged.
- The offered-fields cap and the "+N more" suffix.
- `_empty_failure` passes `filter_warnings` through.

## Out of scope

- A `lenient` flag.
- "Did you mean" suggestions.
- A fallback to another query mechanism.
