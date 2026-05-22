# Protocol Cleanup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all direct Playwright / `backend._page` access from tool files (except browser_tools.py) so tools depend only on the `SapUiBackend` protocol.

**Architecture:** Tool-by-tool cleanup, simplest first. For each dirty tool: identify missing protocol methods, add them to `protocol.py`, implement on `WebGuiBackend`, rewrite the tool, verify. Each task produces a self-contained commit.

**Tech Stack:** Python 3.12, Playwright, pydantic, pytest, tox (linting + type_check + py312)

**Spec:** `docs/superpowers/specs/2026-03-12-protocol-cleanup-design.md`

---

## Design Notes (deviations from spec)

1. **No `query_selector`, `click_selector`, `fill_selector`, `goto` protocol methods.**
   The spec listed these as expected additions. Instead, we use `evaluate_javascript()`
   as a catch-all for DOM operations that don't map to existing high-level protocol
   methods. This avoids protocol bloat — `evaluate_javascript` is already in the
   protocol and handles all these cases. The only new DOM-level method we add is
   `focus_and_type()` for SE16's slow-typing pattern, which can't be done via JS alone.

2. **Session management methods live on `SapNavigation` (per-session protocol).**
   This is architecturally awkward since `list_sessions()` is a cross-session operation
   called on a single backend instance. Accepted as a pragmatic compromise — the spec
   defers protocol reorganisation. Add a `# TODO: move to a session manager protocol
when adding second backend` comment in the code.

3. **Keepalive moves from module-level globals to per-instance state on WebGuiBackend.**
   This is a semantic improvement: each session gets its own keepalive instead of one
   global keepalive. The tool wrapper in `sap_tools.py` calls `backend.start_keepalive()`
   which naturally scopes to the session.

4. **`BackendTimeoutError`:** When removing `PlaywrightTimeout` imports from
   `abapgit_tools.py`, define `BackendTimeoutError(Exception)` in
   `src/sapguimcp/backend/types.py`. `WebGuiBackend` catches `PlaywrightTimeout`
   and re-raises as `BackendTimeoutError`. Tools catch `BackendTimeoutError`.

---

## Chunk 1: Foundation + Trivial Cleanups

### Task 1: Add `wait` protocol method

The most common violation across all files is `page.wait_for_timeout(ms)`. Adding a single `wait()` method eliminates ~15 violations.

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py` (SapNavigation)
- Modify: `src/sapguimcp/backend/webgui/backend.py` (WebGuiBackend)
- Test: `unittests/test_protocol_methods.py` (create)

- [ ] **Step 1: Add `wait` to SapNavigation protocol**

In `src/sapguimcp/backend/protocol.py`, add to the `SapNavigation` class (after `bring_to_front`):

```python
async def wait(self, timeout_ms: int = 200) -> None:
    """Wait for a fixed duration (e.g. to let popups render)."""
```

- [ ] **Step 2: Implement `wait` on WebGuiBackend**

In `src/sapguimcp/backend/webgui/backend.py`, add:

```python
async def wait(self, timeout_ms: int = 200) -> None:
    """Wait for a fixed duration."""
    await self._page.wait_for_timeout(timeout_ms)
```

- [ ] **Step 3: Verify tox passes**

Run: `tox -e linting,type_check`
Expected: PASS (no callers yet, just the new method)

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py
git commit -m "feat(protocol): add wait() method to SapNavigation"
```

---

### Task 2: Add `get_page_title` protocol method

Used by `session_tools.py`, `sap_tools.py`, and `se16_tools.py` to get the browser tab title.

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py` (SapUiInspection)
- Modify: `src/sapguimcp/backend/webgui/backend.py`

- [ ] **Step 1: Add to protocol**

In `SapUiInspection`, add:

```python
async def get_page_title(self) -> str:
    """Get the current page/window title."""
```

- [ ] **Step 2: Implement on WebGuiBackend**

```python
async def get_page_title(self) -> str:
    """Get the current page title."""
    return await self._page.title()
```

- [ ] **Step 3: Verify tox passes**

Run: `tox -e linting,type_check`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py
git commit -m "feat(protocol): add get_page_title() to SapUiInspection"
```

---

### Task 3: Add `is_page_closed` and `close_page` protocol methods

Needed by `session_tools.py` for session close logic.

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py` (SapNavigation)
- Modify: `src/sapguimcp/backend/webgui/backend.py`

- [ ] **Step 1: Add to protocol**

In `SapNavigation`, add:

```python
async def is_page_closed(self) -> bool:
    """Check whether the underlying page/window has been closed."""

async def close_page(self) -> None:
    """Close the underlying page/window."""
```

- [ ] **Step 2: Implement on WebGuiBackend**

```python
async def is_page_closed(self) -> bool:
    """Check whether the page has been closed."""
    return self._page.is_closed()

async def close_page(self) -> None:
    """Close the page."""
    if not self._page.is_closed():
        await self._page.close()
```

- [ ] **Step 3: Verify tox passes**

Run: `tox -e linting,type_check`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py
git commit -m "feat(protocol): add is_page_closed() and close_page() to SapNavigation"
```

---

### Task 4: Add `session_token` property and fix BackendManager

Replace `cached._page is page` identity check with a session token comparison.

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py` (SapUiBackend — add property)
- Modify: `src/sapguimcp/backend/webgui/backend.py` (assign token in `__init__`)
- Modify: `src/sapguimcp/backend/manager.py` (use token instead of `_page`)

- [ ] **Step 1: Add `session_token` to protocol**

In `SapNavigation` (or directly in `SapUiBackend`), add a property:

```python
@property
def session_token(self) -> str:
    """Opaque token identifying the underlying session. Used for cache invalidation."""
    ...
```

Note: Protocol properties work via `@property` in Python 3.12 Protocols.

- [ ] **Step 2: Implement on WebGuiBackend**

In `WebGuiBackend.__init__`, generate a unique token using a module-level counter
(do NOT use `id(page)` — Python can reuse IDs after GC):

```python
import itertools
_token_counter = itertools.count(1)

class WebGuiBackend:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._session_token = f"webgui-{next(_token_counter)}"
```

Add the property:

```python
@property
def session_token(self) -> str:
    return self._session_token
```

- [ ] **Step 3: Update BackendManager**

In `manager.py`, the manager needs to detect whether the underlying page changed.
Since `get_or_create` receives a `page` from `BrowserManager`, we store a
`page_id` mapping alongside the backend cache:

```python
self._backends: dict[str, SapUiBackend] = {}
self._page_ids: dict[str, int] = {}  # session_key -> id(page) at creation time
```

Change line 50 from:

```python
if cached is not None and cached._page is page:  # pylint: disable=protected-access
```

to:

```python
if cached is not None and self._page_ids.get(session_key) == id(page):
```

And when creating a new backend, store the page id:

```python
backend = WebGuiBackend(page)
self._backends[session_key] = backend
self._page_ids[session_key] = id(page)
```

Update the type hint from `dict[str, WebGuiBackend]` to `dict[str, SapUiBackend]`.

- [ ] **Step 4: Verify tox passes**

Run: `tox -e linting,type_check`

- [ ] **Step 5: Verify success criterion**

Run: `grep -r '_page' src/sapguimcp/backend/manager.py`
Expected: No matches.

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py src/sapguimcp/backend/manager.py
git commit -m "refactor(manager): replace _page identity check with session_token"
```

---

### Task 5: Clean up `spro_tools.py`

Only 1 violation: `backend._page` at line 106 to locate a dialog textbox.

The dialog textbox click can be replaced by `evaluate_javascript` (already in protocol) to click the first textbox inside the dialog.

**Files:**

- Modify: `src/sapguimcp/tools/spro_tools.py:93-122`

- [ ] **Step 1: Replace `_page` access with protocol methods**

Replace the `_fill_search_and_execute` function's page access. The current code:

```python
page = backend._page  # type: ignore[attr-defined]  # pylint: disable=protected-access
search_input = page.locator("[role='dialog'] input[role='textbox']")
try:
    await search_input.click()
except Exception:
    logger.warning("Could not click search input, attempting Tab focus")
    await backend.press_key("Tab")
```

Replace with:

```python
# Focus the search textbox inside the dialog via JavaScript.
try:
    focused = await backend.evaluate_javascript(
        "(() => {"
        "  const input = document.querySelector(\"[role='dialog'] input[role='textbox']\");"
        "  if (input) { input.focus(); input.click(); return true; }"
        "  return false;"
        "})()"
    )
    if not focused:
        logger.warning("Could not find search input, attempting Tab focus")
        await backend.press_key("Tab")
except Exception:  # pylint: disable=broad-exception-caught
    logger.warning("Could not click search input, attempting Tab focus")
    await backend.press_key("Tab")
```

- [ ] **Step 2: Verify no violations remain**

Run: `grep -n '_page\|from playwright' src/sapguimcp/tools/spro_tools.py`
Expected: No matches.

- [ ] **Step 3: Run tests**

Run: `tox -e linting,type_check`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/tools/spro_tools.py
git commit -m "refactor(spro): remove backend._page access, use evaluate_javascript"
```

---

## Chunk 2: session_tools.py Cleanup

### Task 6: Add session management protocol methods

`session_tools.py` bypasses the protocol entirely via `get_browser_manager()` + `registry`. We need protocol methods for session listing, closing, binding, and releasing.

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py` (add new sub-protocol or extend SapNavigation)
- Modify: `src/sapguimcp/backend/webgui/backend.py`

- [ ] **Step 1: Define session management types**

In `src/sapguimcp/models/sap_results.py` (or wherever `SessionInfo` lives), verify the existing types are usable. `SessionInfo`, `SessionListResult`, `SessionCloseResult`, `SessionBindResult`, `SessionReleaseResult` should already exist.

- [ ] **Step 2: Add session methods to protocol**

In `SapNavigation`, add. Use `SessionInfo` from `sapguimcp.models` instead of raw tuples:

```python
async def list_sessions(self) -> list[SessionInfo]:
    """List active sessions with their metadata."""

async def close_session(self, session_id: str) -> bool:
    """Close a session by ID. Returns True if closed, False if not found.

    Gracefully sends /nex to the session before closing the page.
    NOTE: Do NOT add s1 protection here — that is a tool-level policy concern.
    """

async def bind_session(self, session_id: str, agent_id: str) -> str | None:
    """Bind an agent to a session. Returns previous agent_id or None."""

async def release_session(self, session_id: str) -> str | None:
    """Release agent binding from a session. Returns released agent_id or None."""

async def has_session(self, session_id: str) -> bool:
    """Check whether a session exists."""
```

- [ ] **Step 3: Implement on WebGuiBackend**

Implement each method by delegating to the existing `BrowserManager` registry:

```python
async def list_sessions(self) -> list[SessionInfo]:
    from sapguimcp.backend.webgui.browser import get_browser_manager
    manager = await get_browser_manager()
    registry = manager.registry
    result = []
    for sid in registry.list_sessions():
        try:
            page = registry.get_page(sid)
            title = await page.title()
            result.append(SessionInfo(
                session_id=sid,
                title=title,
                is_primary=(sid == "s1"),
                agent_id=registry.get_bound_agent(sid),
            ))
        except (ValueError, Exception):
            continue
    return result

async def close_session(self, session_id: str) -> bool:
    from sapguimcp.backend.webgui.browser import get_browser_manager
    manager = await get_browser_manager()
    registry = manager.registry
    if not registry.has_session(session_id):
        return False
    page = registry.get_page(session_id)
    try:
        ok_field = await page.query_selector("#ToolbarOkCode")
        if ok_field:
            await ok_field.fill("/nex")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)
    except Exception:
        pass
    if not page.is_closed():
        await page.close()
    registry.unregister(session_id)
    return True

async def bind_session(self, session_id: str, agent_id: str) -> str | None:
    from sapguimcp.backend.webgui.browser import get_browser_manager
    manager = await get_browser_manager()
    registry = manager.registry
    old = registry.get_bound_agent(session_id)
    registry.bind(session_id, agent_id)
    return old

async def release_session(self, session_id: str) -> str | None:
    from sapguimcp.backend.webgui.browser import get_browser_manager
    manager = await get_browser_manager()
    registry = manager.registry
    old = registry.get_bound_agent(session_id)
    registry.release(session_id)
    return old

async def has_session(self, session_id: str) -> bool:
    from sapguimcp.backend.webgui.browser import get_browser_manager
    manager = await get_browser_manager()
    return manager.registry.has_session(session_id)
```

- [ ] **Step 4: Verify tox passes**

Run: `tox -e linting,type_check`

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py
git commit -m "feat(protocol): add session management methods to SapNavigation"
```

---

### Task 7: Rewrite `session_tools.py` to use protocol

Replace all `get_browser_manager()` + `registry` access with backend protocol calls.

**Files:**

- Modify: `src/sapguimcp/tools/session_tools.py`

- [ ] **Step 1: Rewrite session_tools.py**

Replace the entire file. Key changes:

- Import `get_backend` instead of `get_browser_manager`
- `sap_session_list_impl()`: call `backend.list_sessions()`, build `SessionInfo` list
- `sap_session_close_impl(session_id)`: call `backend.close_session(session_id)`
- `sap_session_bind_impl(session_id, agent_id)`: call `backend.bind_session()`
- `sap_session_release_impl(session_id)`: call `backend.release_session()`

Each function gets a backend via `await get_backend()` and uses only protocol methods. The `s1` protection check for close stays in the tool.

- [ ] **Step 2: Verify no violations remain**

Run: `grep -n 'get_browser_manager\|registry\.\|_page' src/sapguimcp/tools/session_tools.py`
Expected: No matches.

- [ ] **Step 3: Run tox**

Run: `tox -e linting,type_check`

- [ ] **Step 4: Run unit tests**

Run: `python -m pytest unittests/ -x -q` (the full suite to catch regressions)

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/tools/session_tools.py
git commit -m "refactor(session_tools): use protocol methods instead of direct registry access"
```

---

## Chunk 3: sap_tools.py Cleanup

This is the largest and most complex cleanup. `sap_tools.py` has 3 `backend._page` accesses, ~48 `page.*` calls, and direct `get_browser_manager()` usage. The cleanup strategy from the spec:

1. **Login flow** → push into `WebGuiBackend.login()` (protocol method already exists)
2. **Keepalive** → move into backend layer
3. **New window** → add `open_new_session(tcode)` protocol method
4. **`_enable_okcode_field`** → move into backend as internal method
5. **`_capture_sap_identity`** → move into backend (called after login)
6. **`sap_get_shortcuts`** → use `evaluate_javascript` (already in protocol)
7. **`sap_press_key` wait** → use `wait()` (added in Task 1)
8. **`sap_transaction` wait** → use `wait()` (added in Task 1)

### Task 8: Move login logic into WebGuiBackend

The `sap_login` tool (lines 562-722) is ~160 lines of direct Playwright calls. The protocol already declares `login()` on `SapNavigation`. `WebGuiBackend.login()` already handles most of the login flow (goto, fill, click, already-logged-in dialog). The tool reimplements it plus adds: (a) session registry registration, (b) identity capture, (c) keepalive start, and (d) the "no credentials" validation. Fix: enhance `WebGuiBackend.login()` with (a)-(c), keep (d) in the tool (it depends on `get_settings()`), then make the tool call `backend.login()`.

**Important:** `_find_okcode_field` and `_enable_okcode_field` are moved to the backend in THIS task. Task 10 reuses them (they're already on the backend by then) — do NOT re-move them.

**Files:**

- Modify: `src/sapguimcp/backend/webgui/backend.py` — ensure `login()` implementation handles all cases (already logged in, auto-login, "already logged in" dialog, session registration, identity capture)
- Modify: `src/sapguimcp/tools/sap_tools.py` — replace `sap_login` body with `backend.login()` call

- [ ] **Step 1: Read current `WebGuiBackend.login()` implementation**

Read `src/sapguimcp/backend/webgui/backend.py` and find the existing `login()` method. Understand what it does vs what the tool does.

- [ ] **Step 2: Enhance `WebGuiBackend.login()` to match tool behavior**

Move the login flow from `sap_tools.py` lines 598-718 into `WebGuiBackend.login()`. This includes:

- `page.goto(url)` + `wait_for_load_state`
- Check if already logged in (find OkCode field)
- Fill login form (client, user, password, language)
- Click login button
- Handle "already logged in" dialog
- Register in session registry
- Capture SAP identity

The `_enable_okcode_field` helper and all SELECTORS/helpers that it calls should also move to the backend as private methods.

- [ ] **Step 3: Simplify `sap_login` tool to thin wrapper**

The tool becomes:

```python
async def sap_login(url: Optional[str] = None, ctx: Context | None = None) -> LoginResult:
    settings = get_settings()
    effective_url = url or settings.sap_url
    if not effective_url:
        return LoginResult.failure("No SAP URL provided...")

    session_id = getattr(ctx, "session_id", None) if ctx else None
    backend = await get_backend(tool_name="sap_login")
    return await backend.login(
        url=effective_url,
        username=settings.sap_user,
        password=settings.sap_password,
        client=settings.sap_mandant,
        language=settings.sap_language,
    )
```

Note: The `_start_keepalive()` call currently in the tool should also move into `WebGuiBackend.login()` or be triggered by the tool after login succeeds.

- [ ] **Step 4: Move helper functions to backend**

Move these from `sap_tools.py` to `src/sapguimcp/backend/webgui/backend.py` (as private methods or standalone helpers in the webgui package):

- `_find_okcode_field(page)` → `WebGuiBackend._find_okcode_field()`
- `_enable_okcode_field(page)` → `WebGuiBackend._enable_okcode_field()`
- `_try_find_checkbox_by_label(page)` → same
- `_try_find_checkbox_in_tabs(page, steps)` → same
- `_close_settings_dialog(page)` → same
- `_capture_sap_identity(page, ...)` → `WebGuiBackend._capture_sap_identity()`
- `SELECTORS` dict → move to backend

- [ ] **Step 5: Verify no login-related `page.*` calls remain in sap_tools.py**

Run: `grep -n 'page\.\|_find_okcode\|_enable_okcode\|_capture_sap' src/sapguimcp/tools/sap_tools.py`
Check that login-related hits are gone. Some `page.*` calls in `sap_transaction` may still exist (handled in next task).

- [ ] **Step 6: Run tox**

Run: `tox -e linting,type_check`

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest unittests/ -x -q`

- [ ] **Step 8: Commit**

```bash
git add src/sapguimcp/backend/webgui/backend.py src/sapguimcp/tools/sap_tools.py
git commit -m "refactor(login): move login flow from sap_tools into WebGuiBackend"
```

---

### Task 9: Move keepalive into backend layer

Keepalive (`_keepalive_loop`, `_start_keepalive`, `sap_keepalive_stop`) uses `get_browser_manager()` + `browser_manager.get_current_page()`. Move the keepalive loop into the backend.

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py` — add `start_keepalive()` / `stop_keepalive()`
- Modify: `src/sapguimcp/backend/webgui/backend.py` — implement keepalive
- Modify: `src/sapguimcp/tools/sap_tools.py` — simplify tools to call protocol

- [ ] **Step 1: Add keepalive methods to protocol**

In `SapNavigation`:

```python
async def start_keepalive(self, interval_seconds: int = 300) -> None:
    """Start a background keepalive ping to prevent session timeout."""

async def stop_keepalive(self) -> bool:
    """Stop the keepalive task. Returns True if a task was running."""
```

- [ ] **Step 2: Move keepalive implementation to WebGuiBackend**

Move `_keepalive_loop` and state (`_keepalive_task`, `_keepalive_interval`) from `sap_tools.py` into `WebGuiBackend`. The loop uses `self._page` internally (which is fine — it's inside the backend).

- [ ] **Step 3: Simplify tool wrappers**

`sap_keepalive_start` → `backend.start_keepalive(interval_seconds)`
`sap_keepalive_stop` → `backend.stop_keepalive()`

Remove `_keepalive_loop`, `_start_keepalive`, `_keepalive_task`, `_keepalive_interval` globals from `sap_tools.py`.

- [ ] **Step 4: Run tox + tests**

Run: `tox -e linting,type_check && python -m pytest unittests/ -x -q`

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py src/sapguimcp/tools/sap_tools.py
git commit -m "refactor(keepalive): move keepalive loop from sap_tools into WebGuiBackend"
```

---

### Task 10: Add `open_new_session` and clean up `sap_transaction`

The `new_window=True` path in `sap_transaction` (lines 832-917) uses `page.context`, `_register_new_window_session`, `_find_okcode_field`, `page.evaluate`, `page.keyboard`, etc. Add a protocol method for opening a new session.

**Files:**

- Modify: `src/sapguimcp/backend/protocol.py`
- Modify: `src/sapguimcp/backend/webgui/backend.py`
- Modify: `src/sapguimcp/tools/sap_tools.py`

- [ ] **Step 1: Add `open_new_session` to protocol**

In `SapNavigation`:

```python
async def open_new_session(self, tcode: str) -> tuple[str | None, int, str | None]:
    """Open a transaction in a new SAP session window (/o prefix).

    Returns (session_id, session_count, page_title).
    session_id is None if no new session was created.
    """
```

- [ ] **Step 2: Implement on WebGuiBackend**

Move the `new_window=True` logic from `sap_transaction` into `WebGuiBackend.open_new_session()`. This includes:

- Find/enable OkCode field
- Build `/o` prefixed tcode
- Track page count, enter tcode, wait
- Register new session via `_register_new_window_session` (move helper to backend)

- [ ] **Step 3: Clean up remaining `sap_tools.py` violations**

After login, keepalive, and new_window are moved:

- `sap_press_key` line 1045: `page.wait_for_timeout(300)` → `await backend.wait(300)`
- `sap_transaction` line 796+819: replace `backend._page` with `backend.wait(200)`
- `sap_get_shortcuts` line 1538: `page.evaluate(...)` → `backend.evaluate_javascript(...)`

Remove all remaining `backend._page` access and `get_browser_manager()` imports.

Move `_wait_for_new_page`, `_register_new_window_session` helpers to backend.

Remove `SELECTORS` dict from sap_tools (already moved to backend in Task 8).

Note: `page.wait_for_load_state("networkidle")` in the new_window flow should map to
`backend.wait_for_ready()`. Verify that `wait_for_ready()` implementation uses
`networkidle` (or equivalent). If not, the backend implementation may need updating.

- [ ] **Step 4: Verify no violations remain**

Run: `grep -n 'backend\._page\|get_browser_manager\|from playwright' src/sapguimcp/tools/sap_tools.py`
Expected: No matches.

- [ ] **Step 5: Run tox + tests**

Run: `tox -e linting,type_check && python -m pytest unittests/ -x -q`

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py src/sapguimcp/tools/sap_tools.py
git commit -m "refactor(sap_tools): eliminate all _page access, use protocol methods"
```

---

## Chunk 4: se16_tools.py Cleanup

### Task 11: Clean up `se16_tools.py`

8 `backend._page` accesses for complex grid interactions: typing into fields, evaluating JS for grid cells, waiting for grids, slow-typing with delay.

Most violations can be replaced with:

- `backend.evaluate_javascript()` — already in protocol (handles grid JS)
- `backend.wait()` — added in Task 1
- `backend.type_text()` — already in protocol
- `backend.press_key()` — already in protocol
- `backend.get_page_title()` — added in Task 2
- `backend.fill_field()` — already in protocol

For `press_sequentially` (slow typing with delay), either:
a) Use `evaluate_javascript` to set the value + dispatch events, or
b) Add a `type_into_focused(text, delay_ms)` protocol method if needed.

**Files:**

- Modify: `src/sapguimcp/tools/se16_tools.py`
- Possibly modify: `src/sapguimcp/backend/protocol.py` (if new methods needed)
- Possibly modify: `src/sapguimcp/backend/webgui/backend.py`

- [ ] **Step 1: Audit each violation and determine replacement**

Read each `backend._page` usage in se16_tools.py. For each one, determine which existing or new protocol method replaces it.

- [ ] **Step 2: Add any new protocol methods needed**

Likely candidates:

- `focus_and_type(selector: str, text: str, delay_ms: int = 0) -> None` for slow typing into specific elements (used in `_try_type_with_delay` and `_fill_filter_element`)

- [ ] **Step 3: Replace all 8 `_page` accesses**

Rewrite each helper function to use protocol methods. The JS evaluation calls can use `backend.evaluate_javascript()` directly since it's already in the protocol.

- [ ] **Step 4: Verify no violations remain**

Run: `grep -n 'backend\._page\|from playwright' src/sapguimcp/tools/se16_tools.py`
Expected: No matches.

- [ ] **Step 5: Run tox + tests**

Run: `tox -e linting,type_check && python -m pytest unittests/ -x -q`

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/tools/se16_tools.py src/sapguimcp/backend/protocol.py src/sapguimcp/backend/webgui/backend.py
git commit -m "refactor(se16_tools): eliminate all _page access, use protocol methods"
```

---

## Chunk 5: abapgit_tools.py Cleanup

### Task 12: Clean up `abapgit_tools.py`

7 `_page` accesses + 2 Playwright imports. Violations cluster in:

- Progress monitoring (`_pull_and_monitor_progress`, `_monitor_pull_progress`)
- Source extraction (`_extract_source_from_se38`, `_find_git_source_code`)
- Result parsing (`_parse_repo_pull`)
- Error detection (`_detect_pull_error_from_output`)
- Result analysis (`_analyze_pull_result`)

Strategy: Most source extraction helpers are redundant with `backend.read_editor_source()`. Progress monitoring and DOM scraping should move into the backend as abapGit-specific internal methods.

**Files:**

- Modify: `src/sapguimcp/tools/abapgit_tools.py`
- Modify: `src/sapguimcp/backend/webgui/backend.py` (add abapGit-specific internals)
- Possibly modify: `src/sapguimcp/backend/protocol.py`

- [ ] **Step 1: Audit each violation and determine replacement**

Read each helper function to understand what Playwright APIs it uses and whether existing protocol methods suffice.

- [ ] **Step 2: Move DOM-scraping helpers to backend**

Functions like `_extract_source_from_se38`, `_find_git_source_code`, `_read_source_from_iframes`, etc. are deeply browser-specific. Move them into `WebGuiBackend` as private methods. Expose them through a small number of protocol methods if tools need them, or make them backend-internal if they're only used as part of larger protocol operations.

- [ ] **Step 3: Replace progress monitoring with protocol methods**

`_pull_and_monitor_progress` and `_monitor_pull_progress` use `page.wait_for_timeout()` and `page.wait_for_load_state()`. Replace with `backend.wait()` and `backend.wait_for_ready()`.

- [ ] **Step 4: Remove Playwright imports and add BackendTimeoutError**

Remove `from playwright.async_api import TimeoutError as PlaywrightTimeout` and the `TYPE_CHECKING` import of `Page`.

Define `BackendTimeoutError(Exception)` in `src/sapguimcp/backend/types.py`.
In `WebGuiBackend`, catch `PlaywrightTimeout` and re-raise as `BackendTimeoutError`.
In `abapgit_tools.py`, catch `BackendTimeoutError` instead of `PlaywrightTimeout`.

- [ ] **Step 5: Verify no violations remain**

Run: `grep -n 'backend\._page\|from playwright\|import playwright' src/sapguimcp/tools/abapgit_tools.py`
Expected: No matches.

- [ ] **Step 6: Run tox + tests**

Run: `tox -e linting,type_check && python -m pytest unittests/ -x -q`

- [ ] **Step 7: Commit**

```bash
git add src/sapguimcp/tools/abapgit_tools.py src/sapguimcp/backend/webgui/backend.py src/sapguimcp/backend/protocol.py
git commit -m "refactor(abapgit_tools): eliminate all _page access and Playwright imports"
```

---

## Chunk 6: Final Verification

### Task 13: Run full success criteria checks

**Files:** None (verification only)

- [ ] **Step 1: Check no `_page` in tools (except browser_tools)**

```bash
grep -rn 'backend\._page' src/sapguimcp/tools/ | grep -v browser_tools.py
```

Expected: No matches.

- [ ] **Step 2: Check no Playwright imports in tools (except browser_tools)**

```bash
grep -rn 'from playwright' src/sapguimcp/tools/ | grep -v browser_tools.py
```

Expected: No matches.

- [ ] **Step 3: Check no direct registry/browser_manager access in tools (except browser_tools)**

```bash
grep -rn 'get_browser_manager\|\.registry\.' src/sapguimcp/tools/ | grep -v browser_tools.py
```

Expected: No matches.

- [ ] **Step 4: Check BackendManager is clean**

```bash
grep -rn '_page' src/sapguimcp/backend/manager.py
```

Expected: No matches.

- [ ] **Step 5: Check no type:ignore[attr-defined] in tools (except browser_tools)**

```bash
grep -rn 'type: ignore\[attr-defined\]' src/sapguimcp/tools/ | grep -v browser_tools.py
```

Expected: No matches.

- [ ] **Step 6: Run full tox**

Run: `tox`
Expected: All environments pass.

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest unittests/ -x -q`
Expected: All tests pass (except known flaky abapgit e2e if it involves live SAP).

- [ ] **Step 8: Commit any final fixups, then report complete**
