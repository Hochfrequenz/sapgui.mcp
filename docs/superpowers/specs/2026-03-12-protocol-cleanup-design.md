# Protocol Cleanup: Make All Tools Backend-Agnostic

## Goal

Eliminate all direct Playwright / `backend._page` access from the tool layer so that
every tool depends only on `SapUiBackend` protocol methods. This is the prerequisite
for adding a second backend (SAP GUI Scripting via COM).

## Context

- **22 of 28 tool files are already clean** (including all edit tools).
- **6 tool files have violations** totalling 31 `backend._page` accesses plus
  ~50 additional direct `page.*` calls.
- **1 violation in `BackendManager`** (`cached._page is page`).
- The protocol already has 33 methods across 5 sub-protocols.

## Approach

**Tool-by-tool cleanup** (simplest first). For each dirty tool:

1. Identify what it needs from the backend that isn't in the protocol.
2. Add missing protocol methods to `protocol.py`.
3. Implement them on `WebGuiBackend`.
4. Rewrite the tool to use only protocol methods.
5. Verify zero `_page` / `playwright` imports remain.

One tool = one PR (or one logical commit group).

## Cleanup Order

| #   | File               | Violations                                          | Difficulty  | Notes                                             |
| --- | ------------------ | --------------------------------------------------- | ----------- | ------------------------------------------------- |
| 1   | `spro_tools.py`    | 1 `_page`                                           | Trivial     | Dialog textbox locator                            |
| 2   | `session_tools.py` | 6 `page.*` via registry bypass                      | Easy        | Gets page from `registry.get_page()`, not backend |
| 3   | `sap_tools.py`     | 3 `_page` + ~48 `page.*` + `get_browser_manager()`  | Medium-Hard | Login, keepalive, new_window, OkCode              |
| 4   | `se16_tools.py`    | 8 `_page` + complex grid JS                         | Hard        | Grid interaction, slow typing                     |
| 5   | `abapgit_tools.py` | 7 `_page` + 2 Playwright imports + iframe traversal | Hard        | DOM scraping, progress monitoring                 |
| 6   | `browser_tools.py` | 10 `_page`                                          | N/A         | **WebGUI-only escape hatch**                      |
| 7   | `BackendManager`   | 1 (`cached._page is page`)                          | Trivial     | Cache identity check                              |

## Decisions

### `browser_tools.py` — WebGUI-only

These are intentional low-level browser access tools. They stay as-is.
A second backend raises `NotImplementedError` for raw browser methods.
No protocol methods needed.

### Protocol sub-protocol split — defer

Keep the current 5 sub-protocols. Don't reorganise boundaries now.
New methods go into whichever sub-protocol fits best.
Reorganisation happens when the second backend forces clarity.

### New protocol methods needed

The exact set will be determined per-tool during implementation. Expected additions:

**Timing / waiting:**

- `wait(timeout_ms: int) -> None` — replaces ~15 `page.wait_for_timeout()` calls

**Page metadata:**

- `get_page_title() -> str` — replaces `page.title()`
- `is_page_closed() -> bool` — for session close logic
- `close_page() -> None` — for session teardown

**DOM queries (for tools that need raw selectors):**

- `query_selector(selector: str) -> bool` — returns whether element exists
- `query_selector_text(selector: str) -> str | None` — get element text
- `click_selector(selector: str) -> None` — click by CSS selector
- `fill_selector(selector: str, value: str) -> None` — fill by CSS selector
- `type_into_selector(selector: str, text: str, delay_ms: int = 0) -> None` — slow type for SE16 grids

**Navigation:**

- `goto(url: str) -> None` — for `browser_navigate` (WebGUI-only, but useful)

**Session management:**

- Protocol-level session list/close instead of direct registry access

These will be refined during implementation — we add only what each tool actually
needs, not speculative methods.

### `sap_tools.py` — three violation vectors

`sap_tools.py` obtains raw Playwright pages via three distinct paths:

1. **`backend._page`** (3 occurrences) — standard violation, replace with protocol methods.
2. **`get_browser_manager()` / `browser_manager.get_current_page()`** — used in keepalive
   loop and login flow. These are session infrastructure, not UI interaction.
3. **`context.pages`** — used in `new_window=True` transaction to register new sessions.

**Cleanup strategy per path:**

- **Login flow** (`sap_login`, line ~562): Push all login DOM logic into
  `WebGuiBackend.login()`. The tool becomes a thin wrapper: validate params,
  call `backend.login(url, user, pass, client, lang)`, return result. The
  protocol already has `login()` on `SapNavigation`.
- **Keepalive** (`_keepalive_loop`, line ~116): Move entirely into the backend
  layer. Keepalive is session infrastructure — the tool should call something
  like `backend.start_keepalive()` / `backend.stop_keepalive()`, or the
  backend manages it internally.
- **New window** (`sap_transaction` with `new_window=True`): Add protocol method
  `open_new_session(tcode: str) -> str` that returns a session ID. The backend
  handles page creation and registry registration internally.
- **`_enable_okcode_field`** (line ~427, 75 lines of DOM manipulation): Move
  into `WebGuiBackend` as an internal method. This is a one-time WebGUI setup
  operation, not tool-level logic.

### `abapgit_tools.py` — iframe and source extraction

The SE38 verification helpers (`_read_source_from_iframes`,
`_read_source_from_main_document`, `_try_direct_se38_selectors`,
`_read_source_via_javascript`) are deeply browser-specific DOM scraping.
These should move into the backend layer. Since `SapEditor.read_editor_source()`
already exists in the protocol, most of these helpers may be partially
redundant and can be replaced by `backend.read_editor_source()` calls
where possible. Remaining abapGit-specific DOM scraping moves into
backend-internal methods.

### `BackendManager._page` identity check

Give each `WebGuiBackend` instance a `session_token: str` property
(e.g., `str(id(page))` assigned at creation). `BackendManager` compares
tokens instead of accessing `_page`. This keeps the protocol clean and
doesn't leak implementation details.

## Out of scope

- Adding the SAP GUI Scripting backend itself.
- Reorganising sub-protocol boundaries.
- Refactoring clean tool files.
- Changing `browser_tools.py` (stays WebGUI-only).

## Success criteria

- `grep -r 'backend\._page' src/sapguimcp/tools/` returns only `browser_tools.py`.
- `grep -r 'from playwright' src/sapguimcp/tools/` returns only `browser_tools.py` (if any).
- `grep -r 'get_browser_manager\|\.registry\.' src/sapguimcp/tools/` returns only `browser_tools.py` (if any).
- `grep -r '_page' src/sapguimcp/backend/manager.py` returns nothing.
- All existing tests pass.
- No new `# type: ignore[attr-defined]` suppressions outside `browser_tools.py`.
