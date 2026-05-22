# Agent-Session Binding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add agent-session binding to detect cross-session interference in parallel agent workflows.

**Architecture:** Extend SessionRegistry with binding tracking. Add `agent_id` parameter to session-aware tools. Log warnings when sessions are accessed by non-owners. Operations proceed normally (no blocking).

**Tech Stack:** Python 3.11+, FastMCP, Playwright, pytest

---

## Task 1: Extend SessionRegistry with Binding Methods

**Files:**

- Modify: `src/sapguimcp/models/session_registry.py`
- Test: `unittests/test_session_registry.py`

**Step 1: Write failing tests for binding methods**

Add to `unittests/test_session_registry.py`:

```python
class TestSessionRegistryBindings:
    """Tests for agent-session binding functionality."""

    def test_bind_and_get_bound_agent(self) -> None:
        """Test binding an agent to a session."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        registry.bind(sid, "agent-1")

        assert registry.get_bound_agent(sid) == "agent-1"

    def test_get_bound_agent_unbound_returns_none(self) -> None:
        """Test unbound session returns None."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        assert registry.get_bound_agent(sid) is None

    def test_release_clears_binding(self) -> None:
        """Test release removes agent binding."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        registry.bind(sid, "agent-1")
        registry.release(sid)

        assert registry.get_bound_agent(sid) is None

    def test_release_nonexistent_binding_is_noop(self) -> None:
        """Test releasing unbound session doesn't raise."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        registry.release(sid)  # Should not raise
        assert registry.get_bound_agent(sid) is None

    def test_register_with_agent_id_binds(self) -> None:
        """Test register() with agent_id binds immediately."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        assert registry.get_bound_agent(sid) == "agent-1"

    def test_unregister_clears_binding(self) -> None:
        """Test unregister() also removes binding."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        registry.unregister(sid)
        assert registry.get_bound_agent(sid) is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest unittests/test_session_registry.py::TestSessionRegistryBindings -v`
Expected: FAIL with "SessionRegistry has no attribute 'bind'" or similar

**Step 3: Implement binding methods in SessionRegistry**

Edit `src/sapguimcp/models/session_registry.py`:

Add `_bindings` dict to `__init__`:

```python
def __init__(self) -> None:
    self._sessions: dict[str, "Page"] = {}
    self._counter: int = 0
    self._page_to_session: dict["Page", str] = {}
    self._pages_with_listeners: set["Page"] = set()
    self._bindings: dict[str, str] = {}  # session_id -> agent_id
```

Update `register()` signature and body:

```python
def register(self, page: "Page", agent_id: str | None = None) -> str:
    """Register a page and return its session ID.

    Args:
        page: Playwright Page object (browser tab)
        agent_id: Optional agent identifier for binding

    Returns:
        Session ID (e.g., 's1', 's2')
    """
    self._counter += 1
    session_id = f"s{self._counter}"
    self._sessions[session_id] = page
    self._page_to_session[page] = session_id

    if agent_id:
        self._bindings[session_id] = agent_id

    # Auto-unregister when page closes (only attach once per page)
    if page not in self._pages_with_listeners:
        page.on("close", self._make_close_handler(page))
        self._pages_with_listeners.add(page)

    logger.info("Registered session '%s'%s", session_id, f" bound to '{agent_id}'" if agent_id else "")
    return session_id
```

Update `unregister()` to clear binding:

```python
def unregister(self, session_id: str) -> None:
    """Remove a session from the registry.

    Args:
        session_id: Session to remove
    """
    if session_id in self._sessions:
        page = self._sessions.pop(session_id)
        self._page_to_session.pop(page, None)
        self._bindings.pop(session_id, None)  # Clear binding
        logger.info("Unregistered session '%s'", session_id)
```

Add three new methods:

```python
def get_bound_agent(self, session_id: str) -> str | None:
    """Get the agent bound to a session.

    Args:
        session_id: Session to check

    Returns:
        Agent ID or None if unbound
    """
    return self._bindings.get(session_id)

def bind(self, session_id: str, agent_id: str) -> None:
    """Bind a session to an agent.

    Args:
        session_id: Session to bind
        agent_id: Agent identifier
    """
    self._bindings[session_id] = agent_id
    logger.info("Session '%s' bound to agent '%s'", session_id, agent_id)

def release(self, session_id: str) -> None:
    """Release agent binding from a session.

    Args:
        session_id: Session to release
    """
    if session_id in self._bindings:
        old_agent = self._bindings.pop(session_id)
        logger.info("Session '%s' released from agent '%s'", session_id, old_agent)
```

**Step 4: Run tests to verify they pass**

Run: `pytest unittests/test_session_registry.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/models/session_registry.py unittests/test_session_registry.py
git commit -m "feat(session): add agent-session binding methods to SessionRegistry

Add _bindings dict and methods:
- bind(session_id, agent_id): Bind session to agent
- release(session_id): Remove binding
- get_bound_agent(session_id): Get bound agent or None
- register() now accepts optional agent_id parameter
- unregister() clears binding automatically"
```

---

## Task 2: Add check_binding Helper Method

**Files:**

- Modify: `src/sapguimcp/models/session_registry.py`
- Test: `unittests/test_session_registry.py`

**Step 1: Write failing tests for binding check**

Add to `unittests/test_session_registry.py`:

```python
class TestSessionRegistryBindingChecks:
    """Tests for check_binding warning logic."""

    def test_check_binding_unbound_session_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test unbound session doesn't warn."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, "any-agent", "test_tool")

        assert "WARNING" not in caplog.text

    def test_check_binding_matching_agent_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test matching agent doesn't warn."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, "agent-1", "test_tool")

        assert "WARNING" not in caplog.text

    def test_check_binding_mismatched_agent_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test mismatched agent logs warning."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, "agent-2", "test_tool")

        assert "agent-1" in caplog.text
        assert "agent-2" in caplog.text
        assert "test_tool" in caplog.text

    def test_check_binding_none_agent_on_bound_session_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test None agent on bound session logs warning."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, None, "test_tool")

        assert "agent-1" in caplog.text
        assert "without agent_id" in caplog.text
```

**Step 2: Run tests to verify they fail**

Run: `pytest unittests/test_session_registry.py::TestSessionRegistryBindingChecks -v`
Expected: FAIL with "SessionRegistry has no attribute 'check_binding'"

**Step 3: Implement check_binding method**

Add to `src/sapguimcp/models/session_registry.py`:

```python
def check_binding(self, session_id: str, agent_id: str | None, tool_name: str) -> None:
    """Check if agent is authorized to access session.

    Logs warnings for:
    - Bound session accessed without agent_id
    - Bound session accessed by different agent

    Operations always proceed (warn but allow).

    Args:
        session_id: Session being accessed
        agent_id: Agent making the request (or None)
        tool_name: Name of tool for logging context
    """
    bound_agent = self._bindings.get(session_id)

    if bound_agent is None:
        return  # Unbound session, no check

    if agent_id is None:
        logger.warning(
            "Session '%s' bound to '%s' accessed without agent_id by %s",
            session_id,
            bound_agent,
            tool_name,
        )
    elif agent_id != bound_agent:
        logger.warning(
            "Session '%s' bound to '%s' accessed by '%s' via %s",
            session_id,
            bound_agent,
            agent_id,
            tool_name,
        )
```

**Step 4: Add import for logging in test file**

Add at top of test file:

```python
import logging
```

**Step 5: Run tests to verify they pass**

Run: `pytest unittests/test_session_registry.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/sapguimcp/models/session_registry.py unittests/test_session_registry.py
git commit -m "feat(session): add check_binding method for cross-agent detection

Logs warnings when:
- Bound session accessed without agent_id
- Bound session accessed by different agent

Operations always proceed (warn but allow)."
```

---

## Task 3: Add BrowserManager Helper for Page with Binding Check

**Files:**

- Modify: `src/sapguimcp/models/browser.py`
- Test: `unittests/test_session_registry.py`

**Step 1: Write failing test**

Add to `unittests/test_session_registry.py`:

```python
class TestBrowserManagerBindingCheck:
    """Tests for BrowserManager binding check integration."""

    def test_get_session_page_with_binding_check(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test get_session_page_checked calls check_binding."""
        from sapguimcp.models.browser import BrowserManager

        manager = BrowserManager()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = manager.registry.register(page, agent_id="agent-1")

        with caplog.at_level(logging.WARNING):
            result = manager.get_session_page_checked(sid, "agent-2", "test_tool")

        assert result is page
        assert "agent-1" in caplog.text
        assert "agent-2" in caplog.text
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_session_registry.py::TestBrowserManagerBindingCheck -v`
Expected: FAIL with "BrowserManager has no attribute 'get_session_page_checked'"

**Step 3: Implement get_session_page_checked**

Add to `src/sapguimcp/models/browser.py` in BrowserManager class:

```python
def get_session_page_checked(
    self, session_id: str | None, agent_id: str | None, tool_name: str
) -> Page:
    """Get page for a session with binding check.

    Like get_session_page() but also checks agent binding and logs
    warnings for cross-agent access.

    Args:
        session_id: Session ID or None for primary session ('s1')
        agent_id: Agent making the request (or None)
        tool_name: Name of tool for logging context

    Returns:
        Playwright Page object

    Raises:
        ValueError: If session not found or page is closed
    """
    sid = session_id or "s1"
    self.registry.check_binding(sid, agent_id, tool_name)
    return self.registry.get_page(sid)
```

**Step 4: Run tests to verify they pass**

Run: `pytest unittests/test_session_registry.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/models/browser.py unittests/test_session_registry.py
git commit -m "feat(browser): add get_session_page_checked helper

Combines page retrieval with binding check for tool implementations."
```

---

## Task 4: Add sap_session_bind and sap_session_release Tools

**Files:**

- Modify: `src/sapguimcp/tools/session_tools.py`
- Modify: `src/sapguimcp/tools/sap_tools.py` (register tools)
- Test: `unittests/test_session_tools.py` (create if needed)

**Step 1: Add implementation functions**

Add to `src/sapguimcp/tools/session_tools.py`:

```python
from sapguimcp.models import (
    SessionBindResult,
    SessionReleaseResult,
    # ... existing imports
)

__all__ = [
    "sap_session_open_impl",
    "sap_session_list_impl",
    "sap_session_close_impl",
    "sap_session_bind_impl",
    "sap_session_release_impl",
]


async def sap_session_bind_impl(session_id: str, agent_id: str) -> SessionBindResult:
    """Bind a session to an agent.

    Args:
        session_id: Session to bind (e.g., "s2")
        agent_id: Agent identifier

    Returns:
        SessionBindResult
    """
    try:
        manager = await get_browser_manager()
        registry = manager.registry

        if not registry.has_session(session_id):
            available = ", ".join(registry.list_sessions()) or "(none)"
            return SessionBindResult.failure(
                f"Session '{session_id}' not found. Active: {available}."
            )

        old_agent = registry.get_bound_agent(session_id)
        registry.bind(session_id, agent_id)

        return SessionBindResult(
            session_id=session_id,
            agent_id=agent_id,
            previous_agent=old_agent,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error binding session")
        return SessionBindResult.failure(f"Error binding session: {e}")


async def sap_session_release_impl(session_id: str) -> SessionReleaseResult:
    """Release agent binding from a session.

    Args:
        session_id: Session to release

    Returns:
        SessionReleaseResult
    """
    try:
        manager = await get_browser_manager()
        registry = manager.registry

        if not registry.has_session(session_id):
            available = ", ".join(registry.list_sessions()) or "(none)"
            return SessionReleaseResult.failure(
                f"Session '{session_id}' not found. Active: {available}."
            )

        old_agent = registry.get_bound_agent(session_id)
        registry.release(session_id)

        return SessionReleaseResult(
            session_id=session_id,
            released_agent=old_agent,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error releasing session")
        return SessionReleaseResult.failure(f"Error releasing session: {e}")
```

**Step 2: Add result models**

Create or update `src/sapguimcp/models/session_results.py` (or in appropriate models file):

```python
@dataclass
class SessionBindResult:
    """Result of sap_session_bind."""
    session_id: str
    agent_id: str
    previous_agent: str | None = None
    error: str | None = None

    @classmethod
    def failure(cls, error: str) -> "SessionBindResult":
        return cls(session_id="", agent_id="", error=error)


@dataclass
class SessionReleaseResult:
    """Result of sap_session_release."""
    session_id: str
    released_agent: str | None = None
    error: str | None = None

    @classmethod
    def failure(cls, error: str) -> "SessionReleaseResult":
        return cls(session_id="", error=error)
```

**Step 3: Register tools in sap_tools.py**

Find where `sap_session_open` is registered and add nearby:

```python
@mcp.tool(
    description=(
        "Bind a session to an agent for parallel workflow management. "
        "When bound, other agents using this session trigger warnings. "
        "Use for transfer of session ownership between agents."
    )
)
async def sap_session_bind(session: str, agent_id: str) -> SessionBindResult:
    """
    Bind or rebind a session to an agent.

    Args:
        session: Session ID to bind (e.g., "s2")
        agent_id: Agent identifier claiming the session

    Returns:
        SessionBindResult with binding info
    """
    return await sap_session_bind_impl(session, agent_id)


@mcp.tool(
    description=(
        "Release agent binding from a session. "
        "Use when an agent finishes work and wants to free the session "
        "for other agents or general use."
    )
)
async def sap_session_release(session: str) -> SessionReleaseResult:
    """
    Unbind a session from its current agent.

    Args:
        session: Session ID to release

    Returns:
        SessionReleaseResult
    """
    return await sap_session_release_impl(session)
```

**Step 4: Update imports**

Add to sap_tools.py imports:

```python
from sapguimcp.tools.session_tools import (
    sap_session_bind_impl,
    sap_session_release_impl,
    # ... existing imports
)
```

Add to models **init**.py exports:

```python
from .session_results import SessionBindResult, SessionReleaseResult
```

**Step 5: Run full test suite**

Run: `pytest unittests/ -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/sapguimcp/tools/session_tools.py src/sapguimcp/tools/sap_tools.py src/sapguimcp/models/
git commit -m "feat(tools): add sap_session_bind and sap_session_release tools

New tools for agent-session binding management:
- sap_session_bind(session, agent_id): Bind/rebind session to agent
- sap_session_release(session): Unbind session from agent"
```

---

## Task 5: Add agent_id Parameter to sap_session_open

**Files:**

- Modify: `src/sapguimcp/tools/session_tools.py`
- Modify: `src/sapguimcp/tools/sap_tools.py`
- Test: `unittests/test_session_tools.py`

**Step 1: Update sap_session_open_impl**

In `src/sapguimcp/tools/session_tools.py`, update the function signature and body:

```python
async def sap_session_open_impl(
    tcode: str | None = None,
    agent_id: str | None = None,
) -> SessionOpenResult:
    """Create a new SAP session via /o command.

    Args:
        tcode: Optional transaction to open in new session
        agent_id: Optional agent identifier for binding

    Returns:
        SessionOpenResult with new session_id
    """
    # ... existing code until register ...

    # Register new page (with optional binding)
    new_page = context.pages[-1]
    session_id = registry.register(new_page, agent_id=agent_id)

    return SessionOpenResult(
        session_id=session_id,
        tcode=tcode,
        agent_id=agent_id,  # Add this field to result
        session_count=len(registry.list_sessions()),
    )
```

**Step 2: Update SessionOpenResult model**

Add `agent_id` field to SessionOpenResult:

```python
@dataclass
class SessionOpenResult:
    session_id: str
    tcode: str | None = None
    agent_id: str | None = None  # Add this
    session_count: int = 0
    error: str | None = None
```

**Step 3: Update tool registration in sap_tools.py**

```python
@mcp.tool(
    description=(
        "Open a new SAP session (browser tab). Each session can run "
        "independently. Use agent_id for parallel agent workflows to "
        "prevent cross-session interference."
    )
)
async def sap_session_open(
    tcode: str | None = None,
    agent_id: str | None = None,
) -> SessionOpenResult:
    """
    Open a new SAP session (browser tab).

    Args:
        tcode: Optional transaction to open in new session
        agent_id: Optional identifier for the agent claiming this session.
                  When set, other agents using this session trigger warnings.
                  Use for parallel agent workflows to prevent cross-talk.

    Returns:
        SessionOpenResult with new session_id and binding info
    """
    return await sap_session_open_impl(tcode, agent_id)
```

**Step 4: Run tests**

Run: `pytest unittests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/tools/session_tools.py src/sapguimcp/tools/sap_tools.py src/sapguimcp/models/
git commit -m "feat(session): add agent_id parameter to sap_session_open

Sessions can now be bound to agents at creation time.
Binding is optional - backward compatible with existing code."
```

---

## Task 6: Add agent_id to Session-Aware Tools (Part 1: sap_tools.py)

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py`

This task updates 14 tools in sap_tools.py to add the `agent_id` parameter. The pattern is the same for each:

1. Add `agent_id: str | None = None` parameter
2. Replace `browser_manager.get_session_page(session)` with `browser_manager.get_session_page_checked(session, agent_id, "tool_name")`
3. Update docstring

**Tools to update:**

- sap_transaction
- sap_press_key
- sap_get_screen_text
- sap_get_form_fields
- sap_read_table
- sap_click_table_cell
- sap_read_status_bar
- sap_get_screen_info
- sap_discover_fields
- sap_discover_buttons
- sap_get_shortcuts
- sap_close_popup
- sap_fill_form
- sap_set_field

**Example update for sap_press_key:**

```python
async def sap_press_key(
    key: str,
    session: str | None = None,
    agent_id: str | None = None,
) -> KeyboardResult:
    """
    Send a keyboard shortcut to SAP Web GUI.

    Args:
        key: Keyboard shortcut.
        session: Session ID (e.g., "s1", "s2"). None uses primary session.
        agent_id: Agent identifier for binding check. Optional.

    Returns:
        KeyboardResult
    """
    browser_manager = await get_browser_manager()

    try:
        page = browser_manager.get_session_page_checked(session, agent_id, "sap_press_key")
    except ValueError as e:
        return KeyboardResult.failure(str(e), key=key)

    # ... rest unchanged ...
```

**Step 1: Update all 14 tools following the pattern above**

**Step 2: Run tests**

Run: `pytest unittests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py
git commit -m "feat(tools): add agent_id parameter to 14 session-aware tools

Tools now check agent binding before accessing sessions.
Backward compatible - agent_id defaults to None (no check)."
```

---

## Task 7: Add agent_id to Session-Aware Tools (Part 2: SE\* Tools)

**Files:**

- Modify: `src/sapguimcp/tools/se11_tools.py`
- Modify: `src/sapguimcp/tools/se16_tools.py`
- Modify: `src/sapguimcp/tools/se24_tools.py`
- Modify: `src/sapguimcp/tools/se37_tools.py`
- Modify: `src/sapguimcp/tools/se93_tools.py`

Apply the same pattern as Task 6 to all tools in these files:

1. Add `agent_id: str | None = None` parameter
2. Replace `get_session_page(session)` with `get_session_page_checked(session, agent_id, "tool_name")`

**Step 1: Update se11_tools.py**

Find all occurrences of `get_session_page(session)` and update.

**Step 2: Update se16_tools.py**

**Step 3: Update se24_tools.py**

**Step 4: Update se37_tools.py**

**Step 5: Update se93_tools.py**

**Step 6: Run tests**

Run: `pytest unittests/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add src/sapguimcp/tools/se*.py
git commit -m "feat(tools): add agent_id parameter to SE* lookup tools

All SE11, SE16, SE24, SE37, SE93 tools now check agent binding."
```

---

## Task 8: Add agent_id to Browser Tools

**Files:**

- Modify: `src/sapguimcp/tools/browser_tools.py`

Apply the same pattern to browser tools that have session parameter.

**Step 1: Update browser_tools.py**

Update all functions with `session: str | None = None` parameter.

**Step 2: Run tests**

Run: `pytest unittests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/browser_tools.py
git commit -m "feat(tools): add agent_id parameter to browser tools"
```

---

## Task 9: Update SessionListResult to Include Bindings

**Files:**

- Modify: `src/sapguimcp/models/session_results.py`
- Modify: `src/sapguimcp/tools/session_tools.py`

**Step 1: Update SessionInfo model**

```python
@dataclass
class SessionInfo:
    """Info about a single session."""
    session_id: str
    title: str
    is_primary: bool
    agent_id: str | None = None  # Add binding info
```

**Step 2: Update sap_session_list_impl**

```python
sessions.append(
    SessionInfo(
        session_id=session_id,
        title=title,
        is_primary=(session_id == "s1"),
        agent_id=registry.get_bound_agent(session_id),  # Add this
    )
)
```

**Step 3: Run tests**

Run: `pytest unittests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/sapguimcp/models/ src/sapguimcp/tools/session_tools.py
git commit -m "feat(session): include agent_id in session list results

sap_session_list now shows which sessions are bound to which agents."
```

---

## Task 10: Create sap_knowledge.md Documentation

**Files:**

- Create: `docs/sap_knowledge.md`

**Step 1: Write documentation**

````markdown
# SAP WebGUI MCP Knowledge Base

## Multi-Agent Session Management

When running parallel agents (subagents), bind sessions to prevent interference:

### Creating a Bound Session

```python
# Agent claims a session at creation
result = sap_session_open(tcode="VA01", agent_id="my-agent")
# Returns: session_id="s2", agent_id="my-agent"
```
````

### Using Your Session

Pass both `session` and `agent_id` on all subsequent calls:

```python
# All tools support agent_id parameter
sap_press_key("Enter", session="s2", agent_id="my-agent")
sap_fill_form({"Customer": "12345"}, session="s2", agent_id="my-agent")
sap_transaction("VA02", session="s2", agent_id="my-agent")
```

### When Done: Release or Close

```python
# Option 1: Release binding (session stays open)
sap_session_release(session="s2")

# Option 2: Close session entirely
sap_session_close(session="s2")
```

### Transferring Ownership

```python
# Rebind to a different agent
sap_session_bind(session="s2", agent_id="other-agent")
```

### What Happens on Misuse

If an agent accesses a session bound to another agent, a warning is logged:

```
WARNING: Session 's2' bound to 'agent-1' accessed by 'agent-2' via sap_fill_form
```

The operation still proceeds - this is for monitoring, not blocking.

### Checking Session Status

```python
# See all sessions and their bindings
sessions = sap_session_list()
# Returns: [SessionInfo(session_id="s1", agent_id=None),
#           SessionInfo(session_id="s2", agent_id="my-agent")]
```

## Best Practices for Parallel Agents

1. **Always bind sessions** when working with parallel agents
2. **Use consistent agent_id** across all tool calls in an agent
3. **Release when done** to allow reuse
4. **Check logs** for binding warnings to detect cross-talk

````

**Step 2: Commit**

```bash
git add docs/sap_knowledge.md
git commit -m "docs: add multi-agent session management documentation

Explains agent_id parameter usage for parallel workflows."
````

---

## Task 11: Integration Test for Cross-Agent Warning

**Files:**

- Create: `unittests/test_agent_binding_integration.py`

**Step 1: Write integration test**

```python
"""Integration tests for agent-session binding."""

import logging
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestAgentBindingIntegration:
    """Integration tests for cross-agent detection."""

    @pytest.mark.asyncio
    async def test_cross_agent_access_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that cross-agent access logs warning."""
        from sapguimcp.models.browser import BrowserManager

        manager = BrowserManager()

        # Create mock pages
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()

        # Register with bindings
        manager.registry.register(page1)  # s1, unbound
        manager.registry.register(page2, agent_id="agent-A")  # s2, bound to A

        # Agent B tries to access Agent A's session
        with caplog.at_level(logging.WARNING):
            page = manager.get_session_page_checked("s2", "agent-B", "test_tool")

        # Operation should succeed
        assert page is page2

        # But warning should be logged
        assert "agent-A" in caplog.text
        assert "agent-B" in caplog.text

    @pytest.mark.asyncio
    async def test_unbound_session_no_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that unbound session doesn't warn."""
        from sapguimcp.models.browser import BrowserManager

        manager = BrowserManager()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        manager.registry.register(page)  # s1, unbound

        with caplog.at_level(logging.WARNING):
            manager.get_session_page_checked("s1", "any-agent", "test_tool")

        assert "WARNING" not in caplog.text
```

**Step 2: Run test**

Run: `pytest unittests/test_agent_binding_integration.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add unittests/test_agent_binding_integration.py
git commit -m "test: add integration tests for agent-session binding

Tests cross-agent warning behavior and unbound session handling."
```

---

## Task 12: Final Review and Cleanup

**Step 1: Run full test suite**

```bash
pytest unittests/ -v
```

**Step 2: Run type checking**

```bash
mypy src/sapguimcp/
```

**Step 3: Run linting**

```bash
pylint src/sapguimcp/
```

**Step 4: Format code**

```bash
black src/sapguimcp/ unittests/
```

**Step 5: Fix any issues found**

**Step 6: Final commit**

```bash
git add -A
git commit -m "chore: cleanup and formatting for agent-session binding"
```

---

## Summary

This implementation adds agent-session binding with:

1. **SessionRegistry extensions:** `_bindings` dict, `bind()`, `release()`, `get_bound_agent()`, `check_binding()`
2. **BrowserManager helper:** `get_session_page_checked()`
3. **New tools:** `sap_session_bind`, `sap_session_release`
4. **Updated sap_session_open:** accepts `agent_id` parameter
5. **All 29 session-aware tools:** now accept `agent_id` parameter
6. **SessionListResult:** includes binding info
7. **Documentation:** `docs/sap_knowledge.md`
8. **Tests:** Unit and integration tests for all new functionality

The implementation is fully backward compatible - all `agent_id` parameters default to `None`.
