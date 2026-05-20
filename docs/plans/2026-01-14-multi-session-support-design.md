# Multi-Session Support for Parallel Sub-Agents

## Problem

When spawning sub-agents to work in SAP, they share the same browser window. Only one agent can use the browser at a time - while one agent's browser tool collects data or the model thinks, other agents are blocked.

SAP supports multiple "modi" (sessions) via the `/o` prefix (e.g., `/oVA01`), which opens transactions in new browser tabs. This design enables sub-agents to work in isolated sessions.

## Solution Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Parent Agent                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Sub-agent 1  │  │ Sub-agent 2  │  │ Sub-agent 3  │          │
│  │ session="s1" │  │ session="s2" │  │ session="s3" │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
    ┌─────────────────────────────────────────────────────────────┐
    │  MCP Server                                                 │
    │  SessionRegistry: {"s1": Page1, "s2": Page2, "s3": Page3}  │
    └─────────────────────────────────────────────────────────────┘
```

- Each sub-agent receives a session ID in its prompt from the parent
- All SAP/browser tools accept optional `session` parameter
- `session=None` defaults to primary session ("s1") for backwards compatibility
- Server maintains session-to-page mapping with automatic cleanup

## Type Definitions

```python
from typing import Annotated
from pydantic import BeforeValidator, Field

# Session ID type: lowercase 's' followed by digits (s1, s2, s3, ...)
_SESSION_ID_PATTERN = r"^s\d+$"
SessionId = Annotated[str, BeforeValidator(str.lower), Field(pattern=_SESSION_ID_PATTERN)]
```

## New Tools

### sap_session_open

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
```

### sap_session_list

```python
@mcp.tool(description="""List all active SAP sessions.

Returns session IDs, current transaction, and screen title for each.
Use this to see what sessions exist before targeting one.

Primary session ("s1") is created on sap_login().
Additional sessions created via sap_session_open().
""")
async def sap_session_list() -> SessionListResult:
```

### sap_session_close

```python
@mcp.tool(description="""Close a SAP session.

Closes the browser tab and removes the session from the registry.
Cannot close primary session ("s1") - use sap_login() to start fresh.

Args:
    session_id: Session to close (e.g., "s2")
""")
async def sap_session_close(session_id: SessionId) -> SessionCloseResult:
```

## Result Models

```python
class SessionInfo(BaseModel):
    """Information about a single SAP session."""

    session_id: SessionId = Field(description="Session identifier (e.g., 's1', 's2')")
    tcode: str | None = Field(default=None, description="Current transaction code (e.g., 'VA01')")
    title: str | None = Field(default=None, description="Current screen title")
    is_primary: bool = Field(default=False, description="True if this is the primary session ('s1')")


class SessionOpenResult(ToolResult):
    """Result from sap_session_open tool."""

    session_id: SessionId | None = Field(
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

    session_id: SessionId | None = Field(
        default=None,
        description="ID of the session that was closed (e.g., 's2')"
    )
    remaining_sessions: int = Field(default=0, ge=0, description="Sessions still active after closing")
```

## Session Registry

Event-driven registration with automatic cleanup:

```python
class SessionRegistry:
    """Tracks SAP sessions with automatic lifecycle management."""

    def __init__(self) -> None:
        self._sessions: dict[str, Page] = {}
        self._counter: int = 0
        self._page_to_session: dict[Page, str] = {}  # Reverse lookup

    async def setup_listeners(self, context: BrowserContext) -> None:
        """Attach event listeners for automatic registration. Call once after context creation."""
        context.on("page", self._on_page_created)

    def _on_page_created(self, page: Page) -> None:
        """Listen for close events on new pages."""
        page.on("close", lambda: self._on_page_closed(page))

    def _on_page_closed(self, page: Page) -> None:
        """Auto-unregister when browser tab is closed (by SAP, user, or timeout)."""
        if page in self._page_to_session:
            session_id = self._page_to_session.pop(page)
            self._sessions.pop(session_id, None)
            logger.info(f"Session '{session_id}' auto-unregistered (page closed)")

    def register(self, page: Page) -> SessionId:
        """Register a page and return its session ID. Called by sap_login/sap_session_open only."""
        self._counter += 1
        session_id = f"s{self._counter}"
        self._sessions[session_id] = page
        self._page_to_session[page] = session_id
        page.on("close", lambda: self._on_page_closed(page))
        return SessionId(session_id)

    def get_page(self, session_id: SessionId | None) -> Page:
        """Get page for session. Raises ValueError if invalid/closed."""
        sid = session_id or "s1"

        if sid not in self._sessions:
            available = ", ".join(sorted(self._sessions.keys())) or "(none)"
            raise ValueError(
                f"Session '{sid}' not found. Active: {available}. "
                "Use sap_session_list() to see sessions."
            )

        page = self._sessions[sid]
        if page.is_closed():
            self._sessions.pop(sid, None)
            self._page_to_session.pop(page, None)
            raise ValueError(
                f"Session '{sid}' expired (tab closed). "
                "Use sap_session_open() to create a new session."
            )

        return page

    @property
    def primary_session(self) -> SessionId:
        """Primary session is always s1."""
        return SessionId("s1")
```

### Guarantees

| Scenario                     | Behavior                                    |
| ---------------------------- | ------------------------------------------- |
| `/o` creates new tab         | `sap_session_open` explicitly registers it  |
| User closes browser tab      | `page.on("close")` auto-unregisters         |
| SAP timeout closes session   | `page.on("close")` auto-unregisters         |
| Tool calls closed session    | `get_page()` detects and raises clear error |
| `sap_session_close()` called | Explicitly closes page + unregisters        |

## Tool Modifications

All tools that interact with the browser need the `session` parameter (always last, always optional):

```python
async def sap_fill_form(
    fields: dict[str, str],
    strict: bool = False,
    session: SessionId | None = None,  # NEW
) -> FillFormResult:
```

### Tools requiring `session` parameter

| Category       | Tools                                                                                                                                                                                              |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SAP Form       | `sap_fill_form`, `sap_set_field`, `sap_get_form_fields`                                                                                                                                            |
| SAP Navigation | `sap_transaction`, `sap_press_key`                                                                                                                                                                  |
| SAP Read       | `sap_get_screen_text`, `sap_get_screen_info`, `sap_read_status_bar`, `sap_read_table`                                                                                                              |
| SAP Discovery  | `sap_discover_fields`, `sap_discover_buttons`, `sap_get_shortcuts`                                                                                                                                 |
| SAP Table      | `sap_click_table_cell`                                                                                                                                                                             |
| SAP Popup      | `sap_close_popup`                                                                                                                                                                                  |
| SAP Lookup     | `sap_se11_lookup`, `sap_se16_query`, `sap_se24_lookup`, `sap_se37_lookup`, `sap_se93_lookup`                                                                                                       |
| Browser        | `browser_click`, `browser_fill`, `browser_keyboard`, `browser_snapshot`, `browser_screenshot`, `browser_evaluate`, `browser_get_html`, `browser_select_option`, `browser_wait`, `browser_navigate` |

### Tools NOT requiring `session` parameter

- `sap_login` - creates primary session
- `sap_session_open/list/close` - manage sessions themselves
- `sap_session_status` - checks primary session
- `sap_get_capabilities` - returns static info
- `sap_keepalive_start/stop` - applies globally
- `search_transactions`, `search_tables` - catalog lookups, no browser
- `log_intent`, `log_feedback` - logging, no browser
- `workflow_*` - workflow management

## Error Handling

All errors use `Result.failure()` pattern (no exceptions raised to client):

```python
# Invalid session ID
return FillFormResult.failure(
    f"Session '{session_id}' not found. Active sessions: s1, s2. "
    "Use sap_session_list() to see available sessions."
)

# Session closed mid-operation
return FillFormResult.failure(
    f"Session '{session_id}' is no longer active (tab closed or SAP timeout). "
    "Use sap_session_open() to create a new session."
)

# SAP session limit reached
return SessionOpenResult.failure(
    "SAP session limit reached (typically 6 per user). "
    "Close unused sessions with sap_session_close()."
)

# Cannot close primary session
return SessionCloseResult.failure(
    "Cannot close primary session 's1'. Use sap_login() to start fresh."
)
```

## Test Strategy

### Unit tests (no browser)

- `test_register_assigns_sequential_ids`
- `test_register_same_page_twice_raises`
- `test_get_page_returns_correct_page`
- `test_get_page_none_returns_primary`
- `test_get_page_unknown_session_raises_valueerror`
- `test_get_page_closed_page_raises_and_cleans_up`
- `test_on_page_closed_auto_unregisters`
- `test_primary_session_cannot_be_unregistered_manually`

### Integration tests (real browser, no SAP)

- `test_new_tab_creation_and_registration`
- `test_tab_close_triggers_auto_unregister`
- `test_multiple_sessions_isolated`
- `test_get_page_after_tab_crash`
- `test_concurrent_access_to_different_sessions`
- `test_session_survives_navigation`

### E2E tests (real SAP)

- `test_sap_login_registers_s1`
- `test_sap_session_open_creates_new_session`
- `test_sap_session_open_with_tcode`
- `test_sap_session_close_removes_session`
- `test_sap_session_close_primary_rejected`
- `test_tool_with_session_param_targets_correct_window`
- `test_sap_timeout_auto_unregisters`
- `test_parallel_transactions_in_different_sessions`
- `test_session_list_shows_all_active`
- `test_max_sap_sessions_handled_gracefully`

## Migration

- All existing tools continue to work unchanged (`session=None` → "s1")
- New tools added: `sap_session_open`, `sap_session_list`, `sap_session_close`
- Tool descriptions updated to document `session` parameter
- `sap_get_capabilities` output includes session usage examples
