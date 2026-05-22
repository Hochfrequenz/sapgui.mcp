# Backend Encapsulation & Test Reorganization

## Goal

Encapsulate WebGUI-specific code (JS files, ARIA parsers) inside `backend/webgui/` so a second backend (`backend/desktop/` for SAP GUI Scripting via COM) can be built alongside it with a mirror structure. Reorganize tests into backend-agnostic and webgui-specific groups.

## Architecture

One MCP session uses exactly one backend. The backend type is a startup config choice. Tools depend on the `SapUiBackend` protocol for interaction and import backend-specific parsers for structured output. Models are shared — both backends return the same result types.

The LLM client either:

- Calls a raw snapshot tool (`sap_get_snapshot`) and interprets the result itself
- Calls a structured tool (`sap_se09_lookup`) which internally navigates, snapshots, parses, and returns structured data

Parsers are internal to each backend. They are not exposed to the LLM as tools.

## Package Structure

### Current

```
src/sapguimcp/
  backend/
    protocol.py          # SapUiBackend protocol
    manager.py           # get_backend() entry point
    types.py             # AriaSnapshot type alias
    webgui/
      backend.py         # WebGuiBackend
      browser.py         # Playwright/CDP
      js_helpers.py      # load_js() — uses resources.files("sapguimcp.js")
  js/                    # ← WebGUI-specific, top level (loaded via resources.files)
  parsers/               # ← ARIA-specific, top level
  tools/                 # shared MCP tools
  models/                # shared result models
  lang.py                # shared DE/EN constants
  server.py              # MCP server entry point
  logging_config.py      # logging setup
  utils.py               # shared utilities
  middleware/             # MCP middleware
  loghandlers/            # log handlers
  catalog/               # table catalog
  classcatalog/          # class catalog
  fmcatalog/             # function module catalog
  data/                  # static data
  resources/             # resource files
  prompts/               # LLM prompts
  skills/                # LLM skills
  tables/                # table definitions
  workflows/             # workflow definitions
```

### Proposed

Only `js/` and `parsers/` move. Everything else stays where it is.

```
src/sapguimcp/
  backend/
    protocol.py          # SapUiBackend protocol (unchanged)
    manager.py           # picks backend from config
    types.py             # shared type aliases
    webgui/
      backend.py         # WebGuiBackend
      browser.py         # Playwright/CDP
      js_helpers.py      # load_js() — updated to resources.files("sapguimcp.backend.webgui.js")
      js/                # ← moved from src/sapguimcp/js/
      parsers/           # ← moved from src/sapguimcp/parsers/
  tools/                 # shared MCP tools (import paths updated)
  models/                # shared result models (unchanged)
  lang.py                # shared (unchanged)
  # everything else unchanged
```

A future desktop backend mirrors the webgui structure:

```
    desktop/
      backend.py         # DesktopBackend (implements SapUiBackend)
      com.py             # SAP GUI Scripting COM helpers
      parsers/           # COM-tree-specific parsers
```

Both `webgui/parsers/` and `desktop/parsers/` return the same shared model types from `models/`.

## Import Boundary Rules

**Internal** (never imported from outside `backend/webgui/`):

- `backend/webgui/browser.py` — Playwright/CDP session management
- `backend/webgui/js/` — JavaScript files
- `backend/webgui/js_helpers.py` — JS loading utilities

**Backend-specific but importable by tools**:

- `backend/webgui/parsers/` — ARIA-format parsers. Tools import these to parse snapshots into structured data. This is an accepted boundary crossing: parsers are backend-specific but tools need them to return structured results.

**Shared** (imported by everyone):

- `backend/protocol` — `SapUiBackend` type
- `backend/manager` — `get_backend()` entry point
- `models/` — result types
- `lang.py` — DE/EN string constants

**Existing violations to fix:**

- `tools/se16_tools.py` imports `load_js` from `backend.webgui.js_helpers` — must be refactored so the JS loading stays internal to the backend
- `tools/browser_tools.py` imports `_escape_css_selector` from `backend.webgui.backend` — must be moved to a shared utility or into the protocol

These are small logic fixes, not just import path updates.

**When `backend/desktop/` arrives**, tools that parse will gain equivalent desktop parser imports.

## Test Reorganization

### Current

~70 test files flat in `unittests/`, mixing parser unit tests, model tests, WebGUI integration tests, and exploration tests.

### Proposed

```
unittests/
  conftest.py                    # shared fixtures
  # Backend-agnostic tests (shared models, config, utilities)
  test_aria_snapshot_type.py
  test_backend_manager.py
  test_backend_protocol.py
  test_catalog.py
  test_classcatalog.py
  test_config.py
  test_date_helpers.py
  test_fmcatalog.py
  test_feedback_issue_handler.py
  test_logging_config.py
  test_middleware_models.py
  test_models.py
  test_pat_validation.py
  test_prompts.py
  test_server.py
  test_session_registry.py
  test_session_tools.py
  test_tables.py
  test_tool_call_logging_middleware.py

  webgui/                        # everything WebGUI-specific
    conftest.py                  # WebGUI fixtures (sap_mcp_client, etc.)
    abapgit_test_helpers.py      # abapgit test helpers
    abapgit_repos/               # abapgit test fixture repos
    explore_se16.py              # SE16 exploration script
    smoke_test_exe.py            # smoke test for packaged exe

    # Backend unit tests
    test_webgui_backend.py
    test_selectors.py
    test_server_cdp_check.py
    test_abapgit_tools.py

    # Parser unit tests (ARIA format, no SAP connection needed)
    test_screen_state_parser.py
    test_se09_parser.py
    test_se11_parser.py
    test_se16_parser.py
    test_se24_parser.py
    test_se37_parser.py
    test_se93_parser.py
    test_shortcut_parser.py
    test_slg1_parser.py
    test_sm30_parser.py
    test_sm37_parser.py
    test_spro_parser.py
    test_st22_parser.py

    # Screen state / checkbox / ensure_screen_state tests
    test_checkbox_radio_integration.py
    test_ensure_screen_state.py

    # Edit tool tests (WebGUI-specific round-trip)
    test_se24_edit.py
    test_se37_edit.py
    test_se38_edit.py

    # Integration tests (one file per tcode/scope, need live SAP WebGUI)
    # Split from test_sap_integration.py + existing per-tcode files
    test_login_integration.py
    test_popup_integration.py
    test_shortcuts_integration.py
    test_session_integration.py
    test_session_sap_integration.py
    test_agent_binding_integration.py
    test_sap_login_identity.py
    test_abapgit_integration.py
    test_se09_integration.py
    test_se11_integration.py
    test_se16_integration.py
    test_se24_integration.py
    test_se37_integration.py
    test_se38_integration.py       # split from test_sap_integration.py
    test_se93_integration.py
    test_sm30_integration.py
    test_sm37_integration.py
    test_slg1_integration.py
    test_spro_integration.py
    test_st22_integration.py

    # Exploration tests (capture snapshots from live SAP)
    test_se09_exploration.py
    test_se24_edit_exploration.py
    test_se37_edit_exploration.py
    test_se38_edit_exploration.py
    test_slg1_exploration.py
    test_sm30_exploration.py
    test_sm37_exploration.py
    test_spro_exploration.py
    test_st22_exploration.py

    testdata/                    # YAML/HTML snapshots
      html_snapshots/
      yaml_snapshots/
      se09_exploration/
      ...
```

### Split criterion

**Does it need ARIA snapshots, WebGUI infrastructure, or a live SAP WebGUI connection?**

- Yes → `unittests/webgui/`
- No (shared models, config, utilities, catalogs) → `unittests/` top level

### Splitting `test_sap_integration.py`

The monolith `test_sap_integration.py` (~3500 lines) is split by tcode/scope:

- Login/session tests → `test_login_integration.py`
- Popup handling → `test_popup_integration.py`
- Keyboard shortcuts → `test_shortcuts_integration.py`
- SE11 tests → `test_se11_integration.py`
- SE16 tests → `test_se16_integration.py`
- SE24 tests → `test_se24_integration.py`
- SE37 tests → `test_se37_integration.py`
- SE38 tests → `test_se38_integration.py`
- SE09 tests → already in `test_se09_integration.py`
- Etc.

Some per-tcode integration test files already exist (e.g., `test_se09_integration.py`). Those just move into `webgui/`.

## Scope

This is a **structural refactor** with two small logic fixes for import boundary violations. All tests produce the same results from different paths. The changes are:

1. Move `src/sapguimcp/js/` → `src/sapguimcp/backend/webgui/js/`
2. Move `src/sapguimcp/parsers/` → `src/sapguimcp/backend/webgui/parsers/`
3. Update `js_helpers.py` to use `resources.files("sapguimcp.backend.webgui.js")` instead of `resources.files("sapguimcp.js")`
4. Update `pyproject.toml` package-data paths for the moved JS files
5. Update all parser imports in tools (e.g., `from sapguimcp.parsers.X` → `from sapguimcp.backend.webgui.parsers.X`)
6. Fix `se16_tools.py` `load_js` import violation (move JS loading into backend)
7. Fix `browser_tools.py` `_escape_css_selector` import violation (move to shared utility)
8. Split `test_sap_integration.py` into per-tcode files
9. Move WebGUI-specific tests into `unittests/webgui/`
10. Move `testdata/` into `unittests/webgui/testdata/`
11. Update test import paths and conftest fixtures

## What stays unchanged

- `backend/protocol.py` — the shared `SapUiBackend` protocol
- `backend/manager.py` — gains desktop support later, no change now
- `tools/` — stay at top level, only import paths change
- `models/` — shared, untouched
- `lang.py` — shared, untouched
- All other packages (`catalog/`, `middleware/`, `prompts/`, `skills/`, etc.) — untouched
