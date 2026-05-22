# Desktop Backend Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement SapNavigation + SapUiInspection + press_key using pysapgui (COM) — enough to navigate SAP, read screens, and press function keys via the existing MCP tools.

**Architecture:** `DesktopBackend` class implements `SapUiBackend` protocol. All COM calls run on a dedicated background thread (`_ComThread`) to satisfy COM apartment threading. Methods not applicable to desktop (JS, CSS selectors) raise `NotImplementedError`. The `BackendManager` dispatches to `DesktopBackend` when `BACKEND_TYPE=desktop`.

**Tech Stack:** Python 3.11+, pywin32 (COM), pydantic (models), pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-03-15-desktop-backend-adapter-design.md`

---

## File Structure

```
src/sapguimcp/backend/desktop/
    __init__.py              # DesktopBackend class (~200 lines)
    _com_thread.py           # _ComThread — dedicated COM worker (~50 lines)
    _key_mapping.py          # VKey name → number map (~40 lines)

src/sapguimcp/models/config.py     # Modify: BackendType → Literal["webgui", "desktop"]
src/sapguimcp/backend/manager.py   # Modify: add desktop branch

unittests/desktop/
    __init__.py
    conftest.py              # shared mock fixtures
    test_com_thread.py       # _ComThread tests
    test_key_mapping.py      # VKey mapping tests
    test_desktop_backend.py  # DesktopBackend unit tests (mocked COM)
    test_manager_desktop.py  # BackendManager desktop integration
```

---

## Chunk 1: Foundation — ComThread, KeyMapping, Config

### Task 1: \_ComThread

**Files:**

- Create: `src/sapguimcp/backend/desktop/__init__.py` (empty)
- Create: `src/sapguimcp/backend/desktop/_com_thread.py`
- Create: `unittests/desktop/__init__.py`
- Test: `unittests/desktop/test_com_thread.py`

- [ ] **Step 1: Write tests**

```python
# unittests/desktop/test_com_thread.py
"""Tests for _ComThread — dedicated COM worker thread."""
import asyncio

import pytest

from sapguimcp.backend.desktop._com_thread import ComThread


@pytest.fixture
def com_thread():
    """Create a ComThread for testing (no real COM — just the threading mechanism)."""
    thread = ComThread(init_com=False)  # skip CoInitialize for unit tests
    yield thread
    thread.shutdown()


class TestComThread:
    @pytest.mark.anyio
    async def test_run_returns_result(self, com_thread):
        result = await com_thread.run(lambda: 42)
        assert result == 42

    @pytest.mark.anyio
    async def test_run_returns_string(self, com_thread):
        result = await com_thread.run(lambda: "hello")
        assert result == "hello"

    @pytest.mark.anyio
    async def test_run_propagates_exception(self, com_thread):
        def failing():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await com_thread.run(failing)

    @pytest.mark.anyio
    async def test_run_preserves_exception_type(self, com_thread):
        def failing():
            raise KeyError("missing")

        with pytest.raises(KeyError):
            await com_thread.run(failing)

    @pytest.mark.anyio
    async def test_multiple_calls_sequential(self, com_thread):
        results = []
        for i in range(5):
            r = await com_thread.run(lambda i=i: i * 2)
            results.append(r)
        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.anyio
    async def test_all_calls_same_thread(self, com_thread):
        """All COM calls must run on the same thread."""
        import threading

        ids = []
        for _ in range(3):
            tid = await com_thread.run(lambda: threading.current_thread().ident)
            ids.append(tid)
        assert len(set(ids)) == 1, "All calls should be on the same thread"
        assert ids[0] != threading.current_thread().ident, "Should be a different thread"

    def test_shutdown(self):
        thread = ComThread(init_com=False)
        assert thread._thread.is_alive()
        thread.shutdown()
        assert not thread._thread.is_alive()
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest unittests/desktop/test_com_thread.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement \_ComThread**

```python
# src/sapguimcp/backend/desktop/__init__.py
"""Desktop backend — SAP GUI Scripting (COM) implementation."""
```

```python
# src/sapguimcp/backend/desktop/_com_thread.py
"""Dedicated background thread for SAP GUI COM calls.

All COM calls must happen on the same apartment-threaded context.
This thread runs CoInitialize() once at startup and processes work
items from a queue. Async callers submit callables and await the
result via concurrent.futures.Future + asyncio.wrap_future.
"""
# pylint: disable=broad-exception-caught

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import queue
import threading
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ComThread:
    """Dedicated thread for all SAP GUI COM calls."""

    def __init__(self, *, init_com: bool = True) -> None:
        self._init_com = init_com
        self._queue: queue.Queue[tuple[Callable[[], Any], concurrent.futures.Future[Any]] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sapgui-com-worker")
        self._thread.start()

    def _run(self) -> None:
        """Worker loop: CoInitialize, process queue, CoUninitialize on exit."""
        if self._init_com:
            import pythoncom  # type: ignore[import-untyped]

            pythoncom.CoInitialize()
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                fn, cf_future = item
                try:
                    result = fn()
                    cf_future.set_result(result)
                except Exception as exc:
                    cf_future.set_exception(exc)
        except Exception:
            logger.exception("COM worker thread crashed")
        finally:
            if self._init_com:
                import pythoncom  # type: ignore[import-untyped]

                pythoncom.CoUninitialize()

    async def run(self, fn: Callable[[], T]) -> T:
        """Submit a callable to the COM thread and await its result."""
        cf_future: concurrent.futures.Future[T] = concurrent.futures.Future()
        self._queue.put((fn, cf_future))
        return await asyncio.wrap_future(cf_future)

    def shutdown(self) -> None:
        """Signal the worker thread to exit and wait for cleanup."""
        self._queue.put(None)
        self._thread.join(timeout=5)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest unittests/desktop/test_com_thread.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/backend/desktop/__init__.py src/sapguimcp/backend/desktop/_com_thread.py unittests/desktop/__init__.py unittests/desktop/test_com_thread.py
git commit -m "feat(desktop): add ComThread — dedicated COM worker thread for apartment threading"
```

---

### Task 2: VKey Mapping

**Files:**

- Create: `src/sapguimcp/backend/desktop/_key_mapping.py`
- Test: `unittests/desktop/test_key_mapping.py`

- [ ] **Step 1: Write tests**

```python
# unittests/desktop/test_key_mapping.py
"""Tests for VKey name → number mapping."""
from sapguimcp.backend.desktop._key_mapping import key_to_vkey


def test_enter():
    assert key_to_vkey("Enter") == 0


def test_f_keys():
    for i in range(1, 13):
        assert key_to_vkey(f"F{i}") == i


def test_shift_f_keys():
    for i in range(1, 13):
        assert key_to_vkey(f"Shift+F{i}") == 12 + i


def test_ctrl_f_keys():
    for i in range(1, 13):
        assert key_to_vkey(f"Ctrl+F{i}") == 24 + i


def test_escape_maps_to_f12():
    assert key_to_vkey("Escape") == 12


def test_case_insensitive():
    assert key_to_vkey("enter") == 0
    assert key_to_vkey("ENTER") == 0
    assert key_to_vkey("f5") == 5


def test_unknown_key_raises():
    import pytest

    with pytest.raises(KeyError, match="Delete"):
        key_to_vkey("Delete")
```

- [ ] **Step 2: Implement**

```python
# src/sapguimcp/backend/desktop/_key_mapping.py
"""Map key names to SAP GUI VKey numbers.

SAP GUI's SendVKey accepts a numeric VKey code (0-36+). This module maps
human-readable key names (as used by the MCP protocol's press_key method)
to those numbers.

Note: These are SAP VKeys, NOT Windows virtual key codes. "Escape" maps
to VKey 12 (F12/Cancel in SAP), not the literal Escape key.
"""
from __future__ import annotations

# Standard SAP VKey table (from SAP GUI Scripting API, Table GUI_FKEY)
_VKEY_MAP: dict[str, int] = {
    "enter": 0,
    **{f"f{i}": i for i in range(1, 13)},
    **{f"shift+f{i}": 12 + i for i in range(1, 13)},
    **{f"ctrl+f{i}": 24 + i for i in range(1, 13)},
    # SAP-conventional aliases (not literal OS keys — see module docstring)
    "escape": 12,       # F12 = Cancel in SAP
    "backspace": 3,     # F3 = Back in SAP
    "ctrl+s": 11,       # Ctrl+S = Save (VKey 11)
    "ctrl+shift+f3": 24,  # Ctrl+Shift+F3 mapped as Shift+F12
}


def key_to_vkey(key: str) -> int:
    """Convert a key name to a SAP VKey number.

    Args:
        key: Key name like "Enter", "F5", "Ctrl+F2", "Escape".
              Case-insensitive.

    Returns:
        The SAP VKey number.

    Raises:
        KeyError: If the key name is not recognized.
    """
    normalized = key.strip().lower()
    if normalized not in _VKEY_MAP:
        raise KeyError(f"Unknown key '{key}'. Known keys: Enter, F1-F12, Shift+F1-F12, Ctrl+F1-F12, Escape")
    return _VKEY_MAP[normalized]
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest unittests/desktop/test_key_mapping.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/backend/desktop/_key_mapping.py unittests/desktop/test_key_mapping.py
git commit -m "feat(desktop): add VKey name-to-number mapping"
```

---

### Task 3: Config + BackendManager changes

**Files:**

- Modify: `src/sapguimcp/models/config.py`
- Modify: `src/sapguimcp/backend/manager.py`
- Test: `unittests/desktop/test_manager_desktop.py`

- [ ] **Step 1: Write tests**

```python
# unittests/desktop/test_manager_desktop.py
"""Tests for BackendManager desktop backend selection."""
from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.backend.manager import BackendManager


def test_backend_type_accepts_desktop():
    """BackendManager should accept 'desktop' as a valid type."""
    manager = BackendManager(backend_type="desktop")
    assert manager.backend_type == "desktop"


def test_backend_type_rejects_invalid():
    with pytest.raises(ValueError, match="Unknown backend type"):
        BackendManager(backend_type="invalid")  # type: ignore[arg-type]
```

- [ ] **Step 2: Update config.py**

In `src/sapguimcp/models/config.py`, change:

```python
BackendType = Literal["webgui", "desktop"]
```

And update the field description:

```python
    backend_type: BackendType = Field(
        default="webgui",
        description="Backend type: 'webgui' (browser) or 'desktop' (SAP GUI COM)",
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `python -m pytest unittests/desktop/test_manager_desktop.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/sapguimcp/models/config.py unittests/desktop/test_manager_desktop.py
git commit -m "feat: extend BackendType to support 'desktop'"
```

---

## Chunk 2: DesktopBackend — Navigation Methods

### Task 4: DesktopBackend skeleton + login/enter_transaction

**Files:**

- Create: `src/sapguimcp/backend/desktop/__init__.py` (replace empty)
- Test: `unittests/desktop/test_desktop_backend.py`
- Test: `unittests/desktop/conftest.py`

- [ ] **Step 1: Create test fixtures**

```python
# unittests/desktop/conftest.py
"""Shared fixtures for desktop backend tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def make_mock_session(
    *,
    system_name: str = "S4U",
    client: str = "100",
    user: str = "TESTUSER",
    language: str = "EN",
    transaction: str = "SESSION_MANAGER",
    program: str = "SAPLSMTR_NAVIGATION",
    screen_number: int = 100,
    busy: bool = False,
) -> MagicMock:
    """Create a mock GuiSession with realistic info properties."""
    session = MagicMock()
    session.id = "/app/con[0]/ses[0]"
    session.info.system_name = system_name
    session.info.client = client
    session.info.user = user
    session.info.language = language
    session.info.transaction = transaction
    session.info.program = program
    session.info.screen_number = screen_number
    session.info.application_server = "sapserver01"
    session.info.response_time = 42
    session.info.round_trips = 3
    session.busy = busy

    # Main window mock
    wnd = MagicMock()
    wnd.text = "SAP Easy Access"

    # Statusbar mock
    sbar = MagicMock()
    sbar.text = ""
    sbar.message_type = ""

    # OkCode field mock
    okcd = MagicMock()
    okcd.text = ""

    # find_by_id routing
    def find_by_id(element_id: str, raise_error: bool = True) -> MagicMock | None:
        routes = {
            "wnd[0]": wnd,
            "wnd[0]/sbar": sbar,
            "wnd[0]/tbar[0]/okcd": okcd,
        }
        result = routes.get(element_id)
        if result is None and raise_error:
            raise Exception(f"Element not found: {element_id}")
        return result

    session.find_by_id = find_by_id
    return session


@pytest.fixture
def mock_session():
    """Provide a factory for mock GuiSession objects."""
    return make_mock_session
```

- [ ] **Step 2: Write backend tests**

```python
# unittests/desktop/test_desktop_backend.py
"""Tests for DesktopBackend — Navigation methods."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from unittests.desktop.conftest import make_mock_session


class TestDesktopBackendLogin:
    @pytest.mark.anyio
    async def test_login_calls_login_helper(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        with patch("sapguimcp.backend.desktop._login_mod.login", return_value=session) as mock_login:
            backend = DesktopBackend(com_thread=None)  # no real COM thread needed for this test
            backend._session = session  # skip actual login
            result = await backend.login("ignored", "user", "pass", "100", "EN")
            assert result.success is True
            assert result.user == "TESTUSER"


class TestDesktopBackendEnterTransaction:
    @pytest.mark.anyio
    async def test_enter_transaction(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session
        backend._com = MagicMock()  # mock ComThread
        backend._com.run = lambda fn: __import__("asyncio").coroutine(lambda: fn())()

        # Make com.run actually execute the function
        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.enter_transaction("SE16")
        assert result.success is True
        assert result.tcode == "SE16"


class TestDesktopBackendSessionStatus:
    @pytest.mark.anyio
    async def test_get_session_status_active(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.get_session_status()
        assert result.success is True
        assert result.status == "active"


class TestDesktopBackendPressKey:
    @pytest.mark.anyio
    async def test_press_enter(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        wnd = session.find_by_id("wnd[0]")

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.press_key("Enter")
        assert result.success is True
        assert result.key == "Enter"
        wnd.send_v_key.assert_called_once_with(0)

    @pytest.mark.anyio
    async def test_press_f5(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        wnd = session.find_by_id("wnd[0]")

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.press_key("F5")
        wnd.send_v_key.assert_called_once_with(5)
```

- [ ] **Step 3: Implement DesktopBackend skeleton**

```python
# src/sapguimcp/backend/desktop/__init__.py
"""Desktop backend — SAP GUI Scripting (COM) implementation of SapUiBackend.

Bridges the async MCP protocol to synchronous COM calls via a dedicated
ComThread. Methods that don't apply to desktop (JS, CSS selectors) raise
NotImplementedError.
"""
# pylint: disable=import-outside-toplevel,broad-exception-caught,too-many-public-methods

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.backend.desktop._key_mapping import key_to_vkey
from sapguimcp.backend.types import AriaSnapshot
from sapguimcp.models.base import PopupInfo, ToolResult
from sapguimcp.models.sap_results import (
    ButtonInfo,
    FieldInfo,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SessionStatus,
    StatusBarInfo,
    TableData,
    TransactionResult,
)

if TYPE_CHECKING:
    from sapguimcp.backend.protocol import CheckActivateResult
    from sapguimcp.models.alv_models import TableCellClickResult
    from sapguimcp.models.sap_results import (
        ClosePopupResult,
        DropdownFillResult,
        FillFormResult,
        FormFieldsResult,
        SessionInfo,
    )
    from sapguimcp.sapgui.components.session import GuiSession

import sapguimcp.sapgui._login as _login_mod

logger = logging.getLogger(__name__)


class DesktopBackend:
    """SapUiBackend implementation using SAP GUI Scripting (COM).

    Each instance wraps one GuiSession. All COM calls are dispatched
    to a shared ComThread for apartment-threading safety.
    """

    def __init__(self, com_thread: ComThread | None = None) -> None:
        self._com = com_thread or ComThread()
        self._session: GuiSession | None = None
        self._agent_bindings: dict[str, str] = {}  # session_id → agent_id

    def _require_session(self) -> GuiSession:
        """Return the current session or raise."""
        if self._session is None:
            raise RuntimeError("Not logged in — call login() first")
        return self._session

    # ---- SapNavigation ----

    async def login(
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
        session_id: str | None = None,
    ) -> LoginResult:
        """Log into SAP GUI desktop (url is ignored — uses SAP_CONNECTION_NAME)."""
        from sapguimcp.models.config import get_settings

        settings = get_settings()
        connection_name = settings.sap_connection_name
        if not connection_name:
            return LoginResult(success=False, error="SAP_CONNECTION_NAME not configured")

        try:
            session = await self._com.run(
                lambda: _login_mod.login(
                    connection_name=connection_name,
                    client=client,
                    user=username,
                    password=password,
                    language=language,
                )
            )
            self._session = session
            user_name = await self._com.run(lambda: str(session.info.user))
            return LoginResult(success=True, user=user_name)
        except Exception as e:
            return LoginResult(success=False, error=str(e))

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        """Navigate to a transaction code."""
        session = self._require_session()

        def _enter() -> tuple[str, str]:
            okcd = session.find_by_id("wnd[0]/tbar[0]/okcd")
            cast(Any, okcd).text = f"/n{tcode}"
            wnd = session.find_by_id("wnd[0]")
            cast(Any, wnd).send_v_key(0)
            return str(cast(Any, session.find_by_id("wnd[0]")).text), str(session.info.transaction)

        try:
            title, actual_tcode = await self._com.run(_enter)
            return TransactionResult(
                success=True,
                tcode=tcode,
                page_title=title,
            )
        except Exception as e:
            return TransactionResult(success=False, tcode=tcode, error=str(e))

    async def get_session_status(self) -> SessionStatus:
        """Check whether the SAP session is logged in and responsive."""
        session = self._require_session()
        try:
            user = await self._com.run(lambda: str(session.info.user))
            return SessionStatus(success=True, status="active", message=f"Logged in as {user}")
        except Exception:
            return SessionStatus(success=True, status="unknown", message="Session not responsive")

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        """Wait until the session is no longer busy."""
        import asyncio

        session = self._require_session()
        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
        while asyncio.get_event_loop().time() < deadline:
            busy = await self._com.run(lambda: bool(session.busy))
            if not busy:
                return
            await asyncio.sleep(0.2)

    async def bring_to_front(self) -> None:
        """Bring the SAP GUI window to the foreground."""
        session = self._require_session()
        await self._com.run(lambda: (
            cast(Any, session.find_by_id("wnd[0]")).iconify(),
            cast(Any, session.find_by_id("wnd[0]")).restore(),
        ))

    async def wait(self, timeout_ms: int = 200) -> None:
        """Wait for a fixed duration."""
        import asyncio
        await asyncio.sleep(timeout_ms / 1000)

    async def start_keepalive(self, interval_seconds: int = 300) -> None:
        """No-op — desktop sessions don't time out like WebGUI."""

    async def stop_keepalive(self) -> bool:
        """No-op. Returns False (no keepalive was running)."""
        return False

    async def open_new_session(self, tcode: str) -> tuple[str | None, int, str | None]:
        """Open a transaction in a new session/mode (/o)."""
        session = self._require_session()

        def _open() -> tuple[str | None, int, str | None]:
            session.create_session()
            import time
            time.sleep(1)
            conn_com = session.com.Parent
            count = conn_com.Children.Count
            if count < 2:
                return None, count, None
            new_ses_com = conn_com.Children(count - 1)
            new_id = str(new_ses_com.Id)
            # Enter transaction in new session
            new_ses_com.FindById("wnd[0]/tbar[0]/okcd").Text = f"/n{tcode}"
            new_ses_com.FindById("wnd[0]").SendVKey(0)
            title = str(new_ses_com.FindById("wnd[0]").Text)
            return new_id, count, title

        try:
            sid, count, title = await self._com.run(_open)
            return sid, count, title
        except Exception as e:
            logger.error("Failed to open new session: %s", e)
            return None, 1, None

    async def list_sessions(self) -> list[SessionInfo]:
        """List all sessions in the current connection."""
        from sapguimcp.models.sap_results import SessionInfo as SInfo

        session = self._require_session()

        def _list() -> list[dict[str, Any]]:
            conn = session.com.Parent
            result = []
            for i in range(conn.Children.Count):
                ses = conn.Children(i)
                result.append({
                    "session_id": str(ses.Id),
                    "tcode": str(ses.Info.Transaction),
                    "title": str(ses.FindById("wnd[0]").Text),
                    "is_primary": i == 0,
                    "agent_id": self._agent_bindings.get(str(ses.Id)),
                })
            return result

        items = await self._com.run(_list)
        return [SInfo(**item) for item in items]

    async def close_session(self, session_id: str) -> bool:
        """Close a session by ID."""
        session = self._require_session()

        def _close() -> bool:
            conn = session.com.Parent
            try:
                conn.CloseSession(session_id)
                return True
            except Exception:
                return False

        return await self._com.run(_close)

    async def bind_session(self, session_id: str, agent_id: str) -> str | None:
        """Bind an agent to a session."""
        prev = self._agent_bindings.get(session_id)
        self._agent_bindings[session_id] = agent_id
        return prev

    async def release_session(self, session_id: str) -> str | None:
        """Release agent binding from a session."""
        return self._agent_bindings.pop(session_id, None)

    async def has_session(self, session_id: str) -> bool:
        """Check whether a session exists."""
        session = self._require_session()

        def _check() -> bool:
            conn = session.com.Parent
            for i in range(conn.Children.Count):
                if str(conn.Children(i).Id) == session_id:
                    return True
            return False

        return await self._com.run(_check)

    async def is_page_closed(self) -> bool:
        """Check whether the session has been closed."""
        if self._session is None:
            return True
        try:
            await self._com.run(lambda: self._session.info.user)  # type: ignore[union-attr]
            return False
        except Exception:
            return True

    async def close_page(self) -> None:
        """Close the connection."""
        if self._session is None:
            return
        try:
            await self._com.run(lambda: self._session.com.Parent.CloseConnection())  # type: ignore[union-attr]
        except Exception:
            pass
        self._session = None

    def get_session_token(self) -> str:
        """Return opaque token identifying the session."""
        if self._session is None:
            return ""
        return str(self._session.id)

    # ---- SapUiInspection ----

    async def get_status_bar(self) -> StatusBarInfo:
        """Read the SAP status bar."""
        session = self._require_session()

        def _read() -> tuple[str, str]:
            sbar = session.find_by_id("wnd[0]/sbar")
            return str(cast(Any, sbar).text), str(cast(Any, sbar).message_type)

        text, msg_type = await self._com.run(_read)
        bar_type = msg_type if msg_type in ("S", "E", "W", "I", "A") else "none"
        return StatusBarInfo(success=True, type=bar_type, message=text)

    async def get_screen_info(self) -> ScreenInfo:
        """Get technical screen information."""
        session = self._require_session()

        def _read() -> dict[str, Any]:
            info = session.info
            wnd = session.find_by_id("wnd[0]")
            return {
                "transaction": str(info.transaction),
                "title": str(cast(Any, wnd).text),
                "program": str(info.program),
                "dynpro": str(info.screen_number),
            }

        data = await self._com.run(_read)
        return ScreenInfo(success=True, url="desktop://sap", **data)

    async def get_screen_text(self, include_dropdown_options: bool = False) -> ScreenText:
        """Get readable text from the current screen via dump_tree."""
        session = self._require_session()

        def _read() -> dict[str, Any]:
            wnd = session.find_by_id("wnd[0]")
            title = str(cast(Any, wnd).text)
            sbar = session.find_by_id("wnd[0]/sbar")
            sbar_text = str(cast(Any, sbar).text)
            tree = cast(Any, wnd).dump_tree(max_depth=3)

            labels, buttons, tabs, content = [], [], [], []
            for elem in _flatten_tree(tree):
                t = elem.type_as_number
                txt = elem.text.strip()
                if not txt:
                    continue
                if t == 30:  # GuiLabel
                    labels.append(txt)
                elif t == 40:  # GuiButton
                    buttons.append(txt)
                elif t == 91:  # GuiTab
                    tabs.append(txt)
                else:
                    content.append(txt)

            return {
                "title": title,
                "status_bar": sbar_text or None,
                "tabs": tabs,
                "labels": list(dict.fromkeys(labels)),
                "buttons": list(dict.fromkeys(buttons)),
                "table_headers": [],
                "main_content": content,
            }

        data = await self._com.run(_read)
        return ScreenText(success=True, **data)

    async def discover_fields(self) -> list[FieldInfo]:
        """Discover input fields on the current screen."""
        session = self._require_session()

        def _discover() -> list[dict[str, Any]]:
            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            fields = []
            input_types = {31, 32, 33, 34}  # txt, ctxt, pwd, cmb
            for elem in _flatten_tree(tree):
                if elem.type_as_number in input_types:
                    fields.append({
                        "id": elem.id,
                        "name": elem.name,
                        "label": None,
                        "type": elem.type,
                        "selector": elem.id,
                        "value": elem.text,
                    })
            return fields

        items = await self._com.run(_discover)
        return [FieldInfo(**item) for item in items]

    async def get_form_fields(self, *, include_dropdown_options: bool = False) -> FormFieldsResult:
        """Detect form fields with their current values."""
        from sapguimcp.models.sap_results import FormFieldsResult

        fields = await self.discover_fields()
        return FormFieldsResult(success=True, fields=fields, field_count=len(fields))

    async def discover_buttons(self) -> list[ButtonInfo]:
        """Discover clickable buttons on the current screen."""
        session = self._require_session()

        def _discover() -> list[dict[str, str | None]]:
            wnd = session.find_by_id("wnd[0]")
            tree = cast(Any, wnd).dump_tree(max_depth=3)
            buttons = []
            for elem in _flatten_tree(tree):
                if elem.type_as_number == 40 and elem.text.strip():  # GuiButton
                    buttons.append({"label": elem.text.strip(), "id": elem.id, "selector": elem.id})
            return buttons

        items = await self._com.run(_discover)
        return [ButtonInfo(**item) for item in items]

    async def get_snapshot(self) -> AriaSnapshot:
        """Get a tree dump as an AriaSnapshot-like string."""
        session = self._require_session()

        def _dump() -> str:
            wnd = session.find_by_id("wnd[0]")
            tree = cast(Any, wnd).dump_tree(max_depth=5)
            lines = []
            for elem in _flatten_tree(tree):
                indent = "  " * elem.id.count("/")
                lines.append(f"{indent}{elem.type}[{elem.name}]: {elem.text!r}")
            return "\n".join(lines)

        text = await self._com.run(_dump)
        return AriaSnapshot(text)

    async def take_screenshot(self) -> bytes:
        """Take a screenshot of the SAP GUI window."""
        session = self._require_session()

        def _screenshot() -> bytes:
            import os
            import tempfile

            wnd = session.find_by_id("wnd[0]")
            tmp = os.path.join(tempfile.gettempdir(), "sapgui_screenshot.png")
            cast(Any, wnd).hard_copy(tmp, 2)  # 2 = PNG
            with open(tmp, "rb") as f:
                data = f.read()
            os.unlink(tmp)
            return data

        return await self._com.run(_screenshot)

    async def read_table(
        self,
        start_row: int = 1,
        end_row: int | None = None,
        max_rows: int = 100,
    ) -> TableData:
        """Read data from an ALV grid or table control."""
        session = self._require_session()

        def _read() -> dict[str, Any]:
            from sapguimcp.sapgui.components.grid import GuiGridView
            from sapguimcp.sapgui.components.table import GuiTableControl

            # Find grid or table in the user area
            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            grid_id = None
            for elem in _flatten_tree(tree):
                if elem.type_as_number == 122 or elem.type_as_number == 80:
                    grid_id = elem.id
                    break

            if grid_id is None:
                return {"headers": [], "rows": [], "total_rows": 0, "start_row": 1}

            grid = session.find_by_id(grid_id)
            if isinstance(grid, GuiGridView):
                row_count = cast(Any, grid).row_count
                col_order = cast(Any, grid).column_order
                headers = []
                for ci in range(col_order.Count):
                    col_name = str(col_order(ci))
                    headers.append(col_name)

                actual_end = min(end_row or (start_row + max_rows - 1), row_count)
                rows = []
                from sapguimcp.models.sap_results import TableRow
                for ri in range(start_row - 1, actual_end):
                    data = {}
                    for col_name in headers:
                        data[col_name] = str(cast(Any, grid).get_cell_value(ri, col_name))
                    rows.append({"row": ri + 1, "data": data})

                return {
                    "headers": headers,
                    "rows": rows,
                    "total_rows": row_count,
                    "start_row": start_row,
                    "end_row": actual_end,
                }

            return {"headers": [], "rows": [], "total_rows": 0, "start_row": 1}

        data = await self._com.run(_read)
        from sapguimcp.models.sap_results import TableRow
        rows = [TableRow(**r) for r in data.pop("rows", [])]
        return TableData(success=True, rows=rows, **data)

    async def click_table_cell(
        self, row: int, column: int | str, action: str = "click"
    ) -> TableCellClickResult:
        """Click a cell in an ALV grid table."""
        from sapguimcp.models.alv_models import TableCellClickResult

        session = self._require_session()

        def _click() -> None:
            # Find grid
            from sapguimcp.sapgui.components.grid import GuiGridView

            usr = session.find_by_id("wnd[0]/usr")
            tree = cast(Any, usr).dump_tree(max_depth=3)
            for elem in _flatten_tree(tree):
                if elem.type_as_number == 122:
                    grid = session.find_by_id(elem.id)
                    if isinstance(grid, GuiGridView):
                        col_name = str(column)
                        if isinstance(column, int):
                            col_order = cast(Any, grid).column_order
                            col_name = str(col_order(column))
                        if action == "double_click":
                            cast(Any, grid).double_click(row - 1, col_name)
                        else:
                            cast(Any, grid).click(row - 1, col_name)
                        return
            raise ValueError("No ALV grid found on screen")

        try:
            await self._com.run(_click)
            return TableCellClickResult(success=True, row=row, column=str(column))
        except Exception as e:
            return TableCellClickResult(success=False, row=row, column=str(column), error=str(e))

    async def get_dropdown_options(self, label: str) -> list[str]:
        """Get options from a dropdown (not yet implemented — needs element finder)."""
        return []

    async def get_page_title(self) -> str:
        """Get the current window title."""
        session = self._require_session()
        return await self._com.run(lambda: str(cast(Any, session.find_by_id("wnd[0]")).text))

    # ---- SapUiPrimitives (only press_key in Phase 1) ----

    async def press_key(self, key: str) -> KeyboardResult:
        """Send a keyboard shortcut via SAP VKey."""
        session = self._require_session()
        vkey = key_to_vkey(key)

        def _press() -> tuple[str, str, str]:
            wnd = session.find_by_id("wnd[0]")
            cast(Any, wnd).send_v_key(vkey)
            title = str(cast(Any, session.find_by_id("wnd[0]")).text)
            sbar = session.find_by_id("wnd[0]/sbar")
            return title, str(cast(Any, sbar).text), str(cast(Any, sbar).message_type)

        try:
            title, sbar_text, sbar_type = await self._com.run(_press)
            return KeyboardResult(
                success=True,
                key=key,
                page_title=title,
                status_bar_read=True,
                status_bar_type=sbar_type if sbar_type in ("S", "E", "W", "I", "A") else None,
                status_bar_message=sbar_text,
            )
        except KeyError:
            return KeyboardResult(success=False, key=key, error=f"Unknown key: {key}")
        except Exception as e:
            return KeyboardResult(success=False, key=key, error=str(e))

    # ---- Stub methods (Phase 2 + 3) ----

    async def fill_field(self, label: str, value: str) -> None:
        raise NotImplementedError("fill_field not yet implemented — Phase 2")

    async def fill_main_input(self, value: str, labels: list[str]) -> bool:
        raise NotImplementedError("fill_main_input not yet implemented — Phase 2")

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult:
        raise NotImplementedError("fill_form not yet implemented — Phase 2")

    async def fill_grid_cell(self, row: int, column: int | str, value: str) -> None:
        raise NotImplementedError("fill_grid_cell not yet implemented — Phase 2")

    async def click_button(self, label: str) -> None:
        raise NotImplementedError("click_button not yet implemented — Phase 2")

    async def click_tab(self, label: str) -> None:
        raise NotImplementedError("click_tab not yet implemented — Phase 2")

    async def type_text(self, text: str) -> None:
        raise NotImplementedError("type_text not yet implemented — Phase 2")

    async def set_checkbox(self, label: str, checked: bool) -> None:
        raise NotImplementedError("set_checkbox not yet implemented — Phase 2")

    async def set_radio_button(self, label: str) -> None:
        raise NotImplementedError("set_radio_button not yet implemented — Phase 2")

    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult:
        raise NotImplementedError("select_dropdown not yet implemented — Phase 2")

    async def focus_and_type(self, accessible_name: str, text: str, delay_ms: int = 0) -> bool:
        raise NotImplementedError("focus_and_type not yet implemented — Phase 2")

    async def fill_element_by_locator(self, locator: str, value: str, delay_ms: int = 30) -> bool:
        raise NotImplementedError("CSS selectors not supported on desktop SAP GUI")

    async def click_element(self, selector: str) -> bool:
        raise NotImplementedError("CSS selectors not supported on desktop SAP GUI")

    def load_js(self, filename: str) -> str:
        raise NotImplementedError("JavaScript not supported on desktop SAP GUI")

    async def evaluate_javascript(self, script: str, arg: Any = None) -> Any:
        raise NotImplementedError("JavaScript not supported on desktop SAP GUI")

    # ---- SapEditor stubs (Phase 3) ----

    async def read_editor_source(self) -> str | None:
        raise NotImplementedError("read_editor_source not yet implemented — Phase 3")

    async def replace_editor_source(self, code: str) -> bool:
        raise NotImplementedError("replace_editor_source not yet implemented — Phase 3")

    async def check_and_activate(self) -> CheckActivateResult:
        raise NotImplementedError("check_and_activate not yet implemented — Phase 3")

    async def dismiss_language_dialog(self) -> None:
        raise NotImplementedError("dismiss_language_dialog not yet implemented — Phase 3")

    # ---- SapPopup stubs (Phase 3) ----

    async def check_popup(self) -> PopupInfo | None:
        raise NotImplementedError("check_popup not yet implemented — Phase 3")

    async def dismiss_popup(
        self, button_label: str | None = None, use_close_button: bool = False
    ) -> ClosePopupResult:
        raise NotImplementedError("dismiss_popup not yet implemented — Phase 3")


def _flatten_tree(elements: list[Any]) -> list[Any]:
    """Flatten a nested ElementInfo tree into a flat list."""
    result = []
    for elem in elements:
        result.append(elem)
        if elem.children:
            result.extend(_flatten_tree(elem.children))
    return result
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest unittests/desktop/test_desktop_backend.py -v`

- [ ] **Step 5: Update BackendManager**

Add the desktop branch to `src/sapguimcp/backend/manager.py`:

In `get_or_create`, after the webgui block, add:

```python
        elif self.backend_type == "desktop":
            from sapguimcp.backend.desktop import DesktopBackend
            from sapguimcp.backend.desktop._com_thread import ComThread

            session_key = session or "s1"
            cached = self._backends.get(session_key)
            if cached is not None:
                return cached
            if not hasattr(self, "_com_thread"):
                self._com_thread = ComThread()
            backend = DesktopBackend(com_thread=self._com_thread)
            self._backends[session_key] = backend
            return backend
```

In `close`, add:

```python
        elif self.backend_type == "desktop":
            if hasattr(self, "_com_thread"):
                self._com_thread.shutdown()
```

- [ ] **Step 6: Run all tests**

Run: `python -m pytest unittests/desktop/ unittests/sapgui/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Format and lint**

```bash
python -m isort src/sapguimcp/backend/desktop/ unittests/desktop/ --profile black
python -m black src/sapguimcp/backend/desktop/ unittests/desktop/ --line-length 120
tox -e type_check
tox -e linting
```

- [ ] **Step 8: Commit**

```bash
git add src/sapguimcp/backend/desktop/ src/sapguimcp/backend/manager.py unittests/desktop/
git commit -m "feat(desktop): add DesktopBackend with Navigation + Inspection + press_key (Phase 1 MVP)"
```

---
