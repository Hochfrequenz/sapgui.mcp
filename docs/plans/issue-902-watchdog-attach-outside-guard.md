# Halt watchdog attaches outside the scan guard (#902) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The halt watchdog attaches its SAP GUI scripting engine once, outside the 1 s scan guard, so a pending "Notify when a script attaches to SAP GUI" dialog can neither cancel the attach nor make the next scan attach again.

**Architecture:** All changes live in `ComThread` (`src/sapguimcp/backend/desktop/_com_thread.py`). The engine is attached on the watchdog thread (COM apartment of the watchdog) at two points, both outside the `_SCAN_READ_TIMEOUT_S` guard: (1) on the first watchdog tick after `watch_connection` (right after `sap_login`), and (2) at the start of a scan, before the guard timer starts, when the cache is empty (stale engine dropped). A scan read cancelled by the guard (`RPC_E_CALL_CANCELED`) keeps the cached engine; any other scan error still drops it.

**Tech Stack:** Python 3, pywin32 COM (faked in unit tests; CI runs on Linux), pytest with anyio.

**Spec:** GitHub issue #902 ("Desktop: halt watchdog re-attaches to SAP GUI on every scan while a notification dialog is pending").

## Global Constraints

- The engine is only ever attached and used on the watchdog thread (`_watch`); `watch_connection` runs on the asyncio thread and only signals.
- No new dependency. No change to the guard timeout `_SCAN_READ_TIMEOUT_S = 1.0`.
- Keep clearing the cache when the engine is stale (any scan error other than a guard cancel).
- Without an open ABAP debugger window, scans still make no COM call (`TestNoComAccessWithoutDebugger`); the only COM call outside a halt is the one attach after `watch_connection`.
- Unit tests never touch real COM: fake `win32com.client` via `sys.modules` (existing `TestScriptingEngineCaching._install_fake_win32com`), monkeypatch the module-level `_cancel_call_on`.
- Repository is public: no host names, system aliases, user paths in code, tests or commits.
- Accepted trade-off (state it in the `_get_scripting_engine` docstring and in the PR body): an attach waiting on the notification dialog now blocks the watchdog until a person confirms it, so a halt in that window is only cancelled after the dialog is confirmed, and `halted_connections()` times out after 5 s meanwhile. The watch-time attach puts that window next to the login dialogs.
- Known residue (PR body only): after SAP GUI restarts, a later `watch_connection` finds the old engine cached and does not re-attach; the first scan during a halt drops it and the next scan re-attaches (outside the guard), so one dialog can still appear during that halt. Dropping the engine on every `watch_connection` would raise a dialog per login instead.
- Open live checks for the PR body (done by hand): one halt raises at most one watchdog dialog; none while the debugger window is open when the engine was attached after login; several tool calls right after `sap_login` while the watchdog attaches do not disturb the session; confirming the dialog late still reports a halt that happened meanwhile.

## Review Focus

- Attach at watch time fails (SAP GUI not running, scripting off): the watchdog logs and keeps running; the next scan with an open debugger window retries the attach outside the guard. Covered by Task 1 test `test_failed_watch_attach_is_retried_by_the_scan`.
- Second `watch_connection` (another login) must not attach again while the engine is cached. Covered by `test_engine_is_attached_when_a_connection_is_watched`.
- A scan read cancelled by the guard must not drop the engine (that would re-attach and raise another dialog). Covered by `test_cancelled_scan_read_keeps_the_engine`.
- A scan attach that blocks longer than the guard (pending dialog) must not be cancelled and not repeated. Covered by `test_slow_attach_is_not_cancelled_by_the_scan_guard`.
- Existing fakes (`TestHaltedByDebugger._thread_with_fakes`) must not reach real `win32com` now that the watchdog attaches on watch: stub `_get_scripting_engine` there.

---

### Task 1: Attach the watchdog engine outside the scan guard

**Files:**
- Modify: `src/sapguimcp/backend/desktop/_com_thread.py` (constants near line 63-69, `ComThread.__init__` ~403, `watch_connection` ~758, `_watch` ~832, `_halted_watched_connections` ~900, `_list_debugger_sessions` ~931, `_get_scripting_engine` docstring ~959)
- Test: `unittests/desktop/test_com_thread.py` (`TestHaltedByDebugger._thread_with_fakes` ~356, class `TestScriptingEngineCaching` ~610)

**Interfaces:**
- Produces: `ComThread._attach_engine_requested: threading.Event` (set by `watch_connection`, consumed by `_watch`); `ComThread._attach_engine_if_requested(self) -> None`; module constant `_RPC_E_CALL_CANCELED = -2147418110` (0x80010002).

- [ ] **Step 1: Write the failing tests** in `TestScriptingEngineCaching` (reuse `_install_fake_win32com`):

1. `test_slow_attach_is_not_cancelled_by_the_scan_guard(monkeypatch)`: monkeypatch `_com_thread._SCAN_READ_TIMEOUT_S` to `0.05` and `_com_thread._cancel_call_on` to a fake that sets a `threading.Event` `cancel_requested` and returns `True`. Fake `GetObject` appends to `attach_calls`, then sleeps `0.3` s in steps; if `cancel_requested` is set at the end it raises `_FakeComError(-2147418110, ...)` (what a cancelled real attach raises), else returns an object whose `GetScriptingEngine` has `Children.Count = 0`. Thread: `ComThread(init_com=False, min_interval_ms=0)`, `_debugger_window_open = lambda: True`, add `"/app/con[1]"` to `thread._watched_connections` directly (under `_state_lock`, so no watch-time attach runs). Call `thread._halted_watched_connections()` twice from the test.
   Assert: both return `{}`, `attach_calls == ["SAPGUI"]` and `thread._scripting_engine is not None`. (Before the fix the guard fires during the 0.3 s attach, the fake raises the cancel error, the cache is cleared and the second scan attaches again.)
2. `test_engine_is_attached_when_a_connection_is_watched(monkeypatch)`: fake `GetObject` counting calls returning an empty app; `_debugger_window_open = lambda: False`; `thread.watch_connection("/app/con[1]")`; poll up to 2 s until `attach_calls == ["SAPGUI"]`; then `thread.watch_connection("/app/con[2]")`, poll up to 2 s until `not thread._attach_engine_requested.is_set()` (the watchdog consumed the request); assert `attach_calls == ["SAPGUI"]`. Use `halt_check_after_s=0.2` (0.1 s ticks).
3. `test_failed_watch_attach_is_retried_by_the_scan(monkeypatch)`: fake `GetObject` raises `RuntimeError("SAP GUI not running")` on the first call, returns an empty app afterwards; `halt_check_after_s=0.2`; `watch_connection`, poll until one attach call happened and the watchdog is still alive; then `_debugger_window_open = lambda: True` and `await thread.halted_connections() == {}`; assert `attach_calls == ["SAPGUI", "SAPGUI"]` and `thread._watchdog.is_alive()`. Comment in the test: the request event is cleared before the failed attach, so no tick retries it and the second attach comes from the scan.
4. `test_cancelled_scan_read_keeps_the_engine(monkeypatch)`: engine whose first `Children` access raises `_FakeComError(-2147418110, ...)` and later accesses return `Count = 0`; call `thread._list_debugger_sessions({"/app/con[1]"})` (expect `_FakeComError`), then again (returns `{}`); assert `attach_calls == ["SAPGUI"]`.

Use `-2147418110` via the new constant `_RPC_E_CALL_CANCELED` imported from `sapguimcp.backend.desktop._com_thread` once it exists (in Step 1 the import fails, which is an acceptable failure reason; alternatively use the existing `TestHaltedByDebugger._CANCELLED`).

Also update `TestHaltedByDebugger._thread_with_fakes`: `thread._get_scripting_engine = lambda: object()` so the fakes never reach `win32com`. Before finishing, grep `unittests/` for `watch_connection` and `_record_connection` to confirm no other test with a real `ComThread` now reaches the watch-time attach unstubbed (`test_login_session_lifecycle.py` patches `_record_connection`; `test_session_ownership.py` uses a `MagicMock` com).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bash <helper> run --gate test unittests/desktop/test_com_thread.py -k "TestScriptingEngineCaching"`
Expected: tests 1-4 FAIL (1: two attach calls; 2: no attach on watch; 3: one attach only; 4: two attach calls). Existing tests pass.

- [ ] **Step 3: Implement in `_com_thread.py`**

- `_RPC_E_CALL_CANCELED = -2147418110  # 0x80010002 — what CoCancelCall makes the cancelled call raise` next to the other codes.
- `__init__`: `self._attach_engine_requested = threading.Event()` (before the watchdog thread starts).
- `watch_connection`: after adding the id, `self._attach_engine_requested.set()`.
- `_attach_engine_if_requested(self) -> None`: if the event is set, clear it; then `self._get_scripting_engine()`; on `Exception` log `logger.warning("com_watchdog_attach_failed", exc_info=True)` and return (the scan retries). Docstring says why: attaching here, right after login, shows SAP GUI's attach dialog together with the login dialogs, never during a halt, and outside any guard.
- `_watch`: inside the per-tick `try`, call `self._attach_engine_if_requested()` first, before `_answer_scan_request` and `_cancel_if_halted`.
- `_halted_watched_connections`: after the `_debugger_window_open()` check and before creating the guard timer, `self._get_scripting_engine()` inside `try/except Exception` that logs `com_debugger_scan_failed` at debug and returns `{}`. One-line comment: the attach can wait on SAP GUI's notification dialog; under the guard it would be cancelled and repeated by every scan.
- `_list_debugger_sessions` `except Exception as exc`: clear `self._scripting_engine` only when `_get_com_error_code(exc) != _RPC_E_CALL_CANCELED`; update the comment (a read cancelled by the guard says nothing about the engine; dropping it would re-attach and raise another dialog).
- `_get_scripting_engine` docstring: replace the sentence about the dialog blocking the read with: it is called outside the scan guard (see `_attach_engine_if_requested` and `_halted_watched_connections`) because the attach waits for the dialog; while it waits, the watchdog cancels nothing (the accepted trade-off of the Global Constraints).
- Module docstring (paragraph "Halted sessions", lines 28-36): one sentence that the watchdog attaches its own scripting engine once, on its first tick after a connection is watched (or at the start of a scan when none is cached), outside the scan-read guard.
- Keep the "stale proxy" explanation in the `_list_debugger_sessions` comment next to the new cancel exception.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bash <helper> run --gate test unittests/desktop/test_com_thread.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/desktop/_com_thread.py unittests/desktop/test_com_thread.py
git commit -m 'fix(#902): halt watchdog attaches to SAP GUI outside the scan guard' -m 'Bugspecht-Sprint: bs-20261120-0924-rfw3'
```
