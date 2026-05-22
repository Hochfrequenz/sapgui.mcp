# `sap_fill_form` Desktop Backend Performance Fix

**Date**: 2026-04-07
**Issue**: Hochfrequenz/sapgui.mcp#627
**Branch (sapguimcp)**: TBD

## Problem

On the desktop backend, `sap_fill_form` times out when filling more than a
handful of label-matched fields in a single call. The reported reproduction
is creating a Business Partner via transaction `BP` (person creation), which
needs ~7 fields (Vorname, Nachname, Land/Region, Strasse, PLZ, Ort, etc.).

### Surface symptoms

When the agent passes the *correct* payload shape
(`{"fields": {...}, "strict": false}`):

- The MCP client (e.g. OpenCode) waits for the request.
- The server is busy inside the `_fill` COM closure: dump tree, look up label
  1, dump tree again for label 2, and so on.
- The MCP client's per-request timer expires. The client returns
  `MCP error -32001: Request timed out`.
- The server keeps running. It may finish the fills a few seconds later, but
  nobody is listening — the result never reaches the agent.
- No exception is raised on the server side. No traceback in the logs. The
  call simply takes too long and the client gives up.

The first error in the issue
(`Additional properties are not allowed`) is unrelated to performance — it
comes from the agent guessing the wrong payload shape on its first attempt.
That's a pure documentation problem, addressed separately in this spec.

### Root cause

`desktop.fill_form` runs the entire field-iteration loop inside a single
`self.com.run(_fill)` call. Each iteration calls `find_field_by_label`, which
internally calls `dump_tree()` once or twice depending on which strategy
succeeds:

| Strategy | Function                              | Calls `dump_tree`? |
| -------- | ------------------------------------- | ------------------ |
| 1        | `_find_by_name_prefix`                | No                 |
| 2        | `_find_by_label_text`                 | **Yes**            |
| 3        | `_find_by_readonly_textfield_label`   | **Yes**            |
| 4        | `_find_by_sap_name`                   | No                 |

For German BP labels like `Vorname`, `Nachname`, Strategy 1 misses, so
Strategy 2 fires (1 dump). For composite labels like `Strasse/Hausnummer`,
Strategy 2 misses too and Strategy 3 fires (2 dumps total). For 7 fields
that's roughly 7-14 full tree dumps in one synchronous COM call.

`dump_tree()` is the dominant cost: it walks the entire `usr` subtree of the
active window and serialises every element via COM. On a complex screen this
runs into seconds per dump.

### Why the WebGUI backend is unaffected

`webgui.fill_form` is one `page.evaluate` call that fills all fields in JS.
There is no per-field round-trip. The bug is desktop-specific.

### When the bug was introduced

- **2026-03-15**, commit `7eec6feb` (#376, *feat(desktop): Phase 2 - fill
  fields, click buttons, element finder*) - desktop `fill_form` and
  `find_field_by_label` are added in this commit. Strategy 2 already calls
  `dump_tree` per call. At this point: 1 dump per missed-Strategy-1 field.
- **2026-03-19**, commit `2fd35e8c` (#452, *composite label support for
  sap_fill_form*) - Strategy 3 added. Strategy 3 also calls `dump_tree`, so
  any field that misses Strategy 2 now does **two** dumps. This is the
  commit that turned a slow function into one that times out on real
  payloads.
- **2026-04-05**, commit `6e589e7a` (#612, active-window refactor) - touched
  `fill_form`'s window resolution but did not change the per-field dump
  pattern.

The bug has therefore existed in some form since 2026-03-15 (~3 weeks at
time of writing) and got materially worse on 2026-03-19. It only surfaced
in #627 because that was the first reproduction with enough labelled fields
on a single screen to blow past the MCP client timeout.

## Design

### Principle

**The flat element tree is loop-invariant input, not a cache.** Within a
single `fill_form` call the form does not move between fields, so the same
flat tree can serve every label lookup in the loop. We hoist the
`_flatten(dump_tree())` computation out of the per-field path and pass it
in explicitly. There is no shared state, no eviction policy, no `is the
cached value still fresh` check anywhere. The tree is a parameter the way
`label` is a parameter.

### Part 1: element-finder signature change

`find_field_by_label` and the two strategy helpers that walk the tree gain
`flat_tree` as a **required** positional parameter. There is no `flat_tree=
None` fallback that fetches a fresh tree internally - that branchiness is
exactly what would make the change feel cache-like.

```python
def find_field_by_label(
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None: ...

def _find_by_label_text(
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None: ...

def _find_by_readonly_textfield_label(
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None: ...
```

Inside `_find_by_label_text` and `_find_by_readonly_textfield_label`, the
`usr = session.find_by_id(...); tree = usr.dump_tree(); flat = _flatten(tree)`
preamble is removed. The body iterates the parameter directly.

Strategies 1 (`_find_by_name_prefix`) and 4 (`_find_by_sap_name`) are not
modified - they don't walk the tree.

### Part 2: caller updates in `desktop/__init__.py`

There are five production callers of `find_field_by_label` in the desktop
backend. Each must compute a `flat_tree` once at the top of its COM closure
and pass it to every call:

| Line  | Method                      | Calls per closure |
| ----- | --------------------------- | ----------------- |
| ~929  | `fill_field`                | 1                 |
| ~944  | `fill_main_input`           | up to len(labels) |
| ~966  | `fill_form` **(perf path)** | len(fields)       |
| ~1104 | `select_dropdown`           | 1 (fallback)      |
| ~1147 | `focus_and_type`            | 1 (fallback)      |

For single-call sites (`fill_field`, `select_dropdown`, `focus_and_type`)
the change is purely mechanical: compute the tree, pass it. The behaviour
is identical to today (still one dump per call).

For `fill_form` and `fill_main_input`, the win is that the same tree is
reused across the loop. `fill_form` is the user-visible fix; `fill_main_input`
gets the same treatment for free because they share the helper.

A small helper added to
`src/sapguimcp/backend/desktop/_element_finder.py` keeps the
dump-and-flatten idiom in one place. It is a module-private helper named
with a leading underscore, matching the existing `_flatten` convention in
the same file:

```python
def _dump_flat_tree(session: Any, wnd_id: str = "wnd[0]") -> list[Any]:
    """Dump and flatten the usr subtree of the given window."""
    usr = session.find_by_id(f"{wnd_id}/usr")
    return _flatten(usr.dump_tree())
```

Each caller becomes:

```python
def _fill() -> None:
    wnd_id = _active_window_id(session)
    flat_tree = _dump_flat_tree(session, wnd_id)
    field = find_field_by_label(session, label, flat_tree, wnd_id=wnd_id)
    ...
```

### Part 3: tool documentation fix

The MCP tool description for `sap_fill_form` in
`src/sapguimcp/tools/sap_tools.py` (~line 1146) currently lists key
formats but never shows a complete payload. Append a single canonical
example to the description string:

```
Example payload:
  {"fields": {"Vorname": "Mario", "Nachname": "Rossi"}, "strict": false}
```

This is purely a docstring change. FastMCP derives the schema from the
type hints, so no schema work is needed. The first error in #627
("Additional properties are not allowed") was the agent guessing the
wrong shape on attempt 1; a visible example prevents the same guess.

### Out of scope

- `find_button_by_label`, `find_checkbox_by_label`, `find_radio_by_label`,
  `find_combobox_by_label`. They follow the same `dump_tree` per call
  pattern, but they are only called from single-field tools today
  (`sap_click_button`, `sap_set_checkbox`, `sap_set_radio_button`,
  `sap_select_dropdown`). No batch caller exists. YAGNI - revisit if a
  `sap_click_buttons`-style batch tool ever lands.
- Server-side `wait_for_ready` between fields in `fill_form`. Today's code
  doesn't do this and this refactor doesn't add it. Out of scope.
- MCP-client-side timeout handling, partial-progress reporting on
  client-side timeout, retry logic. Not achievable from the server: the
  server doesn't know the client gave up.

## Error handling and edge cases

**1. Empty or malformed tree.** If `dump_tree()` returns an empty list, the
loops in Strategies 2 and 3 simply do not match anything and the function
falls through to Strategy 4 (SAP `find_by_name`). Identical to today's
behaviour.

**2. `dump_tree()` itself raises.** If the COM call to fetch the tree fails
(session died, window vanished), the `_fill` closure raises before the field
loop starts. The existing `except Exception` in
`sap_tools.py:sap_fill_form` catches it and returns `FillFormResult.failure`.
Today the same exception would surface from inside the loop on the first
field; the user-visible result is identical.

**3. Tree staleness mid-loop.** With the hoisted dump, all fields in one
`fill_form` call look up against the same snapshot of the tree. If filling
field N somehow reshapes the form before field N+1's lookup, that snapshot
is stale where today it would have been re-dumped. Realistic scenarios:

- **F4 search-help auto-popup** - extremely unlikely from a plain
  `_set_field_value`; F4 is triggered by the F4 key, not by setting `.text`.
- **Backend-validated dropdowns that reshape the screen on selection** -
  possible in theory, but `_set_field_value` for combobox sets `.key` and
  does not trigger ENTER, so no server round-trip happens between fields.
- **Field-exit events with screen reshuffle** - possible but rare.

These are documented as a known limitation: if a `fill_form` call hits a
field that reshapes the form, split it into two `fill_form` calls. We do
not try to detect staleness automatically - that is where real caches and
real complexity start.

**4. `not_found` and `errors` reporting.** Unchanged. Same lists, same
strict-mode behaviour in the MCP layer.

## Testing

### Existing tests to update

`unittests/desktop/test_element_finder.py` has ~10 call sites of
`find_field_by_label` (lines 77, 86, 94, 113, 128, 141, 275, 306, 330, 346).
Each will fail to compile after the signature change. The fix is
mechanical: build a `flat_tree` from the test's fake-session COM tree
(using the same `_flatten(...dump_tree())` idiom) and pass it in. No
behavioural changes to existing assertions.

Existing `desktop.fill_form` and `desktop.fill_field` tests should keep
passing without modification because the public methods' signatures are
unchanged.

### New tests

1. **Unit: `find_field_by_label` accepts a pre-built tree.** Pass a
   hand-built `flat_tree` (list of fake elements) to `find_field_by_label`
   and assert it finds the expected field via Strategy 2 *without* the
   test's mock session being asked for `dump_tree`. Proves the helper no
   longer dumps internally.

2. **Unit: `fill_form` calls `dump_tree` exactly once for N fields.** Mock
   the COM session's `dump_tree`, call `desktop.fill_form` with 5 fields,
   assert `dump_tree.call_count == 1`. This is the regression test for
   #627. If anyone reintroduces a per-field dump in the future, this fails
   loudly with a clear message.

3. **Unit: `fill_form` reports `not_found` when the cached tree doesn't
   contain the label.** Same fake tree, ask for a label that isn't there,
   assert it lands in `not_found` rather than `errors`.

4. **Integration (desktop, marked `skip_no_sap`): BP person creation with
   multi-field `fill_form`.** Add a test to `unittests/desktop/test_bp_
   integration.py` (or extend the existing one) that fills 5-7 fields in
   the BP person-creation screen via a single `sap_fill_form` call and
   asserts it completes well under any reasonable timeout (soft-assert
   wall-clock < 5 seconds). This is the end-to-end proof that the
   user-reported scenario actually works.

### Not tested

- Tree-staleness scenarios. Documented as a known limitation, not a
  supported feature, so there's nothing to assert.
- Performance microbenchmarks. The `dump_tree.call_count == 1` assertion
  captures the intent without flakiness from CI host load.

### Documentation change verification

The tool description update in `sap_tools.py` is a string literal. Visual
inspection only - no test needed.

## Migration / rollout notes

- The change to `find_field_by_label`'s signature is API-breaking for
  in-tree callers but the function is private to the desktop backend
  (`src/sapguimcp/backend/desktop/_element_finder.py`). No external
  consumers exist.
- The MCP-facing tool API (`sap_fill_form` request shape) does not change.
- The MCP tool description string changes; agents reading the tool list
  will see the new example payload.
