# pysapgui Open-Source Readiness — Gap Analysis & Plan

## Goal

Prepare the `sapgui/` subpackage for open-source release as an independent PyPI library. All work happens in the current repo first; repo extraction and packaging is the final step.

## Current State

The library is already architecturally decoupled from the MCP server — zero imports from `sapguimcp` outside of `sapgui/` itself, zero references to MCP concepts. It wraps 40+ SAP GUI Scripting element types with typed Python classes, has a two-level factory dispatch, login/logoff helpers, and 15 mock-based test files.

**No competing library provides typed element wrappers.** The closest alternatives (`pysapscript`, `robotframework-sapguilibrary`) use string-based generic `read()`/`write()` or Robot Framework keywords. This library's typed approach with IDE autocomplete is a genuine differentiator.

## Competitive Landscape

| Library | Stars | Active | Typed Wrappers | License |
|---|---|---|---|---|
| pysapscript | 11 | Yes (GPL-3) | No | GPL-3 |
| PySapGUI (gutskodv) | 25 | Dead (2020) | No | GPL-2 |
| sapguipy | — | Yes (MIT) | No | MIT |
| RF SapGuiLibrary | 52 | Stale (2022) | No | Apache-2 |
| **pysapgui (ours)** | — | Yes | **Yes — 40+ classes** | TBD |

## Work Phases — Issue Tracker

All work ordered so that extraction to a separate repo is the very last step.
Issues declare their dependencies so execution order is visible from the tickets alone.

### Phase 1: API Completeness (feature gaps) — all independent, can be parallelized

| Issue | Title | Depends On |
|---|---|---|
| #473 | GuiGridView: fill missing methods | — |
| #474 | GuiTree: fill missing methods | — |
| #475 | GuiTextedit/GuiAbapEditor: fill missing methods | — |
| #476 | GuiTableControl: fill missing methods | — |
| #477 | GuiContextMenu: add wrapper (type 127) | — |
| #478 | GuiScrollbar: add wrapper (type 100) | — |

### Phase 2: Design Improvements — mostly independent

| Issue | Title | Depends On |
|---|---|---|
| #479 | Extract `_login.py` to login submodule | — |
| #480 | Add context manager protocol to GuiApplication | — |
| #481 | Log non-COM exceptions in `_safe_com_attr()` | — |
| ~~#482~~ | ~~Replace Pydantic with dataclasses~~ | **CLOSED — keeping Pydantic** |
| #483 | Add `__all__` to all component modules | — |
| #484 | Document thread safety / COM apartment rules | — |
| #499 | Fix `-> Any` return types for typed DX | — |
| #500 | Packaging polish (py.typed, __version__, CHANGELOG) | #492 |

### Phase 3: Documentation — depends on Phase 1+2

| Issue | Title | Depends On |
|---|---|---|
| #485 | Write README with quickstart, installation, examples | #473–#478 |
| #486 | Docstring audit for all public classes/methods | #473–#478 |
| #487 | Create examples directory | #473–#478, #485 |
| #497 | Add doctests to public API methods | #473–#478, #486 |
| #498 | Set up documentation site (RTD or GitHub Pages) | #486, #497, #492 |

### Phase 4: Testing — depends on Phase 1

| Issue | Title | Depends On |
|---|---|---|
| #488 | Unit test completeness audit | #473–#478 |
| #489 | Integration test infrastructure | #488 |
| #490 | CI pipeline (lint, type-check, tests) | #488, #489 |

### Phase 5: Extraction & Packaging — last step

| Issue | Title | Depends On |
|---|---|---|
| #491 | Rename imports `sapguimcp.sapgui` → `pysapgui` | All Phase 1–4 |
| #492 | Create standalone pyproject.toml and extract to own repo | #491, #485, #490 |

## Dependency Graph

```
Phase 1 (parallel):  #473  #474  #475  #476  #477  #478
                       │     │     │     │     │     │
Phase 2 (parallel):  #479  #480  #481  #483  #484

Phase 3:              #485 ◄── Phase 1
                       │       #486 ◄── Phase 1
                       ▼       #487 ◄── Phase 1 + #485
                      #497 ◄── Phase 1 + #486
                       │
Phase 4:              #488 ◄── Phase 1
                       │
                      #489 ◄── #488
                       │
                      #490 ◄── #488, #489
                       │
Phase 5:              #491 ◄── All Phase 1–4
                       │
                      #492 ◄── #491, #485, #490
                       │
                      #498 ◄── #486, #497, #492
```

Note: #482 (Pydantic → dataclasses) is CANCELLED — Pydantic stays.

## Phase Details

### Phase 1: API Completeness

**1.1 GuiGridView gaps (#473)** _(PDF-verified 2026-03-22)_
- `get_cell_color()`, `get_cell_icon()`, `get_cell_state()` ~~`get_display_cell_value()`~~ (not in API 6.40)
- `modify_cell()` (alias for set_cell_value — SAP spec uses both names)
- `get_displayed_column_title()` ~~`get_column_title_by_name()`~~ (not in API), `get_column_tooltip()`, `get_column_data_type()`
- `is_cell_hotspot()`, `get_cell_tooltip()`

**1.2 GuiTree gaps (#474)** _(PDF-verified 2026-03-22)_
- `change_checkbox()`, `get_checkbox_state()` — tree checkbox support
- `get_item_type()` ~~`get_node_item_type()`~~ (COM: GetItemType, not GetNodeItemType), `get_item_tooltip()` (COM: GetItemToolTip, capital T)
- `get_node_style()`, `is_folder()`
- ~~`is_changeable()`~~ (already inherited as `changeable` property from base)
- ~~`get_list_tree_item_text()`, `get_column_tree_item_text()`~~ (not in API; `get_item_text()` already covers all tree types)

**1.3 GuiTextedit / GuiAbapEditor gaps (#475)** _(PDF-verified 2026-03-22)_
- `set_unprotected_text_part()` (returns bool, not void), `get_unprotected_text_part()`
- `is_read_only` property (GuiTextedit has it, verify GuiAbapEditor — note: GuiAbapEditor not in PDF 6.40)
- `first_visible_line` (r/w), `last_visible_line` (read-only — not in PDF 6.40, likely newer API)

**1.4 GuiTableControl gaps (#476)** _(PDF-verified 2026-03-22 — no errors)_
- `get_absolute_row()` — for scrolled tables (raises if row not visible)
- `columns` property should return typed `GuiTableColumn` collection
- `rows` property should return typed `GuiTableRow` collection

**1.5 GuiContextMenu (type 127) (#477)** _(PDF-verified 2026-03-22)_
- New class extending **`GuiMenu`** ~~`GuiVContainer`~~ — inherits `select()` from GuiMenu
- Register in factory + types

**1.6 GuiScrollbar (type 100) (#478)** _(PDF-verified 2026-03-22 — no errors)_
- Properties: `minimum`, `maximum`, `position` (r/w), `page_size`
- Update `GuiUserArea` to return typed scrollbars

### Phase 2: Design Improvements

**2.1 Extract `_login.py` to login submodule (#479)**
- Make it `from pysapgui.login import login, logoff`
- Core API remains separate from login convenience

**2.2 Context manager protocol (#480)**
- `with SapGui.connect() as app:` for automatic cleanup

**2.3 Log non-COM exceptions in `_safe_com_attr()` (#481)**
- Keep broad `Exception` catch as safety net (COM errors are not always `pywintypes.com_error`)
- Add warning log for non-COM exceptions so real bugs are visible in logs

**~~2.4 Replace Pydantic with dataclasses (#482)~~ — CANCELLED**
- Keeping Pydantic — better usability (`.model_dump()`, validation, JSON serialization)

**2.5 Add `__all__` (#483)**
- Every public module declares exports

**2.6 Thread safety docs (#484)**
- Document COM apartment threading rules

### Phase 3: Documentation

**3.1 README (#485)** — quickstart, installation, comparison, architecture
**3.2 Docstring audit (#486)** — 100% coverage on public API
**3.3 Examples (#487)** — 4 runnable example scripts
**3.4 Doctests (#497)** — at least 10 doctest examples across key methods
**3.5 Documentation site (#498)** — auto-generated API docs (pdoc + GitHub Pages or RTD)

### Phase 4: Testing

**4.1 Unit test completeness (#488)** — every public method tested
**4.2 Integration test infra (#489)** — pytest markers, skip logic
**4.3 CI pipeline (#490)** — GitHub Actions for the standalone repo

### Phase 5: Extraction & Packaging

**5.1 Rename imports (#491)** — `sapguimcp.sapgui` → `pysapgui`
**5.2 Extract to own repo (#492)** — pyproject.toml, license, PyPI release, update sapgui.mcp

## Out of Scope

- Event handling (SAP GUI events) — can be added post-release
- Recording support — niche feature
- Async API — COM is inherently synchronous, async belongs in the consumer layer
- Cross-platform — COM is Windows-only, that's fundamental
- Deferred shell types (GuiBarChart, GuiChart, etc.) — recording-only controls, generic GuiShell fallback is fine
