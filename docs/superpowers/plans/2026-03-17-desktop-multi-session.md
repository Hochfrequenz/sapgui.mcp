# Desktop Multi-Session Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable parallel agents on the desktop backend by routing COM calls to the correct SAP GUI session via a DesktopSessionRegistry + ContextVar.

**Architecture:** New `DesktopSessionRegistry` mirrors WebGUI's `SessionRegistry`. A `ContextVar` set by `BackendManager` before each tool call tells `_require_session()` which `GuiSession` to return. Single `DesktopBackend` instance shared across all sessions; `ComThread` serializes COM calls.

**Tech Stack:** Python asyncio, contextvars, pysapgui COM wrappers, pytest + live SAP integration tests.

**Spec:** `docs/superpowers/specs/2026-03-17-desktop-multi-session-design.md`

---

## Task 1: DesktopSessionRegistry — unit tests + implementation

**Files:**
- Create: `src/sapguimcp/backend/desktop/_session_registry.py`
- Create: `unittests/test_desktop_session_registry.py`

- [ ] **Step 1.1: Write failing tests for the registry**

Create `unittests/test_desktop_session_registry.py` with tests covering:
- `TestRegister`: first=s1, second=s2, counter increments to s5
- `TestGetSession`: returns correct session, None defaults to s1, unknown raises ValueError, empty registry + None raises ValueError, stale session auto-unregisters (monkeypatch `_last_probe` to bypass TTL)
- `TestTTLCache`: session probed on first access, NOT probed within TTL window even if COM would fail, probed again after TTL expires
- `TestUnregister`: removes session, clears binding, unregister s1 while s2 exists
- `TestBinding`: bind+get, release, check_binding warns on mismatch (use caplog), no warning when matching
- `TestListAndHas`: list_sessions, has_session

Key: the stale session test MUST set `reg._last_probe["s1"] = 0` to force the probe past the TTL cache. Without this, the test passes without actually exercising the stale path.

- [ ] **Step 1.2: Run tests — verify they fail (ImportError)**

Run: `python -m pytest unittests/test_desktop_session_registry.py -x -q --tb=short`
Expected: FAIL with `ImportError: cannot import name 'DesktopSessionRegistry'`

- [ ] **Step 1.3: Implement DesktopSessionRegistry**

Create `src/sapguimcp/backend/desktop/_session_registry.py` with:
- `_PROBE_TTL_SECONDS = 5.0` constant
- `register(session) → str`: increments counter, stores session, sets probe timestamp
- `get_session(session_id | None) → GuiSession`: None→"s1", probes COM with TTL, auto-unregisters on failure
- `unregister(session_id)`: removes from all dicts
- `bind/release/check_binding/get_bound_agent`: agent binding (warn-only check)
- `list_sessions/has_session`: simple dict lookups

- [ ] **Step 1.4: Run tests — verify all pass**

Run: `python -m pytest unittests/test_desktop_session_registry.py -x -q --tb=short`
Expected: All tests PASS (target: ~18 tests)

- [ ] **Step 1.5: isort + black + linting**

- [ ] **Step 1.6: Commit**

---

## Task 2: Wire registry into DesktopBackend + ContextVar routing

**Files:**
- Modify: `src/sapguimcp/backend/desktop/__init__.py`
- Modify: `src/sapguimcp/backend/manager.py`
- Create: `unittests/test_contextvar_routing.py` (unit test for ContextVar + _require_session)

- [ ] **Step 2.1: Add ContextVar and update `__init__`, `login`, `_require_session`**

In `src/sapguimcp/backend/desktop/__init__.py`:

Module-level:
```python
from contextvars import ContextVar
from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry

_current_session_id: ContextVar[str | None] = ContextVar("_current_session_id", default=None)
```

Change `__init__`:
```python
def __init__(self, com_thread=None):
    self._com = com_thread or ComThread()
    self._registry = DesktopSessionRegistry()
```

Change `login` — register directly (NOT via property setter):
```python
async def login(self, url, username, password, client, language, session_id=None):
    # ... existing COM login code ...
    session = await self._com.run(lambda: _login_mod.login(...))
    self._registry.register(session)  # → "s1"
    # ... rest of method ...
```

Add backward compat property (read-only, for external code like conftest teardown):
```python
@property
def _session(self) -> GuiSession | None:
    try:
        return self._registry.get_session("s1")
    except ValueError:
        return None
```

Change `_require_session`:
```python
def _require_session(self) -> GuiSession:
    session_id = _current_session_id.get()
    return self._registry.get_session(session_id)  # None → "s1"
```

- [ ] **Step 2.2: Rewrite session management methods**

`open_new_session`:
```python
async def open_new_session(self, tcode):
    session = self._require_session()
    await self._com.run(session.create_session)
    await asyncio.sleep(1)
    def _navigate():
        conn_com = session.com.Parent
        count = conn_com.Children.Count
        if count < 2:
            return None, count, None
        new_ses_com = conn_com.Children(count - 1)
        from sapguimcp.sapgui._factory import wrap_com_object
        new_gui_session = wrap_com_object(new_ses_com)
        new_ses_com.FindById("wnd[0]/tbar[0]/okcd").Text = f"/n{tcode}"
        new_ses_com.FindById("wnd[0]").SendVKey(0)
        title = str(new_ses_com.FindById("wnd[0]").Text)
        return new_gui_session, count, title
    result = await self._com.run(_navigate)
    if result[0] is None:
        return None, result[1], None
    new_gui_session, count, title = result
    session_id = self._registry.register(new_gui_session)
    return session_id, count, title
```

`close_session` — accepts registry ID, maps to COM ID:
```python
async def close_session(self, session_id):
    if not self._registry.has_session(session_id):
        return False
    target = self._registry.get_session(session_id)
    com_id = target.id  # e.g. "/app/con[0]/ses[1]"
    primary = self._registry.get_session("s1")
    def _close():
        conn = primary.com.Parent
        conn.CloseSession(com_id)
        return True
    try:
        result = await self._com.run(_close)
    except Exception:
        result = False
    self._registry.unregister(session_id)
    return result
```

`list_sessions` — registry is source of truth:
```python
async def list_sessions(self):
    result = []
    for sid in self._registry.list_sessions():
        session = self._registry.get_session(sid)
        def _info(s=session):
            return {
                "tcode": str(s.com.Info.Transaction),
                "title": str(s.com.FindById("wnd[0]").Text),
            }
        info = await self._com.run(_info)
        result.append(SessionInfo(
            session_id=sid,
            is_primary=(sid == "s1"),
            agent_id=self._registry.get_bound_agent(sid),
            **info,
        ))
    return result
```

`bind_session`, `release_session`, `has_session`:
```python
async def bind_session(self, session_id, agent_id):
    prev = self._registry.get_bound_agent(session_id)
    self._registry.bind(session_id, agent_id)
    return prev

async def release_session(self, session_id):
    prev = self._registry.get_bound_agent(session_id)
    self._registry.release(session_id)
    return prev

async def has_session(self, session_id):
    return self._registry.has_session(session_id)
```

- [ ] **Step 2.3: Update BackendManager**

In `src/sapguimcp/backend/manager.py`, change desktop branch:
- Single instance keyed as `"desktop"` (not per-session)
- Set `_current_session_id` ContextVar before returning
- Call `registry.check_binding` if session is specified

- [ ] **Step 2.4: Write ContextVar routing unit test**

Create `unittests/test_contextvar_routing.py`:
- Mock registry with two sessions
- Set `_current_session_id` to "s1" → verify `_require_session()` returns session 1
- Set to "s2" → verify returns session 2
- Set to None → verify returns s1 (default)
- Verify ContextVar isolation across async tasks via `asyncio.gather`

- [ ] **Step 2.5: Update conftest teardown**

In `unittests/desktop/conftest.py`, update the backend fixture teardown to clear the registry:
```python
# After closing connections
if hasattr(b, '_registry'):
    for sid in list(b._registry.list_sessions()):
        b._registry.unregister(sid)
```

- [ ] **Step 2.6: Run all unit tests to verify no regressions**

Run: `python -m pytest unittests/test_desktop_session_registry.py unittests/test_contextvar_routing.py unittests/test_table_helpers.py unittests/webgui/ -x -q --tb=short`

- [ ] **Step 2.7: isort + black + linting + typecheck**

- [ ] **Step 2.8: Commit**

---

## Task 3: Desktop integration tests for multi-session

**Files:**
- Create: `unittests/desktop/test_multi_session_integration.py`

- [ ] **Step 3.1: Write integration tests**

Tests to write:
- `test_open_second_session`: open s2, verify both s1 and s2 exist, cleanup
- `test_parallel_navigation`: open s2, set ContextVar per-task, `asyncio.gather(navigate_s1_to_SE37, navigate_s2_to_SE16)`, verify each on correct transaction
- `test_close_session`: open s2, close it, verify s2 gone + s1 works
- `test_bind_and_check`: bind s1 to agent_a, `check_binding` with agent_b, use `caplog` to verify warning logged
- `test_list_sessions`: open s2, call `list_sessions`, verify both IDs present

Important: each test must clean up extra sessions (close s2) and `go_home(backend)`.

- [ ] **Step 3.2: Run integration tests**

Run: `python -m pytest unittests/desktop/test_multi_session_integration.py -x -q --tb=short`

- [ ] **Step 3.3: isort + black + linting**

- [ ] **Step 3.4: Commit**

---

## Task 4: Final verification + PR

- [ ] **Step 4.1: Run full non-integration test suite**

Run: `python -m pytest unittests/test_desktop_session_registry.py unittests/test_contextvar_routing.py unittests/test_table_helpers.py unittests/webgui/ -x -q --tb=short`

- [ ] **Step 4.2: Run ALL desktop integration tests**

Run: `python -m pytest unittests/desktop/ -x -q --tb=short`
This must include existing SE37/SE24/SE11/SE38/SE09/SM37 tests + new multi-session tests.

- [ ] **Step 4.3: linting + typecheck**

Run: `tox -e linting && tox -e type_check`

- [ ] **Step 4.4: Code reviewer**

Dispatch `superpowers:code-reviewer` on the branch against main.

- [ ] **Step 4.5: Push and create PR**

Closes #398.
