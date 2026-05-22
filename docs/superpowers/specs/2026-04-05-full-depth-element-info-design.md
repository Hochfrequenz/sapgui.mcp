# Full-Depth Element Tree with Comprehensive Attributes

**Date**: 2026-04-05
**Branch (sapsucker)**: `feat/full-element-info`
**Branch (sapguimcp)**: `feat/full-depth-tree`

## Problem

The desktop backend repeatedly misses GUI elements and attributes:

1. **`ElementInfo` is too thin.** Only 6 of 15+ COM properties are captured (id,
   type, type_as_number, name, text, changeable). Missing properties like tooltip
   and icon_name require separate COM roundtrips per element — leading to
   workarounds (#570, #614) and recurring bugs.

2. **Inconsistent `max_depth` values cause silent truncation.** Popup code uses
   `max_depth=2`, table code uses 8, everything else uses 20. Shallow depths hide
   elements with no indication to the caller. This caused #570 (buttons invisible),
   #600 (popup fields invisible), and similar issues.

3. **No way for the LLM to know it's missing data.** When the tree is truncated,
   the response doesn't say so. The agent has no signal that deeper elements exist
   and no way to request them.

## Design

### Principle

**Read everything once, show what's needed.** sapsucker captures the complete
tree with all COM properties. The MCP layer decides how much to show the LLM,
always reporting when deeper content exists.

### Part 1: sapsucker — comprehensive ElementInfo

Extend `ElementInfo` with all readable COM properties:

```python
class ElementInfo(BaseModel):
    # Existing (unchanged)
    id: str
    type: str
    type_as_number: int
    name: str
    text: str
    changeable: bool
    children: list[ElementInfo] = []

    # New — all have safe defaults for backward compatibility
    tooltip: str = ""
    default_tooltip: str = ""
    icon_name: str = ""
    modified: bool = False
    acc_text: str = ""
    acc_tooltip: str = ""
    acc_text_on_request: str = ""
    height: int = 0
    width: int = 0
    left: int = 0
    top: int = 0
    screen_left: int = 0
    screen_top: int = 0
    is_symbol_font: bool = False
```

Each new property is read via `_safe_com_attr` on the `child` COM pointer that
`_dump_tree_recursive` already holds — no extra `find_by_id` call needed. This
keeps the overhead low: ~300ms extra on a typical 196-element screen (benchmarked
on SE38), because individual COM property reads cost ~0.11ms each when the COM
pointer is already in hand.

### Part 2: sapsucker — full depth by default

`dump_tree()` walks the full tree with no practical depth limit. The `max_depth`
parameter is kept for backward compatibility but defaults to `None` (unlimited).

```python
def dump_tree(self, max_depth: int | None = None) -> list[ElementInfo]:
```

When `max_depth` is `None`, internally uses `sys.maxsize` as the sentinel to
avoid `TypeError` in the `depth + 1 < max_depth` comparison. A hard safety cap
of 200 levels is enforced regardless of input to prevent infinite recursion from
pathological COM trees (SAP GUI trees never exceed ~15 levels in practice).

`_probe_bdt_fields()` also constructs `ElementInfo` objects and must be updated
to populate the new fields via `_safe_com_attr`.

### Part 3: sapguimcp — smart truncation in MCP tools

The MCP layer handles LLM token concerns. sapsucker does not.

**Tools that gain a `depth` parameter:**
- `sap_com_snapshot(depth=3)`
- `sap_discover_fields(depth=3)`
- `sap_discover_buttons(depth=3)`
- `sap_get_form_fields(depth=3)`

Default depth is 3 (or 4 — to be tuned based on typical screen structure).
`depth` is constrained to `>= 1` via `Field(ge=1)`.

For `sap_com_snapshot`, the `depth` parameter is threaded through to a new
`get_snapshot(depth)` backend method that truncates the full tree before
formatting it as text.

**Truncation logic** (shared helper):

```python
def truncate_tree(
    tree: list[ElementInfo], depth: int
) -> tuple[list[ElementInfo], int, int]:
    """Truncate a full tree to a given depth.

    Returns (truncated_tree, max_depth_found, elements_hidden).
    """
```

- Walks the full tree once
- Computes `max_depth_found` (deepest level in the tree)
- Copies nodes up to `depth`, replacing deeper children with empty lists
- Counts `elements_hidden` (total elements beyond the cutoff)

**Tool results include truncation metadata:**

```python
depth_shown: int       # How deep the response goes
max_depth_found: int   # How deep the tree actually is
elements_hidden: int   # How many elements were cut
```

When `elements_hidden > 0`, the tool description tells the LLM:
"N elements at deeper levels not shown. Call again with depth=M to see all."

### Part 4: sapguimcp — remove all hardcoded max_depth

Remove explicit `max_depth` arguments from all 5 limited call sites:

| File | Current | New |
|------|---------|-----|
| `__init__.py` check_popup | `dump_tree(max_depth=2)` | `dump_tree()` |
| `__init__.py` dismiss_popup | `dump_tree(max_depth=2)` | `dump_tree()` |
| `sap_tools.py` _get_button_tooltips | `dump_tree(max_depth=3)` | `dump_tree()` |
| `se24_edit_tools.py` | `dump_tree(max_depth=8)` | `dump_tree()` |
| `table_helpers.py` | `dump_tree(max_depth=8)` | `dump_tree()` |

The 18 call sites using `dump_tree()` (default) are unchanged — they already
get full depth since the new default is unlimited.

### Part 5: sapguimcp — remove tooltip workaround

The tooltip COM re-fetch in `discover_buttons()` and `check_popup()` (added in
#614) becomes unnecessary — `elem.tooltip` is now available directly from
`ElementInfo`. Remove the workaround and use `elem.tooltip` instead.

### Part 6: sapguimcp — internal code uses full tree

Backend methods that search for elements (`_element_finder.py`, `fill_form`,
`click_button`, `discover_fields`, etc.) always receive the full tree. No
truncation applies to internal operations — only to LLM-facing tool responses.

## Testing strategy

### sapsucker

- Unit test: `ElementInfo` has all new fields with correct defaults
- Unit test: `dump_tree(max_depth=None)` recurses fully (mock COM tree 10 levels)
- Unit test: `dump_tree(max_depth=3)` still works (backward compat)
- Unit test: new properties read via safe getter (COM failure → default value)

### sapguimcp

- Unit test: `truncate_tree()` with various depths, verify counts
- Unit test: `truncate_tree()` with depth=None returns full tree
- Integration test: `sap_discover_fields(depth=1)` returns truncation metadata
- Integration test: `sap_discover_fields(depth=99)` returns full tree
- Integration test: `sap_com_snapshot` includes tooltip in output for toolbar buttons
- Integration test: `check_popup` finds "Weiter (Enter)" via `elem.tooltip` (no COM re-fetch)
- Verify: no hardcoded `max_depth` values remain (grep)

## Files to modify

### sapsucker (`feat/full-element-info` branch)

| File | Change |
|------|--------|
| `sapsucker/models.py` | Extend `ElementInfo` with ~13 new fields |
| `sapsucker/components/base.py` | Read new properties in `_dump_tree_recursive` and `_probe_bdt_fields`, default `max_depth=None` with 200 safety cap |

### sapguimcp (`feat/full-depth-tree` branch)

| File | Change |
|------|--------|
| `backend/desktop/__init__.py` | Remove 2 `max_depth` args, remove tooltip workaround, use `elem.tooltip` |
| `backend/desktop/_element_finder.py` | No change (benefits automatically from richer ElementInfo) |
| `tools/sap_tools.py` | Remove 1 `max_depth` arg, add `depth` param to 4 tools, add truncation metadata |
| `tools/com_tools.py` | Add `depth` param to `sap_com_snapshot` |
| `tools/se24_edit_tools.py` | Remove 1 `max_depth` arg |
| `tools/table_helpers.py` | Remove 1 `max_depth` arg |
| `models/sap_results.py` | Add truncation fields to relevant result classes |
| `backend/desktop/_truncation.py` | New: `truncate_tree()` helper |
| `unittests/desktop/test_truncation_unit.py` | New: unit tests for truncation |

## Out of scope

- WebGUI (uses JavaScript DOM, not COM/dump_tree)
- Changing what `_flatten` does (it correctly preserves all ElementInfo data)
- Token budget estimation (the `depth` parameter is the LLM's tool for managing this)
