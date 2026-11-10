# Session Language Plumbing Implementation Plan (phase 1 of #1044)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every tool call knows the logon language of the session it works on. SLG1, SM37 and ST22
stop reading the language of the _default_ system.

**Architecture:** A new module `sapguimcp/session_language.py` holds a backend-neutral context
variable with the current session's SAP language key. Both session registries store each
session's language. Desktop reads it from `session.info.language` in the existing login COM call;
WebGUI reads `document.documentElement.lang` in `_post_login_setup`. `BackendManager.get_or_create`
sets the variable on every tool call, login sets it for the new session, and recovery clears it.
`ComThread.run` copies the caller's context to the COM worker, so the variable (and every other
context variable) is visible inside COM closures.

**Tech Stack:** Python 3.11+, `contextvars`, pytest + anyio, Playwright (WebGUI), sapsucker (desktop COM).

Spec: `docs/superpowers/specs/2026-11-10-language-packs-design.md` §5 and rollout phase 1.

**Phase-1 compromise:** there are no language packs yet. When the variable is unset (legacy
`_session` setter, unit tests), `session_sap_language()` falls back to the configured default
system's language — today's behaviour — and logs it at debug level. Phase 2 replaces this with
`lang.current()` / `UnsupportedLanguageError`.

## Testing rules (read before running anything)

- Run unit tests **by explicit path** (`uv run --group tests python -m pytest unittests/<file> -q`).
  Never run the whole suite.
- Live tests touch the single shared SAP connection: only the controller runs them, one at a time,
  after all tasks are done (Task 6). Implementer agents do **not** run `-m integration`.
- Desktop live-test teardown closes the SAP GUI connections it opened.
- **Lint and type check** at the end of every task (from `CONTRIBUTING.md`):
  `uv run --group linting ruff check .`, `uv run --group linting ruff format --check .`,
  `uv run --group type_check mypy --show-error-codes src/sapguimcp --strict`.
- Tests that call code which sets the session language wrap it in `with use_language(None):`, so
  no value leaks into other tests.
- Commit with explicit `git add <paths>`; `git commit -a` skips new files.

## File structure

| File                                                                         | Responsibility                                                                                                                                                                                                                                                                                                      |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Create `src/sapguimcp/session_language.py`                                   | context variable, `current_language`, `set_session_language`, `use_language`, `normalize_language`, `session_sap_language`                                                                                                                                                                                          |
| Modify `src/sapguimcp/backend/desktop/_com_thread.py`                        | `run()` copies the caller context to the worker                                                                                                                                                                                                                                                                     |
| Modify `src/sapguimcp/backend/desktop/_session_registry.py`                  | `_languages` dict, `set_language`, `language_of`, cleanup in `unregister`/`prune`                                                                                                                                                                                                                                   |
| Modify `src/sapguimcp/backend/desktop/__init__.py`                           | login reads `(user, language)`; `_open_new_session_locked` copies the parent's language; login sets the context variable                                                                                                                                                                                            |
| Modify `src/sapguimcp/backend/webgui/models/session_registry.py`             | `_languages` dict, `set_language`, `language_of`, `session_id_of`, cleanup                                                                                                                                                                                                                                          |
| Modify `src/sapguimcp/backend/webgui/backend.py`                             | `_post_login_setup` reads the page language; `/o` tabs inherit it                                                                                                                                                                                                                                                   |
| Modify `src/sapguimcp/backend/manager.py`                                    | `get_or_create` sets the variable; recovery clears it                                                                                                                                                                                                                                                               |
| Modify `src/sapguimcp/tools/slg1_tools.py`, `sm37_tools.py`, `st22_tools.py` | use `session_sap_language()`                                                                                                                                                                                                                                                                                        |
| Tests                                                                        | `unittests/test_session_language.py` (new), `unittests/desktop/test_com_thread.py`, `unittests/test_desktop_session_registry.py`, `unittests/test_session_registry.py`, `unittests/test_backend_manager.py`, `unittests/desktop/test_login_session_lifecycle.py`, `unittests/test_webgui_session_language.py` (new) |

## Model assignment (from the spec)

| Task                                         | Implement                                    | Review              |
| -------------------------------------------- | -------------------------------------------- | ------------------- |
| 1 `session_language` module                  | opus                                         | fable (with Task 2) |
| 2 `copy_context` in `ComThread.run`          | opus                                         | fable               |
| 3 registries + desktop/WebGUI language reads | sonnet                                       | opus                |
| 4 manager wiring + recovery                  | opus                                         | fable               |
| 5 SLG1/SM37/ST22 switch                      | sonnet                                       | sonnet              |
| 6 live tests                                 | controller runs, haiku may collect summaries | —                   |

---

### Task 1: `session_language` module

**Files:**

- Create: `src/sapguimcp/session_language.py`
- Test: `unittests/test_session_language.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the per-session SAP language context variable (#1044, phase 1)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.session_language import (
    current_language,
    normalize_language,
    session_sap_language,
    set_session_language,
    use_language,
)


def test_default_is_none() -> None:
    assert current_language() is None


def test_use_language_sets_and_restores() -> None:
    with use_language("DE"):
        assert current_language() == "DE"
        with use_language("EN"):
            assert current_language() == "EN"
        assert current_language() == "DE"
    assert current_language() is None


@pytest.mark.parametrize(("raw", "expected"), [("de", "DE"), (" En ", "EN"), ("", None), (None, None)])
def test_normalize_language(raw: str | None, expected: str | None) -> None:
    assert normalize_language(raw) == expected


def test_set_session_language_normalizes() -> None:
    with use_language(None):
        set_session_language("de")
        assert current_language() == "DE"


@pytest.mark.anyio
async def test_tasks_are_isolated() -> None:
    async def worker(code: str) -> str | None:
        set_session_language(code)
        await asyncio.sleep(0)
        return current_language()

    results = await asyncio.gather(worker("DE"), worker("EN"))
    assert results == ["DE", "EN"]
    assert current_language() is None


def test_session_sap_language_uses_context() -> None:
    with use_language("DE"):
        assert session_sap_language() == "DE"


def test_session_sap_language_falls_back_to_default_system() -> None:
    cfg = MagicMock()
    cfg.get_default.return_value.language = "DE"
    with use_language(None), patch("sapguimcp.models.config.get_sap_config", return_value=cfg):
        assert session_sap_language() == "DE"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/test_session_language.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'sapguimcp.session_language'`

- [ ] **Step 3: Implement**

```python
"""The SAP logon language of the session the current tool call works on (#1044).

A context variable, so concurrent tool calls on different sessions never see each other's
language. ``BackendManager.get_or_create`` sets it for every tool call, ``sap_login`` sets it for
the session it just opened, and desktop recovery clears it. ``ComThread.run`` copies the caller's
context to the COM worker, so the value is visible inside COM closures too.

Phase 1 of #1044: this module only carries the language. The language packs of phase 2 build on
it (``lang.current()``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sapguimcp.utils import SapLanguage, as_sap_language

logger = logging.getLogger(__name__)

_session_language: ContextVar[str | None] = ContextVar("session_language", default=None)


def normalize_language(code: str | None) -> str | None:
    """Upper-case and strip an SAP language key; empty or ``None`` becomes ``None``."""
    if code is None:
        return None
    normalized = code.strip().upper()
    return normalized or None


def current_language() -> str | None:
    """SAP language key of the current session, or ``None`` when unknown."""
    return _session_language.get()


def set_session_language(code: str | None) -> None:
    """Set the current session's language for the rest of this task (and its child tasks)."""
    _session_language.set(normalize_language(code))


@contextmanager
def use_language(code: str | None) -> Iterator[None]:
    """Temporarily set the session language, e.g. in tests."""
    token = _session_language.set(normalize_language(code))
    try:
        yield
    finally:
        _session_language.reset(token)


def session_sap_language() -> SapLanguage:
    """The current session's language narrowed to what the tools handle today.

    Falls back to the configured default system's language when the session language is
    unknown — the behaviour before #1044. Phase 2 replaces this with the language packs.
    """
    code = current_language()
    if code is None:
        from sapguimcp.models.config import get_sap_config  # noqa: PLC0415  # avoid import cycle

        code = get_sap_config().get_default().language
        logger.debug("session language unknown, using the default system's", extra={"language": code})
    return as_sap_language(code)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --group tests python -m pytest unittests/test_session_language.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/session_language.py unittests/test_session_language.py
git commit -m "feat(lang): context variable for the session's logon language (#1044)"
```

---

### Task 2: `ComThread.run` copies the caller's context

**Files:**

- Modify: `src/sapguimcp/backend/desktop/_com_thread.py` (`run`, around lines 592-620)
- Test: `unittests/desktop/test_com_thread.py`

- [ ] **Step 1: Write the failing tests** (append to `TestComThread`)

```python
    @pytest.mark.anyio
    async def test_run_sees_callers_context_variables(self, com_thread):
        """#1044: COM closures see the caller's context (e.g. the session language)."""
        from sapguimcp.session_language import current_language, use_language

        with use_language("DE"):
            assert await com_thread.run(current_language) == "DE"
        with use_language("EN"):
            assert await com_thread.run(current_language) == "EN"

    @pytest.mark.anyio
    async def test_run_context_is_per_call(self, com_thread):
        """Concurrent callers with different contexts each see their own value."""
        from sapguimcp.session_language import current_language, set_session_language

        async def call(code: str) -> str | None:
            set_session_language(code)
            return await com_thread.run(current_language)

        assert await asyncio.gather(call("DE"), call("EN"), call("FR")) == ["DE", "EN", "FR"]

    @pytest.mark.anyio
    async def test_worker_writes_do_not_leak(self, com_thread):
        """Context-variable writes inside a COM closure stay on the worker's copy."""
        from sapguimcp.session_language import current_language, set_session_language, use_language

        with use_language("DE"):
            await com_thread.run(lambda: set_session_language("EN"))
            assert current_language() == "DE"
            assert await com_thread.run(current_language) == "DE"

    @pytest.mark.anyio
    async def test_many_sequential_calls_under_one_context(self, com_thread):
        """A fresh copy per call: repeated calls never hit 'cannot enter context'."""
        from sapguimcp.session_language import current_language, use_language

        with use_language("DE"):
            results = [await com_thread.run(current_language) for _ in range(20)]
        assert results == ["DE"] * 20
```

Also add a **mandatory** retry test, following the existing pattern at
`unittests/desktop/test_com_thread.py:86-105` (`FakeComError(-2147023179)`): a callable that fails
once with that retryable error and then returns `current_language()` must return the caller's value
under `use_language("DE")`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/desktop/test_com_thread.py -q -k "context or leak or sequential or retry"`
Expected: every new test except `test_worker_writes_do_not_leak` FAILS (the worker returns `None`).

- [ ] **Step 3: Implement** in `ComThread.run`, replacing the `put`:

```python
        cf_future: concurrent.futures.Future[T] = concurrent.futures.Future()
        # Run fn inside a copy of the caller's context so context variables (session language,
        # #1044) are visible on the worker. One fresh copy per call, never stored: a Context
        # cannot be entered twice concurrently, and retries re-enter it one after another.
        # ``com_call_target`` stays hand-carried: the watchdog thread reads it.
        ctx = contextvars.copy_context()
        self._queue.put(
            (functools.partial(ctx.run, fn), cf_future, max_retries, com_call_target.get(), retry_server_fault)
        )
        return await asyncio.wrap_future(cf_future)
```

Add `import contextvars` at the top (`functools` is already imported; check). Read
`_invoke_tracked` and `_execute_with_retry` first: if they call `fn(...)` with arguments (batch
carrier), `functools.partial(ctx.run, fn)` forwards them — confirm with a test that passes an
argument if such a path exists.

- [ ] **Step 4: Run the whole COM-thread test files**

Run: `uv run --group tests python -m pytest unittests/desktop/test_com_thread.py unittests/desktop/test_com_thread_stress.py unittests/desktop/test_com_evaluate_unit.py unittests/desktop/test_com_serverfault.py unittests/test_contextvar_routing.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/desktop/_com_thread.py unittests/desktop/test_com_thread.py
git commit -m "fix(desktop): COM closures see the caller's context variables (#1044)"
```

---

### Task 3: Both registries store each session's language

**Files:**

- Modify: `src/sapguimcp/backend/desktop/_session_registry.py`
- Modify: `src/sapguimcp/backend/desktop/__init__.py` (login ~line 801-803, `_open_new_session_locked` ~line 1074-1101)
- Modify: `src/sapguimcp/backend/webgui/models/session_registry.py`
- Modify: `src/sapguimcp/backend/webgui/backend.py` (`_post_login_setup` ~line 230, `_register_new_window_session` ~line 549)
- Test: `unittests/test_desktop_session_registry.py`, `unittests/test_session_registry.py`,
  `unittests/desktop/test_login_session_lifecycle.py`, and a **new** file
  `unittests/test_webgui_session_language.py` (no `_post_login_setup` tests exist yet).

Login sets the context variable itself (both backends), so the rest of the `sap_login` tool call
works on the new session's language: desktop `login` calls `set_session_language(logon_language)`
right after storing it; WebGUI `_post_login_setup` calls `set_session_language(<stored value>)`.
Both run in the tool's task (`await backend.login(...)`). `sap_login_impl.py` is **not** changed —
WebGUI's `LoginResult` carries no `session_id`, and `WebGuiBackend` has no `.registry`.

- [ ] **Step 1: Failing registry tests** (both registries, same shape)

```python
def test_language_is_stored_and_cleared() -> None:
    reg = DesktopSessionRegistry()           # WebGUI: SessionRegistry() with a MagicMock page
    sid = reg.register(MagicMock())
    assert reg.language_of(sid) is None
    reg.set_language(sid, "de")
    assert reg.language_of(sid) == "DE"
    reg.unregister(sid)
    assert reg.language_of(sid) is None


def test_language_of_unknown_session_is_none() -> None:
    assert DesktopSessionRegistry().language_of("s9") is None
```

Desktop also: `prune([...])` and `clear()` clear the language (`clear()` resets the counter, so a
stale language would otherwise attach to the next `s1`). WebGUI also: `_on_page_closed(page)` and the
stale-tab cleanup in `get_page` (~line 107-110, where `_bindings` is popped) clear it, and
`session_id_of(page)` returns the id of a registered page and `None` otherwise.

- [ ] **Step 2: Run, verify failure** (`AttributeError: ... has no attribute 'language_of'`).

- [ ] **Step 3: Implement** in both registries:

```python
        self._languages: dict[str, str] = {}  # session_id -> SAP logon language key (#1044)

    def set_language(self, session_id: str, code: str | None) -> None:
        """Record *session_id*'s logon language; ``None``/empty removes it."""
        normalized = normalize_language(code)
        if normalized is None:
            self._languages.pop(session_id, None)
        else:
            self._languages[session_id] = normalized

    def language_of(self, session_id: str) -> str | None:
        """Logon language of *session_id*, or ``None`` when unknown."""
        return self._languages.get(session_id)
```

Pop `_languages` wherever `_bindings` is popped: desktop `unregister`, `prune`, `clear()`
(`self._languages.clear()`); WebGUI `unregister`, `_on_page_closed`, the stale-tab cleanup in
`get_page`.
WebGUI additionally:

```python
    def session_id_of(self, page: "Page") -> str | None:
        """Session id of a registered page, or ``None``."""
        return self._page_to_session.get(page)
```

- [ ] **Step 4: Failing desktop login test** in `unittests/desktop/test_login_session_lifecycle.py`
      (use `make_mock_session(language=...)` from `unittests/desktop/conftest.py:245-262`; the file's
      `_make_backend` passthrough returns `fn()`, so a tuple-returning lambda works): after a successful
      login with language `"DE"`, `backend.registry.language_of(result.session_id) == "DE"` **and**
      `current_language() == "DE"`. A second test: `open_new_session` from a `DE` session registers the
      new session with language `DE`. Wrap each test body in `with use_language(None):` so the value
      does not leak into other tests (anyio shares the runner task).

- [ ] **Step 5: Implement desktop**

Login (replace the `user_name = await self.com.run(lambda: str(session.info.user))` line):

```python
                user_name, logon_language = await self.com.run(
                    lambda: (str(session.info.user), str(session.info.language))
                )
                self.registry.set_language(new_session_id, logon_language)
                # The rest of this sap_login call works on the new session (#1044).
                set_session_language(logon_language)
```

Do **not** name it `language`: that would shadow `login`'s own `language` parameter, which is used a
few lines above. Add `"language": logon_language` to the existing `login` log `extra`. In
`_open_new_session_locked` (reached from `open_new_session`), after
`session_id = self.registry.register(result_session)`:

```python
            # A session opened from another one shares its connection, so its logon language.
            parent_id = _current_session_id.get() or self.registry.primary_session
            self.registry.set_language(session_id, self.registry.language_of(parent_id))
```

(`require_session` resolves the parent through `get_session(None)`, i.e. the same default.)

- [ ] **Step 6: Failing WebGUI tests** in the new `unittests/test_webgui_session_language.py`. Pattern
      from `unittests/test_get_session_status_per_id.py:214`:
      `patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=SessionRegistry()))`, also
      patch `_capture_sap_identity`, page `evaluate=AsyncMock(return_value="de")`. With that,
      `_post_login_setup` leaves `registry.language_of(<page's session>) == "DE"` and
      `current_language() == "DE"`. A page returning `""` falls back to the
      `language` passed to `login` (pass it into `_post_login_setup` as a new keyword argument).
      A test for `_register_new_window_session`: the new tab inherits the origin tab's language.

- [ ] **Step 7: Implement WebGUI**

`_post_login_setup(self, effective_url, mandant, session_id, requested_language: str | None = None)`;
all three call sites in `login` pass `language`. After registering:

```python
        page_session = registry.session_id_of(self._page)
        if page_session is not None:
            registry.set_language(page_session, await self._read_page_language() or requested_language)
            # The rest of this sap_login call works on this session (#1044).
            set_session_language(registry.language_of(page_session))
```

```python
    async def _read_page_language(self) -> str | None:
        """SAP logon language from the page's ``<html lang>`` (ISO code, e.g. ``de``).

        Phase 1 of #1044: ISO and SAP keys coincide for DE and EN. Phase 2 maps ISO codes to SAP
        keys through the language packs' ``html_lang``.
        """
        try:
            value = await self._page.evaluate("() => document.documentElement.lang || ''")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("could not read the page language", exc_info=True)
            return None
        if not isinstance(value, str):  # e.g. a mocked page
            return None
        return normalize_language(value.split("-")[0])
```

In `_register_new_window_session`, after `new_session_id = registry.register(new_page)`:

```python
            origin_session = registry.session_id_of(self._page)
            if origin_session is not None:
                registry.set_language(new_session_id, registry.language_of(origin_session))
```

- [ ] **Step 8: Run all touched test files** — expected PASS:

`uv run --group tests python -m pytest unittests/test_desktop_session_registry.py unittests/test_session_registry.py unittests/desktop/test_login_session_lifecycle.py unittests/test_webgui_session_language.py unittests/test_get_session_status_per_id.py -q`

- [ ] **Step 9: Commit**

```bash
git add src/sapguimcp/backend unittests/test_desktop_session_registry.py unittests/test_session_registry.py unittests/desktop/test_login_session_lifecycle.py unittests/test_webgui_session_language.py
git commit -m "feat: session registries record each session's logon language (#1044)"
```

---

### Task 4: Set the variable on every tool call, clear it on recovery

(Login already sets it, Task 3.)

**Files:**

- Modify: `src/sapguimcp/backend/manager.py` (`get_or_create`, `_recover_desktop_if_dead`). Import
  `set_session_language` at module top level, **not** inside the `if sys.platform == "win32" or
TYPE_CHECKING:` block — the WebGUI path needs it on every platform.
- Test: `unittests/test_backend_manager.py`.
    - Desktop: use `_make_desktop_manager()` and the `desktop_symbols` fixture (lines ~82-116); seed
      `manager._backends["desktop"]` with `DesktopBackend.__new__` plus a real
      `DesktopSessionRegistry`; leaving `_com_thread=None` makes recovery a no-op.
    - WebGUI: patch `sapguimcp.backend.manager.get_browser_manager` to return a mock whose
      `get_or_create_session_page_checked` is an `AsyncMock` and whose `registry` is a real
      `SessionRegistry`.
    - Wrap each test in `with use_language(None):`.

- [ ] **Step 1: Failing tests**
    - desktop: registry with `s1` (`DE`) and `s2` (`EN`); `get_or_create(session="s2")` →
      `current_language() == "EN"`; `get_or_create()` → language of the primary session.
    - desktop: a session without a recorded language → `current_language() is None` (no stale value
      from a previous call in the same task).
    - webgui: same with the browser manager's registry.
    - recovery: call `_recover_desktop_if_dead` directly with a dead `_com_thread` mock
      (`is_alive = False`); afterwards `current_language() is None`.

- [ ] **Step 2: Run, verify failure.**

- [ ] **Step 3: Implement**

In `get_or_create`, desktop paths after `_current_session_id.set(effective)`:

```python
                set_session_language(cached.registry.language_of(effective))
```

(and `new_backend.registry.language_of(effective)` in the new-backend path). WebGUI path, before
each `return`: `set_session_language(browser_manager.registry.language_of(session_key))`. In
`_recover_desktop_if_dead`, next to `_current_session_id.set(None)`: `set_session_language(None)`.

- [ ] **Step 4: Run tests** — expected PASS:

`uv run --group tests python -m pytest unittests/test_backend_manager.py unittests/desktop/test_engine_busy_hint.py unittests/test_contextvar_routing.py unittests/test_session_language.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/manager.py unittests/test_backend_manager.py
git commit -m "feat: every tool call carries its session's logon language (#1044)"
```

---

### Task 5: SLG1, SM37, ST22 use the session's language

**Files:**

- Modify: `src/sapguimcp/tools/slg1_tools.py:136-137,294-295`, `src/sapguimcp/tools/sm37_tools.py:241-242,501-502`, `src/sapguimcp/tools/st22_tools.py:162-163`
- Test: `unittests/test_slg1_desktop_unreadable_list.py`, `unittests/test_sm37_desktop_empty_result.py`, `unittests/test_st22_desktop_readiness.py`, plus one new test per tool

- [ ] **Step 1: Failing test per tool**: with the default system configured as `EN` (patch
      `sapguimcp.models.config.get_sap_config`) and `use_language("DE")`, the tool formats a date as
      `DD.MM.YYYY` / uses the DE labels. Before the change it uses EN.

- [ ] **Step 1b: Update existing tests** that patch the tool modules' `get_sap_config`, which no
      longer exists there after this task: `unittests/test_slg1_desktop_unreadable_list.py:33`,
      `unittests/test_slg1_log_tree.py:94`, `unittests/test_sm37_desktop_empty_result.py:39,52,70`.
      Replace each patch with `use_language("EN")` / `use_language("DE")` matching the language the test
      configured.

- [ ] **Step 2: Run, verify failure.**

- [ ] **Step 3: Implement**: replace each

```python
    sap_cfg = get_sap_config()
    language: SapLanguage = as_sap_language(sap_cfg.get_default().language)
```

with

```python
    language: SapLanguage = session_sap_language()
```

Remove imports that become unused (`get_sap_config`, `as_sap_language`); keep any still used.

- [ ] **Step 4: Run the tool test files** — expected PASS:

`uv run --group tests python -m pytest unittests/test_slg1_desktop_unreadable_list.py unittests/test_slg1_log_tree.py unittests/test_sm37_desktop_empty_result.py unittests/test_st22_desktop_readiness.py unittests/test_st22_detail_parsing.py unittests/test_date_helpers.py -q`

- [ ] **Step 5: Lint and type check the touched files**

See "Lint and type check" in the testing rules.

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/tools unittests
git commit -m "fix(slg1,sm37,st22): use the session's logon language, not the default system's (#1044)"
```

---

### Task 6: Live verification (controller only, single SAP connection)

- [ ] Desktop backend, on both systems (the ECC and the S/4HANA system), DE and EN where configured:
    - login, then `sap_sm37_lookup` with a date range, `sap_slg1_lookup` with a date range,
      `sap_st22_lookup` for today: no regression.
    - a second login to a system with a different language in the same server process, then the
      same lookups on each session: each uses its own language.
- [ ] Run the relevant existing live tests by path (`unittests/desktop/` login/session lifecycle,
      SM37/SLG1/ST22 live tests) and record the literal pytest summaries for the PR. Rerun a failure
      on its own and compare with `main` before calling it real (flaky-test rule in the spec).
- [ ] WebGUI: one login + SM37 live test if the WebGUI environment is available; otherwise state
      in the PR that it was not run and why.

Then: PR with the spec, this plan and the code; self-review, Copilot review, CI green; ask before
merging.
