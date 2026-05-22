# Desktop Multi-Session Support (#398)

## Problem

The desktop backend has a single `_session` attribute. All tools call `_require_session()` which returns the same `GuiSession`. When multiple agents are dispatched in parallel, they all operate on the same SAP GUI window and interfere with each other.

## Design

### Approach: DesktopSessionRegistry + ContextVar routing

Mirror the WebGUI `SessionRegistry` pattern for the desktop COM backend. Session IDs are `s1`, `s2`, `s3` (same as WebGUI) — not SAP's COM IDs (`/app/con[0]/ses[0]`).

### Component 1: DesktopSessionRegistry

New file: `src/sapguimcp/backend/desktop/_session_registry.py`

```
DesktopSessionRegistry:
    _sessions: dict[str, GuiSession]     # "s1" → COM session object
    _bindings: dict[str, str]            # "s1" → "agent_a"
    _counter: int                        # auto-increment for IDs

    register(session) → str              # returns "s1", "s2", ...
    get_session(session_id | None) → GuiSession  # None defaults to "s1"
    unregister(session_id) → None
    bind(session_id, agent_id) → None    # matches WebGUI signature (void)
    release(session_id) → None           # matches WebGUI signature (void)
    check_binding(session_id, agent_id, tool_name) → None  # warn-only
    list_sessions() → list[str]
    has_session(session_id) → bool
    get_bound_agent(session_id) → str | None
```

**Stale session detection:** `get_session()` probes `session.com.Info.Transaction` before returning. If the COM call fails, the session is auto-unregistered and `ValueError` is raised. This replaces WebGUI's `page.is_closed()` check — SAP GUI COM has no close event, so we check on access.

**Performance:** To avoid a COM round-trip on every tool call, the probe is only performed if the session hasn't been successfully used within the last 5 seconds (cached TTL). On first access or after errors, the full probe runs.

### Component 2: ContextVar routing

Module-level in desktop backend:

```python
_current_session_id: ContextVar[str | None] = ContextVar("_current_session_id", default=None)
```

Flow:
1. `BackendManager.get_or_create(session="s2")` sets `_current_session_id.set("s2")`
2. Tool calls `backend.fill_field(...)` → `_require_session()`
3. `_require_session()` reads `_current_session_id.get()` → `registry.get_session("s2")` → correct `GuiSession`
4. The resolved `GuiSession` is captured by the lambda closure submitted to `ComThread`
5. COM call goes to the right SAP window

**Critical invariant:** The `ContextVar` MUST be read on the async caller's task (in `_require_session()`), NEVER inside a `ComThread` lambda. `ContextVar` does not propagate across threads — reading it on the COM thread would return the default `None`. The current code already follows this pattern: `session = self._require_session()` is always called in the async method body, then `session` is captured by the lambda.

**Thread safety:** `ContextVar` is per-async-task. Parallel `asyncio.gather()` calls with different session IDs resolve correctly. The `ComThread` serializes actual COM execution — parallelism is at the async layer, not COM layer.

### Component 3: Changes to BackendManager

Currently `BackendManager.get_or_create()` creates a **new `DesktopBackend`** for each session key (caching in `self._backends`). This must change:

- **Single `DesktopBackend` instance** shared across all sessions (one `ComThread`, one `DesktopSessionRegistry`)
- `self._backends["desktop"]` stores the single instance
- Session routing is handled by the `ContextVar`, not by separate backend instances
- Before returning the backend, set `_current_session_id.set(session or "s1")` and call `registry.check_binding()`
- `self._page_ids` cache (WebGUI-specific) is not used for desktop

### Component 4: Changes to DesktopBackend

**`__init__`**: Replace `self._session` and `self._agent_bindings` with `self._registry = DesktopSessionRegistry()`.

**`login`**: After login, `self._registry.register(session)` → returns "s1".

**`_require_session`**: Read `_current_session_id.get()`, look up via registry. Fallback to "s1" if no ContextVar set (backward compat).

**`open_new_session`**: Create SAP session via COM `session.create_session()`, then get the new session from `conn.Children(count-1)`. Wrap the raw COM object in a pysapgui `GuiSession` using `wrap_com_object()` from `sapguimcp.sapgui._factory`. Register in registry → returns "s2". The registry stores `GuiSession` wrappers, not raw COM objects.

**`close_session`**: Accepts registry ID ("s2"). Looks up `GuiSession` from registry to get the raw COM session ID (`session.id`), calls `conn.CloseSession(com_id)`, then `registry.unregister("s2")`.

**`list_sessions`**: Iterates `registry.list_sessions()`, builds `SessionInfo` from each `GuiSession`'s properties (transaction, title, etc). Does NOT enumerate `conn.Children` directly — the registry is the source of truth.

**`bind_session` / `release_session`**: Delegate to `registry.bind()` / `registry.release()`. Return types match WebGUI signatures (void via the `DesktopBackend` wrapper, even if the protocol returns `str | None`).

**Backward compat**: `self._session` becomes a property returning `registry.get_session("s1")`.

### Error handling

- **Session not found**: `ValueError` raised by `get_session()` — same as WebGUI.
- **Session limit reached**: `open_new_session` returns `(None, count, None)` — caller handles.
- **Primary session closed externally**: COM probe fails → `ValueError`. Recovery requires new `login()`.
- **Stale sessions**: Detected on access via COM probe (with TTL cache), auto-unregistered.

### Differences from WebGUI SessionRegistry

| Aspect | WebGUI | Desktop |
|--------|--------|---------|
| Stored object | Playwright `Page` | pysapgui `GuiSession` |
| Auto-cleanup | `page.on("close")` event | Check-on-access (COM probe with TTL) |
| Stale detection | `page.is_closed()` | `session.com.Info.Transaction` probe |
| Session creation | `/o` opens browser tab | `session.create_session()` COM call |
| BackendManager | One `WebGuiBackend` per page | Single `DesktopBackend` shared |

Everything else is identical: ID scheme, binding, check_binding (warn-only), list/has/close.

## Testing

### Unit tests (no SAP)
- Registry: register/get/unregister/bind/release/check_binding/list with mock GuiSession
- `_require_session()` with ContextVar: verify correct session routing per async task
- Stale session: mock dead COM, verify ValueError + auto-unregister
- Edge cases: get nonexistent session, unregister primary, TTL cache behavior

### Integration tests (live SAP)
- Open second session, verify "s2" returned and session count = 2
- **Parallel navigation** via `asyncio.gather()`: s1 navigates to SE37, s2 to SE16 concurrently — verify each is on the correct transaction afterward
- Session isolation: fill field on s1 → verify s2 screen is unaffected
- Bind + cross-agent access: bind s2 to "agent_a", access with "agent_b" → verify warning logged
- Close session: close s2 → verify s2 raises ValueError, s1 still works
- Cleanup: teardown closes all extra sessions

## Files changed

- **New**: `src/sapguimcp/backend/desktop/_session_registry.py`
- **New**: `unittests/test_desktop_session_registry.py` (unit tests)
- **New**: `unittests/desktop/test_multi_session_integration.py`
- **Modified**: `src/sapguimcp/backend/desktop/__init__.py` (registry, ContextVar, _require_session)
- **Modified**: `src/sapguimcp/backend/manager.py` (single desktop backend, set ContextVar)
