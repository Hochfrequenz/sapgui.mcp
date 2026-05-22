# Multi-Session Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable parallel sub-agents to work in isolated SAP sessions via browser tabs.

**Architecture:** Add SessionRegistry to track session-to-page mappings with event-driven cleanup. All browser-interacting tools get optional `session` parameter. New tools `sap_session_open/list/close` manage session lifecycle.

**Tech Stack:** Python 3.11+, Pydantic v2, Playwright, pytest, pytest-anyio

**Design Doc:** `docs/plans/2026-01-14-multi-session-support-design.md`

---

## Task 1: SessionId Type Alias

**Files:**

- Modify: `src/sapguimcp/models/base.py`
- Modify: `src/sapguimcp/models/__init__.py`
- Test: `unittests/test_models.py`

**Step 1: Write the failing test**

Add to `unittests/test_models.py`:

```python
class TestSessionIdValidation:
    """Tests for SessionId type validation."""

    def test_valid_session_id(self) -> None:
        """Test valid session ID format."""
        from sapguimcp.models import SessionId
        from pydantic import TypeAdapter

        adapter = TypeAdapter(SessionId)
        assert adapter.validate_python("s1") == "s1"
        assert adapter.validate_python("s123") == "s123"

    def test_session_id_normalized_to_lowercase(self) -> None:
        """Test that session IDs are normalized to lowercase."""
        from sapguimcp.models import SessionId
        from pydantic import TypeAdapter

        adapter = TypeAdapter(SessionId)
        assert adapter.validate_python("S1") == "s1"
        assert adapter.validate_python("S99") == "s99"

    def test_invalid_session_id_rejected(self) -> None:
        """Test that invalid session IDs raise ValidationError."""
        from sapguimcp.models import SessionId
        from pydantic import TypeAdapter, ValidationError

        adapter = TypeAdapter(SessionId)
        with pytest.raises(ValidationError):
            adapter.validate_python("invalid")
        with pytest.raises(ValidationError):
            adapter.validate_python("1")  # Must start with 's'
        with pytest.raises(ValidationError):
            adapter.validate_python("session1")  # Must be 's' + digits only
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_models.py::TestSessionIdValidation -v`
Expected: FAIL with "cannot import name 'SessionId'"

**Step 3: Write minimal implementation**

Add to `src/sapguimcp/models/base.py` after the TCode definition (~line 12):

```python
# Session ID type: lowercase 's' followed by digits (s1, s2, s3, ...)
_SESSION_ID_PATTERN = r"^s\d+$"
SessionId = Annotated[str, BeforeValidator(str.lower), Field(pattern=_SESSION_ID_PATTERN)]
```

**Step 4: Export SessionId**

Add to `src/sapguimcp/models/base.py` `__all__`:

```python
__all__ = [
    # ... existing exports
    "SessionId",
]
```

Add to `src/sapguimcp/models/__init__.py`:

```python
from sapguimcp.models.base import TCODE_PATTERN, PopupButton, PopupInfo, PopupType, SessionId, TCode, ToolResult
```

And add `"SessionId"` to the `__all__` list in `__init__.py`.

**Step 5: Run test to verify it passes**

Run: `pytest unittests/test_models.py::TestSessionIdValidation -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/sapguimcp/models/base.py src/sapguimcp/models/__init__.py unittests/test_models.py
git commit -m "feat(models): add SessionId type alias with validation"
```

---

## Task 2: Session Result Models

**Files:**

- Modify: `src/sapguimcp/models/sap_results.py`
- Modify: `src/sapguimcp/models/__init__.py`
- Test: `unittests/test_models.py`

**Step 1: Write the failing test**

Add to `unittests/test_models.py`:

```python
class TestSessionModels:
    """Tests for session management result models."""

    def test_session_info_creation(self) -> None:
        """Test SessionInfo model creation."""
        from sapguimcp.models import SessionInfo

        info = SessionInfo(session_id="s1", tcode="VA01", title="Create Sales Order", is_primary=True)
        assert info.session_id == "s1"
        assert info.tcode == "VA01"
        assert info.is_primary is True

    def test_session_open_result_success(self) -> None:
        """Test SessionOpenResult for successful session creation."""
        from sapguimcp.models import SessionOpenResult

        result = SessionOpenResult(session_id="s2", tcode="MM01", session_count=2)
        assert result.success is True
        assert result.session_id == "s2"
        assert result.session_count == 2

    def test_session_open_result_failure(self) -> None:
        """Test SessionOpenResult.failure() factory."""
        from sapguimcp.models import SessionOpenResult

        result = SessionOpenResult.failure("SAP session limit reached")
        assert result.success is False
        assert "limit" in result.error

    def test_session_list_result(self) -> None:
        """Test SessionListResult with multiple sessions."""
        from sapguimcp.models import SessionInfo, SessionListResult

        result = SessionListResult(sessions=[
            SessionInfo(session_id="s1", is_primary=True),
            SessionInfo(session_id="s2", tcode="VA01"),
        ])
        assert result.session_count == 2
        assert result.sessions[0].is_primary is True

    def test_session_close_result(self) -> None:
        """Test SessionCloseResult model."""
        from sapguimcp.models import SessionCloseResult

        result = SessionCloseResult(session_id="s2", remaining_sessions=1)
        assert result.success is True
        assert result.session_id == "s2"
        assert result.remaining_sessions == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_models.py::TestSessionModels -v`
Expected: FAIL with "cannot import name 'SessionInfo'"

**Step 3: Write minimal implementation**

Add to `src/sapguimcp/models/sap_results.py` after existing imports:

```python
from sapguimcp.models.base import PopupInfo, SessionId, TCode, ToolResult
```

Then add after `SessionStatus` class (~line 77):

```python
class SessionInfo(BaseModel):
    """Information about a single SAP session."""

    session_id: str = Field(description="Session identifier (e.g., 's1', 's2')")
    tcode: str | None = Field(default=None, description="Current transaction code (e.g., 'VA01')")
    title: str | None = Field(default=None, description="Current screen title")
    is_primary: bool = Field(default=False, description="True if this is the primary session ('s1')")


class SessionOpenResult(ToolResult):
    """Result from sap_session_open tool."""

    session_id: str | None = Field(
        default=None,
        description="ID of the new session (e.g., 's2'). Pass to other tools via session= parameter."
    )
    tcode: str | None = Field(default=None, description="Transaction opened in new session, if requested")
    session_count: int = Field(default=1, ge=1, description="Total active sessions after opening")


class SessionListResult(ToolResult):
    """Result from sap_session_list tool."""

    sessions: list[SessionInfo] = Field(
        default_factory=list,
        description="All active SAP sessions with their current state"
    )

    @property
    def session_count(self) -> int:
        """Number of active sessions."""
        return len(self.sessions)


class SessionCloseResult(ToolResult):
    """Result from sap_session_close tool."""

    session_id: str | None = Field(
        default=None,
        description="ID of the session that was closed (e.g., 's2')"
    )
    remaining_sessions: int = Field(default=0, ge=0, description="Sessions still active after closing")
```

**Step 4: Export new models**

Add to `src/sapguimcp/models/sap_results.py` imports in `__init__.py` and `__all__`:

- `SessionInfo`
- `SessionOpenResult`
- `SessionListResult`
- `SessionCloseResult`

**Step 5: Run test to verify it passes**

Run: `pytest unittests/test_models.py::TestSessionModels -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/sapguimcp/models/sap_results.py src/sapguimcp/models/__init__.py unittests/test_models.py
git commit -m "feat(models): add session management result models"
```

---

## Task 3: SessionRegistry Core (Unit Tests)

**Files:**

- Create: `src/sapguimcp/models/session_registry.py`
- Modify: `src/sapguimcp/models/__init__.py`
- Create: `unittests/test_session_registry.py`

**Step 1: Write the failing tests**

Create `unittests/test_session_registry.py`:

```python
"""Unit tests for SessionRegistry with mocked Page objects."""

from unittest.mock import MagicMock, AsyncMock
import pytest

from sapguimcp.models.session_registry import SessionRegistry


class TestSessionRegistryUnit:
    """Unit tests for SessionRegistry without real browser."""

    def test_register_assigns_sequential_ids(self) -> None:
        """Test that register() assigns s1, s2, s3 sequentially."""
        registry = SessionRegistry()

        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()

        sid1 = registry.register(page1)
        sid2 = registry.register(page2)

        assert sid1 == "s1"
        assert sid2 == "s2"

    def test_get_page_returns_correct_page(self) -> None:
        """Test that get_page returns the registered page."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        retrieved = registry.get_page(sid)

        assert retrieved is page

    def test_get_page_none_returns_primary(self) -> None:
        """Test that get_page(None) returns s1 (primary session)."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        registry.register(page)  # s1
        retrieved = registry.get_page(None)

        assert retrieved is page

    def test_get_page_unknown_session_raises(self) -> None:
        """Test that get_page with unknown session raises ValueError."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()
        registry.register(page)  # s1

        with pytest.raises(ValueError, match="Session 's99' not found"):
            registry.get_page("s99")

    def test_get_page_closed_page_raises_and_cleans_up(self) -> None:
        """Test that accessing closed page raises and removes from registry."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)

        # Simulate page being closed
        page.is_closed.return_value = True

        with pytest.raises(ValueError, match="expired"):
            registry.get_page(sid)

        # Should be cleaned up
        assert sid not in registry._sessions

    def test_unregister_removes_session(self) -> None:
        """Test that unregister removes session from registry."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        assert sid in registry._sessions

        registry.unregister(sid)
        assert sid not in registry._sessions

    def test_list_sessions_returns_all_active(self) -> None:
        """Test list_sessions returns all registered sessions."""
        registry = SessionRegistry()

        for _ in range(3):
            page = MagicMock()
            page.is_closed.return_value = False
            page.on = MagicMock()
            registry.register(page)

        sessions = registry.list_sessions()
        assert len(sessions) == 3
        assert set(sessions) == {"s1", "s2", "s3"}

    def test_primary_session_is_always_s1(self) -> None:
        """Test that primary_session property returns s1."""
        registry = SessionRegistry()
        assert registry.primary_session == "s1"

    def test_has_session(self) -> None:
        """Test has_session check."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        registry.register(page)

        assert registry.has_session("s1") is True
        assert registry.has_session("s2") is False
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_session_registry.py -v`
Expected: FAIL with "No module named 'sapguimcp.models.session_registry'"

**Step 3: Write minimal implementation**

Create `src/sapguimcp/models/session_registry.py`:

```python
"""Session registry for tracking SAP browser sessions."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

__all__ = ["SessionRegistry"]

logger = logging.getLogger(__name__)


class SessionRegistry:
    """Tracks SAP sessions with automatic lifecycle management.

    Each session maps to a browser tab (Playwright Page). The registry:
    - Assigns sequential IDs (s1, s2, s3...)
    - Auto-unregisters when tabs close (via event listener)
    - Validates sessions are still open on access
    """

    def __init__(self) -> None:
        self._sessions: dict[str, "Page"] = {}
        self._counter: int = 0
        self._page_to_session: dict["Page", str] = {}

    @property
    def primary_session(self) -> str:
        """Primary session ID (always 's1')."""
        return "s1"

    def register(self, page: "Page") -> str:
        """Register a page and return its session ID.

        Args:
            page: Playwright Page object (browser tab)

        Returns:
            Session ID (e.g., 's1', 's2')
        """
        self._counter += 1
        session_id = f"s{self._counter}"
        self._sessions[session_id] = page
        self._page_to_session[page] = session_id

        # Auto-unregister when page closes
        page.on("close", lambda: self._on_page_closed(page))

        logger.info(f"Registered session '{session_id}'")
        return session_id

    def unregister(self, session_id: str) -> None:
        """Remove a session from the registry.

        Args:
            session_id: Session to remove
        """
        if session_id in self._sessions:
            page = self._sessions.pop(session_id)
            self._page_to_session.pop(page, None)
            logger.info(f"Unregistered session '{session_id}'")

    def get_page(self, session_id: str | None) -> "Page":
        """Get the Page for a session.

        Args:
            session_id: Session ID, or None for primary session ('s1')

        Returns:
            Playwright Page object

        Raises:
            ValueError: If session not found or page is closed
        """
        sid = session_id or "s1"

        if sid not in self._sessions:
            available = ", ".join(sorted(self._sessions.keys())) or "(none)"
            raise ValueError(
                f"Session '{sid}' not found. Active: {available}. "
                "Use sap_session_list() to see sessions."
            )

        page = self._sessions[sid]
        if page.is_closed():
            # Clean up stale entry
            self._sessions.pop(sid, None)
            self._page_to_session.pop(page, None)
            raise ValueError(
                f"Session '{sid}' expired (tab closed). "
                "Use sap_session_open() to create a new session."
            )

        return page

    def has_session(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    def list_sessions(self) -> list[str]:
        """List all registered session IDs."""
        return list(self._sessions.keys())

    def _on_page_closed(self, page: "Page") -> None:
        """Handle page close event - auto-unregister."""
        if page in self._page_to_session:
            session_id = self._page_to_session.pop(page)
            self._sessions.pop(session_id, None)
            logger.info(f"Session '{session_id}' auto-unregistered (page closed)")

    async def setup_context_listeners(self, context: "BrowserContext") -> None:
        """Attach event listeners to browser context.

        Call once after context creation to enable auto-cleanup.
        """
        context.on("page", self._on_page_created)

    def _on_page_created(self, page: "Page") -> None:
        """Handle new page creation - attach close listener."""
        page.on("close", lambda: self._on_page_closed(page))
```

**Step 4: Run test to verify it passes**

Run: `pytest unittests/test_session_registry.py -v`
Expected: PASS

**Step 5: Export from models package**

Add to `src/sapguimcp/models/__init__.py`:

```python
from sapguimcp.models.session_registry import SessionRegistry
```

Add `"SessionRegistry"` to `__all__`.

**Step 6: Commit**

```bash
git add src/sapguimcp/models/session_registry.py src/sapguimcp/models/__init__.py unittests/test_session_registry.py
git commit -m "feat(models): add SessionRegistry with unit tests"
```

---

## Task 4: Integrate SessionRegistry into BrowserManager

**Files:**

- Modify: `src/sapguimcp/models/browser.py`
- Test: `unittests/test_session_registry.py`

**Step 1: Write the failing test**

Add to `unittests/test_session_registry.py`:

```python
class TestBrowserManagerSessionIntegration:
    """Tests for BrowserManager + SessionRegistry integration."""

    def test_browser_manager_has_registry(self) -> None:
        """Test that BrowserManager exposes session registry."""
        from sapguimcp.models.browser import BrowserManager

        manager = BrowserManager()
        assert hasattr(manager, 'registry')
        assert manager.registry is not None

    def test_browser_manager_get_session_page(self) -> None:
        """Test BrowserManager.get_session_page() method."""
        from sapguimcp.models.browser import BrowserManager
        from unittest.mock import MagicMock

        manager = BrowserManager()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        manager.registry.register(page)

        retrieved = manager.get_session_page("s1")
        assert retrieved is page

        retrieved_default = manager.get_session_page(None)
        assert retrieved_default is page
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_session_registry.py::TestBrowserManagerSessionIntegration -v`
Expected: FAIL (no `registry` attribute or `get_session_page` method)

**Step 3: Modify BrowserManager**

In `src/sapguimcp/models/browser.py`, add import:

```python
from sapguimcp.models.session_registry import SessionRegistry
```

Modify `BrowserManager.__init__`:

```python
def __init__(self, settings: Optional[SapGuiSettings] = None) -> None:
    self._settings = settings
    self._playwright: Optional[Playwright] = None
    self._browser: Optional[Browser] = None
    self._context: Optional[BrowserContext] = None
    self._pages: dict[str, Page] = {}  # Legacy - keep for compatibility during migration
    self._default_page_name = "sap"
    self._initialized = False
    self._registry = SessionRegistry()  # NEW

@property
def registry(self) -> SessionRegistry:
    """Session registry for multi-session support."""
    return self._registry

def get_session_page(self, session_id: str | None) -> Page:
    """Get page for a session ID.

    Args:
        session_id: Session ID or None for primary session

    Returns:
        Playwright Page for the session
    """
    return self._registry.get_page(session_id)
```

**Step 4: Run test to verify it passes**

Run: `pytest unittests/test_session_registry.py::TestBrowserManagerSessionIntegration -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/models/browser.py unittests/test_session_registry.py
git commit -m "feat(browser): integrate SessionRegistry into BrowserManager"
```

---

## Task 5: Session Tools (sap_session_open, sap_session_list, sap_session_close)

**Files:**

- Create: `src/sapguimcp/tools/session_tools.py`
- Modify: `src/sapguimcp/server.py` (import new tools)
- Test: `unittests/test_session_tools.py`

**Step 1: Write the failing tests**

Create `unittests/test_session_tools.py`:

```python
"""Unit tests for session management tools."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestSessionToolsUnit:
    """Unit tests for session tools with mocked browser."""

    @pytest.mark.anyio
    async def test_sap_session_list_empty(self) -> None:
        """Test sap_session_list with no sessions."""
        from sapguimcp.tools.session_tools import sap_session_list_impl
        from sapguimcp.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        with patch('sapguimcp.tools.session_tools.get_browser_manager') as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_list_impl()

        assert result.success is True
        assert result.session_count == 0

    @pytest.mark.anyio
    async def test_sap_session_list_with_sessions(self) -> None:
        """Test sap_session_list with active sessions."""
        from sapguimcp.tools.session_tools import sap_session_list_impl
        from sapguimcp.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        # Mock pages
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()
        page1.title = AsyncMock(return_value="SAP Easy Access")

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()
        page2.title = AsyncMock(return_value="Create Sales Order")

        registry.register(page1)
        registry.register(page2)

        with patch('sapguimcp.tools.session_tools.get_browser_manager') as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_list_impl()

        assert result.success is True
        assert result.session_count == 2

    @pytest.mark.anyio
    async def test_sap_session_close_rejects_primary(self) -> None:
        """Test that sap_session_close rejects closing s1."""
        from sapguimcp.tools.session_tools import sap_session_close_impl

        result = await sap_session_close_impl("s1")

        assert result.success is False
        assert "primary" in result.error.lower() or "s1" in result.error

    @pytest.mark.anyio
    async def test_sap_session_close_unknown_session(self) -> None:
        """Test sap_session_close with unknown session."""
        from sapguimcp.tools.session_tools import sap_session_close_impl
        from sapguimcp.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        with patch('sapguimcp.tools.session_tools.get_browser_manager') as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_close_impl("s99")

        assert result.success is False
        assert "not found" in result.error.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_session_tools.py -v`
Expected: FAIL with "No module named 'sapguimcp.tools.session_tools'"

**Step 3: Write minimal implementation**

Create `src/sapguimcp/tools/session_tools.py`:

```python
"""Session management tools for parallel sub-agent support."""

import logging

from sapguimcp.models import (
    SessionCloseResult,
    SessionInfo,
    SessionListResult,
    SessionOpenResult,
    get_browser_manager,
)

__all__ = [
    "sap_session_open_impl",
    "sap_session_list_impl",
    "sap_session_close_impl",
]

logger = logging.getLogger(__name__)


async def sap_session_open_impl(tcode: str | None = None) -> SessionOpenResult:
    """Create a new SAP session via /o command.

    Args:
        tcode: Optional transaction to open in new session

    Returns:
        SessionOpenResult with new session_id
    """
    try:
        manager = await get_browser_manager()
        registry = manager.registry

        # Get primary session page to execute /o command
        if not registry.has_session("s1"):
            return SessionOpenResult.failure(
                "No primary session. Call sap_login() first."
            )

        primary_page = registry.get_page("s1")
        context = primary_page.context

        # Count pages before
        pages_before = len(context.pages)

        # Execute /o or /o<tcode> to open new session
        ok_code_field = await primary_page.query_selector("#ToolbarOkCode")
        if not ok_code_field:
            return SessionOpenResult.failure("Could not find OK code field")

        command = f"/o{tcode}" if tcode else "/o"
        await ok_code_field.fill(command)
        await primary_page.keyboard.press("Enter")

        # Wait for new tab
        await primary_page.wait_for_timeout(2000)

        # Check for new page
        if len(context.pages) <= pages_before:
            return SessionOpenResult.failure(
                "SAP session limit reached (typically 6 per user). "
                "Close unused sessions with sap_session_close()."
            )

        # Register new page
        new_page = context.pages[-1]
        session_id = registry.register(new_page)

        return SessionOpenResult(
            session_id=session_id,
            tcode=tcode,
            session_count=len(registry.list_sessions()),
        )

    except Exception as e:
        logger.exception("Error opening new session")
        return SessionOpenResult.failure(f"Error opening session: {e}")


async def sap_session_list_impl() -> SessionListResult:
    """List all active SAP sessions.

    Returns:
        SessionListResult with all sessions and their state
    """
    try:
        manager = await get_browser_manager()
        registry = manager.registry

        sessions: list[SessionInfo] = []

        for session_id in registry.list_sessions():
            try:
                page = registry.get_page(session_id)
                title = await page.title() if hasattr(page.title, '__call__') else None

                sessions.append(SessionInfo(
                    session_id=session_id,
                    title=title,
                    is_primary=(session_id == "s1"),
                ))
            except ValueError:
                # Session expired, skip
                continue

        return SessionListResult(sessions=sessions)

    except Exception as e:
        logger.exception("Error listing sessions")
        return SessionListResult.failure(f"Error listing sessions: {e}")


async def sap_session_close_impl(session_id: str) -> SessionCloseResult:
    """Close a SAP session.

    Args:
        session_id: Session to close (cannot be 's1')

    Returns:
        SessionCloseResult
    """
    # Protect primary session
    if session_id == "s1":
        return SessionCloseResult.failure(
            "Cannot close primary session 's1'. Use sap_login() to start fresh."
        )

    try:
        manager = await get_browser_manager()
        registry = manager.registry

        if not registry.has_session(session_id):
            available = ", ".join(registry.list_sessions()) or "(none)"
            return SessionCloseResult.failure(
                f"Session '{session_id}' not found. Active: {available}."
            )

        page = registry.get_page(session_id)

        # Close SAP session gracefully with /nex
        try:
            ok_code_field = await page.query_selector("#ToolbarOkCode")
            if ok_code_field:
                await ok_code_field.fill("/nex")
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(500)
        except Exception:
            pass  # Page might already be closing

        # Close browser tab
        if not page.is_closed():
            await page.close()

        # Unregister (might already be done by close event)
        registry.unregister(session_id)

        return SessionCloseResult(
            session_id=session_id,
            remaining_sessions=len(registry.list_sessions()),
        )

    except Exception as e:
        logger.exception("Error closing session")
        return SessionCloseResult.failure(f"Error closing session: {e}")
```

**Step 4: Run test to verify it passes**

Run: `pytest unittests/test_session_tools.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/tools/session_tools.py unittests/test_session_tools.py
git commit -m "feat(tools): add session management tools (open/list/close)"
```

---

## Task 6: Register Session Tools with MCP Server

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py`
- Test: `unittests/test_server.py`

**Step 1: Write the failing test**

Add to `unittests/test_server.py`:

```python
def test_session_tools_registered() -> None:
    """Test that session management tools are registered."""
    from sapguimcp.server import mcp

    tool_names = [t.name for t in mcp._tool_manager._tools.values()]

    assert "sap_session_open" in tool_names
    assert "sap_session_list" in tool_names
    assert "sap_session_close" in tool_names
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_server.py::test_session_tools_registered -v`
Expected: FAIL (tools not registered)

**Step 3: Add tool registrations**

Add to `src/sapguimcp/tools/sap_tools.py` after existing imports:

```python
from sapguimcp.tools.session_tools import (
    sap_session_close_impl,
    sap_session_list_impl,
    sap_session_open_impl,
)
```

Add tool definitions (after existing tools):

```python
@mcp.tool(description="""Create a new SAP session (window/tab) for parallel work.

Use this when spawning sub-agents that need isolated SAP sessions.
Each session is independent - actions in one don't affect others.

Returns a session_id (e.g., "s2") to pass to other SAP tools.

Example workflow for parallel agents:
1. Parent: session = sap_session_open()  # Returns {"session_id": "s2"}
2. Parent: Spawn sub-agent with instruction "use session='s2'"
3. Sub-agent: sap_transaction("VA01", session="s2")
4. Sub-agent: sap_fill_form({...}, session="s2")
""")
async def sap_session_open(tcode: str | None = None) -> SessionOpenResult:
    """Create a new SAP session."""
    return await sap_session_open_impl(tcode)


@mcp.tool(description="""List all active SAP sessions.

Returns session IDs, current transaction, and screen title for each.
Use this to see what sessions exist before targeting one.

Primary session ("s1") is created on sap_login().
Additional sessions created via sap_session_open().
""")
async def sap_session_list() -> SessionListResult:
    """List all active sessions."""
    return await sap_session_list_impl()


@mcp.tool(description="""Close a SAP session.

Closes the browser tab and removes the session from the registry.
Cannot close primary session ("s1") - use sap_login() to start fresh.

Args:
    session_id: Session to close (e.g., "s2")
""")
async def sap_session_close(session_id: str) -> SessionCloseResult:
    """Close a specific session."""
    return await sap_session_close_impl(session_id)
```

Add imports for result models at top of file:

```python
from sapguimcp.models import (
    # ... existing imports
    SessionCloseResult,
    SessionListResult,
    SessionOpenResult,
)
```

**Step 4: Run test to verify it passes**

Run: `pytest unittests/test_server.py::test_session_tools_registered -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py
git commit -m "feat(server): register session management tools"
```

---

## Task 7: Add session Parameter to Key Tools (Phase 1 - SAP Tools)

This is a large task split into multiple sub-steps. We'll modify tools incrementally.

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py`
- Modify: `src/sapguimcp/tools/sap_tool_impl.py`
- Test: Integration tests (manual for now)

**Step 1: Add session parameter to sap_fill_form**

In `src/sapguimcp/tools/sap_tools.py`, modify `sap_fill_form`:

```python
@mcp.tool(description="""Fill multiple SAP form fields in a single call.

Keys can be:
- Visible label text (e.g., 'First Name', 'Straße')
- CSS selectors starting with '#' (e.g., '#M0:46:1:1::0:21')

**Session parameter:**
- session=None (default): Uses primary session ("s1")
- session="s2": Targets specific session (for parallel agents)

Use sap_session_list() to see active sessions.
""")
async def sap_fill_form(
    fields: dict[str, str],
    strict: bool = False,
    session: str | None = None,  # NEW
) -> FillFormResult:
```

Inside the function, replace:

```python
page = await browser_manager.get_current_page()
```

with:

```python
page = browser_manager.get_session_page(session)
```

**Step 2: Add session parameter to sap_transaction**

Similar pattern - add `session: str | None = None` as last parameter and use `get_session_page(session)`.

**Step 3: Add session parameter to remaining SAP tools**

Apply same pattern to:

- `sap_press_key`
- `sap_get_screen_text`
- `sap_get_screen_info`
- `sap_read_status_bar`
- `sap_read_table`
- `sap_discover_fields`
- `sap_discover_buttons`
- `sap_get_shortcuts`
- `sap_click_table_cell`
- `sap_close_popup`
- `sap_set_field`
- `sap_get_form_fields`

**Step 4: Commit after each batch of 3-4 tools**

```bash
git add src/sapguimcp/tools/sap_tools.py
git commit -m "feat(tools): add session param to sap_fill_form, sap_transaction, sap_press_key"
```

---

## Task 8: Add session Parameter to Browser Tools

**Files:**

- Modify: `src/sapguimcp/tools/browser_tools.py`

Apply same pattern to:

- `browser_click`
- `browser_fill`
- `browser_keyboard`
- `browser_snapshot`
- `browser_screenshot`
- `browser_evaluate`
- `browser_get_html`
- `browser_select_option`
- `browser_wait`
- `browser_navigate`

**Step 1: Add session to browser_click**

```python
async def browser_click(
    selector: str,
    session: str | None = None,  # NEW
) -> ClickResult:
```

**Step 2: Update page retrieval**

```python
browser_manager = await get_browser_manager()
page = browser_manager.get_session_page(session)
```

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/browser_tools.py
git commit -m "feat(tools): add session param to browser tools"
```

---

## Task 9: Add session Parameter to SE\* Tools

**Files:**

- Modify: `src/sapguimcp/tools/se11_tools.py`
- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `src/sapguimcp/tools/se24_tools.py`
- Modify: `src/sapguimcp/tools/se37_tools.py`
- Modify: `src/sapguimcp/tools/se93_tools.py`

Apply same pattern to each SE\* lookup tool.

**Step 1: Commit**

```bash
git add src/sapguimcp/tools/se*.py
git commit -m "feat(tools): add session param to SE11/SE16/SE24/SE37/SE93 tools"
```

---

## Task 10: Integration Tests with Real Browser

**Files:**

- Create: `unittests/test_session_integration.py`

**Step 1: Write integration tests**

```python
"""Integration tests for session management with real Playwright browser."""

import pytest


@pytest.fixture
async def browser_context():
    """Real Playwright browser context for testing."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        yield context
        await browser.close()


class TestSessionRegistryIntegration:
    """Integration tests with real browser (no SAP)."""

    @pytest.mark.anyio
    async def test_register_real_page(self, browser_context) -> None:
        """Test registering a real Playwright page."""
        from sapguimcp.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        page = await browser_context.new_page()

        session_id = registry.register(page)

        assert session_id == "s1"
        assert registry.get_page("s1") is page

    @pytest.mark.anyio
    async def test_page_close_auto_unregisters(self, browser_context) -> None:
        """Test that closing page triggers auto-unregister."""
        from sapguimcp.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        page = await browser_context.new_page()

        session_id = registry.register(page)
        assert registry.has_session(session_id)

        await page.close()

        # Give event time to fire
        import asyncio
        await asyncio.sleep(0.1)

        assert not registry.has_session(session_id)

    @pytest.mark.anyio
    async def test_multiple_pages_independent(self, browser_context) -> None:
        """Test multiple pages are tracked independently."""
        from sapguimcp.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        page1 = await browser_context.new_page()
        page2 = await browser_context.new_page()

        sid1 = registry.register(page1)
        sid2 = registry.register(page2)

        assert sid1 == "s1"
        assert sid2 == "s2"
        assert registry.get_page("s1") is page1
        assert registry.get_page("s2") is page2

        # Navigate page1, page2 should be unaffected
        await page1.goto("about:blank")
        assert registry.get_page("s2") is page2
```

**Step 2: Run integration tests**

Run: `pytest unittests/test_session_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add unittests/test_session_integration.py
git commit -m "test(session): add integration tests with real Playwright browser"
```

---

## Task 11: E2E Tests with Real SAP

**Files:**

- Create: `unittests/test_session_sap_integration.py`

These tests require SAP access (skip on CI).

```python
"""End-to-end tests for session management against real SAP system."""

import pytest
from unittests.conftest import is_sap_integration_test_machine, call_tool_typed

pytestmark = pytest.mark.skipif(
    not is_sap_integration_test_machine(),
    reason="SAP integration tests only run on authorized machines"
)


class TestSessionSAPIntegration:
    """E2E tests requiring real SAP system."""

    @pytest.mark.anyio
    async def test_sap_login_registers_s1(self, sap_mcp_client) -> None:
        """Test that sap_login creates primary session s1."""
        from sapguimcp.models import SessionListResult

        # Login first
        await sap_mcp_client.call_tool("sap_login", {})

        # Check sessions
        result = await call_tool_typed(
            sap_mcp_client, "sap_session_list", {}, SessionListResult
        )

        assert result.success
        assert result.session_count >= 1
        assert any(s.session_id == "s1" for s in result.sessions)

    @pytest.mark.anyio
    async def test_sap_session_open_creates_s2(self, sap_mcp_client) -> None:
        """Test that sap_session_open creates new session."""
        from sapguimcp.models import SessionOpenResult

        # Login first
        await sap_mcp_client.call_tool("sap_login", {})

        # Open new session
        result = await call_tool_typed(
            sap_mcp_client, "sap_session_open", {}, SessionOpenResult
        )

        assert result.success
        assert result.session_id == "s2"
        assert result.session_count == 2

    @pytest.mark.anyio
    async def test_tool_targets_correct_session(self, sap_mcp_client) -> None:
        """Test that session parameter targets correct window."""
        from sapguimcp.models import ScreenInfo

        # Login and open second session with different tcode
        await sap_mcp_client.call_tool("sap_login", {})
        await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE38"})
        await sap_mcp_client.call_tool("sap_session_open", {"tcode": "SE11"})

        # Get screen info from s1
        info_s1 = await call_tool_typed(
            sap_mcp_client, "sap_get_screen_info", {"session": "s1"}, ScreenInfo
        )

        # Get screen info from s2
        info_s2 = await call_tool_typed(
            sap_mcp_client, "sap_get_screen_info", {"session": "s2"}, ScreenInfo
        )

        # They should show different transactions
        assert "SE38" in (info_s1.transaction or info_s1.title or "")
        assert "SE11" in (info_s2.transaction or info_s2.title or "")
```

**Step 1: Commit**

```bash
git add unittests/test_session_sap_integration.py
git commit -m "test(session): add E2E tests for SAP session management"
```

---

## Task 12: Update sap_login to Register Primary Session

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py`

**Step 1: Modify sap_login**

After successful login, register the page as s1:

```python
# After login success, register as primary session
browser_manager = await get_browser_manager()
page = await browser_manager.get_current_page()

# Register if not already registered
if not browser_manager.registry.has_session("s1"):
    browser_manager.registry.register(page)
```

**Step 2: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py
git commit -m "feat(login): register primary session s1 on successful login"
```

---

## Task 13: Final Integration & Documentation

**Files:**

- Modify: `src/sapguimcp/data/sap_knowledge.md`
- Modify: `README.md`

**Step 1: Update sap_knowledge.md**

Add section on multi-session support:

````markdown
## Multi-Session Support (Parallel Agents)

When spawning sub-agents for parallel SAP work, each agent can have its own session:

1. **Create session:** `sap_session_open()` returns a `session_id`
2. **Pass to sub-agent:** Include `session='s2'` in agent instructions
3. **Use in tools:** All SAP/browser tools accept `session` parameter

Example:

```python
# Parent agent
result = sap_session_open()  # Returns {"session_id": "s2"}
# Spawn sub-agent with: "Your SAP session is 's2'. Pass session='s2' to all SAP tools."

# Sub-agent uses:
sap_transaction("VA01", session="s2")
sap_fill_form({"Customer": "123"}, session="s2")
```
````

Primary session ("s1") is created on `sap_login()`. Up to 6 sessions typically allowed per SAP user.

````

**Step 2: Run full test suite**

```bash
pytest unittests/ -v --tb=short
````

**Step 3: Final commit**

```bash
git add src/sapguimcp/data/sap_knowledge.md README.md
git commit -m "docs: add multi-session documentation"
```

---

## Summary

| Task | Description                  | Est. Steps |
| ---- | ---------------------------- | ---------- |
| 1    | SessionId type alias         | 6          |
| 2    | Session result models        | 6          |
| 3    | SessionRegistry core         | 6          |
| 4    | BrowserManager integration   | 5          |
| 5    | Session tools impl           | 5          |
| 6    | Register tools with MCP      | 4          |
| 7    | Add session to SAP tools     | 4          |
| 8    | Add session to browser tools | 3          |
| 9    | Add session to SE\* tools    | 2          |
| 10   | Integration tests (browser)  | 3          |
| 11   | E2E tests (SAP)              | 2          |
| 12   | Update sap_login             | 2          |
| 13   | Documentation                | 3          |

**Total: ~51 steps**
