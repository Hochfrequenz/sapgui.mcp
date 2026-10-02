# sap_se16_query (desktop): fail on filter fields that cannot be applied (#907)

## Scope

This spec covers the **desktop backend** only (`_execute_se16_query_desktop`). The desktop backend
comes first. The WebGUI backend follows separately: its filter fill matches fields by position
and can set the wrong row (#924), so its strict mode is designed together with that fix.

## Problem

`sap_se16_query` fills the SE16N selection criteria before it runs the query. If a requested
filter field cannot be applied, `_fill_se16n_filters_desktop` returns an error message. The code
stores it in `filter_warnings` and runs the query anyway (`src/sapguimcp/tools/se16_tools.py`,
around lines 704-710). The result looks like a valid answer:

1. **Unknown field, no matching rows.**
    - If SE16N reports this through an error-type status bar message, the code returns
      `_empty_failure` (around line 727). `_empty_failure` has no `filter_warnings` parameter, so
      the warning is lost and the caller sees an ordinary "not found".
    - If SE16N reports it through the "no values / no entries" text branch, the warning is kept
      but `success` is still true with 0 hits.
2. **Unknown field, populated table.** The rows come back unfiltered with `success=true`, and
   there is only a warning, which is easy to miss.
3. **A field that exists in the table but that SE16N does not offer as a selection field.** Same
   as case 2.

Agents use this tool for existence checks, so a typo in a field name gives them a confident
wrong answer either way.

## Decision

If **any** filter cannot be applied, the tool fails **before F8**, so the query never runs. There
is no opt-out flag: a caller who wants fewer filters omits them.

Validating the fields up front against SE11/DDIC was rejected. It costs an extra round trip and
cannot detect case 3, which depends on what SE16N offers.

## Design

### Structured fill result

`_fill_se16n_filters_desktop` returns a small dataclass instead of `list[str]`:

```python
@dataclass
class _FilterFillResult:
    unapplied_fields: list[str]   # requested field names (as given) not found in the SE16N grid
    other_errors: list[str]       # non-field problems, e.g. "selection criteria table control not found"
    offered_fields: list[str]     # technical names seen in the grid, de-duplicated, grid order
```

- `offered_fields` is filled only when some field was not found, because only then is the whole
  grid walked. The success path costs nothing extra.
- The walk is done once and the result is cached for the remaining missing fields. Rows seen
  more than once because scroll windows overlap are de-duplicated, keeping the order.
- `_find_and_set_filter_cell` and `_set_filter_with_scrolling` also report the field names they
  saw, so the collected names come from the scan that already exists rather than a second pass.
- The non-desktop guard ("Filter filling requires DesktopBackend") becomes an `other_errors`
  entry.

### Failure result

In `_execute_se16_query_desktop`, right after the fill and before setting max hits and pressing
F8:

- **`unapplied_fields` non-empty**: return a failure with
    - `success=false`, `total_hits=0`, no rows;
    - `filter_warnings`: one message per unapplied field, worded as today
      ("Field 'X' not found in SE16N selection criteria"), plus any `other_errors`;
    - `error`:

        > Filter field(s) 'X', 'Y' not available as SE16N selection criteria for table T. Offered
        > fields: A, B, C, …. A field can exist in the table without being an SE16N selection field;
        > use sap-adt `run_query` if available.

        The offered list is capped at 50 names followed by "… (+N more)". If it is empty, the
        "Offered fields" sentence is left out.
- **Only `other_errors` non-empty**: fail with `error` = "Could not apply filters: " followed by
  the messages joined with "; ". `filter_warnings` holds the same messages.
- **Both non-empty**: the unapplied-fields error as above, with the `other_errors` messages
  appended to `filter_warnings`.

Before returning, the backend leaves the SE16N selection screen exactly as other failure paths
do today. No extra navigation is needed.

### Side fix

`_empty_failure` gets an optional `filter_warnings: list[str] | None = None` parameter. The
desktop error-status-bar path passes the warnings through, so no desktop exit path drops them.
After this change no warnings should exist at F8 time, but the pass-through is kept so that it
stays correct.

### Unchanged

- The success path, the WebGUI backend, and the `output_file` path. `SE16FileSummary` is only
  built from a successful result.

### Docs

The `sap_se16_query` tool description says that on the desktop backend a filter field that is
unknown, or not offered by SE16N, makes the call fail and lists the offered fields.

## Tests

### Reproducible live integration tests (required, desktop)

These are written **first** and must **fail on current main**, then pass after the fix. They
use only standard SAP tables present on every system, with no namespaced objects and no
system-specific values. They follow the existing desktop SE16 integration test pattern and are
run one at a time.

- **Case 1:** a populated standard table (e.g. `T000`) with a valid filter that matches nothing
  (e.g. `MANDT = "ZZZ"`) plus a made-up field. Expected: `success=false`, the made-up field named
  in `error`, a non-empty offered list that contains `MANDT`, and no rows.
- **Case 2:** a populated standard table with only a made-up field. Today this returns unfiltered
  rows with `success=true`. Expected: `success=false` and no rows.
- **Case 3:** a real column of a standard table that SE16N does not offer as a selection field,
  for example a long string or raw-string column. The implementer identifies a suitable
  standard table on the live system, such as through DDIC metadata. If none is reliably
  available, case 3 is covered by unit tests only, and the reason is written in the test file.
- **Regression:** a valid filter on a standard table still returns filtered rows with
  `success=true`.

### Unit tests

- An unapplied field means F8 is never pressed. `error` contains the field name and the offered
  list, and `filter_warnings` contains the per-field messages.
- `other_errors` only, and both kinds together, as specified above.
- The offered list: the 50-name cap with the "+N more" suffix, de-duplication, and an empty list
  (no "Offered fields" sentence).
- `_empty_failure` passes `filter_warnings` through.
- No fill errors: the behaviour is unchanged.

## Out of scope

- The WebGUI backend (follow-up together with #924).
- A `lenient` flag.
- "Did you mean" suggestions.
- A fallback to another query mechanism.
