# Agent-Session Binding Design

## Problem

When multiple parallel agents work in separate SAP sessions, there's no mechanism to:

- Track which agent owns which session
- Detect when an agent accidentally uses another agent's session
- Provide visibility into cross-session interference

This can cause data corruption when agents unknowingly overwrite each other's work.

## Solution

Bind sessions to agent identifiers at creation time. Log warnings when sessions are accessed by non-owners. Operations proceed normally (no blocking).

## Design

### Data Model

Extend `SessionRegistry` with agent bindings:

```python
class SessionRegistry:
    def __init__(self):
        self._sessions: dict[str, Page] = {}    # s1 -> Page
        self._bindings: dict[str, str] = {}     # s1 -> "agent-id"

    def register(self, page: Page, agent_id: str | None = None) -> str:
        session_id = f"s{self._counter}"
        self._sessions[session_id] = page
        if agent_id:
            self._bindings[session_id] = agent_id
        return session_id

    def get_bound_agent(self, session_id: str) -> str | None:
        return self._bindings.get(session_id)

    def bind(self, session_id: str, agent_id: str) -> None:
        self._bindings[session_id] = agent_id

    def release(self, session_id: str) -> None:
        self._bindings.pop(session_id, None)
```

### Warning Logic

```python
def check_session_binding(
    session_id: str,
    agent_id: str | None,
    tool_name: str,
) -> None:
    bound_agent = self.get_bound_agent(session_id)

    if bound_agent is None:
        return  # Unbound session, no check

    if agent_id is None:
        logger.warning(
            "Session '%s' bound to '%s' accessed without agent_id by %s",
            session_id, bound_agent, tool_name
        )
    elif agent_id != bound_agent:
        logger.warning(
            "Session '%s' bound to '%s' accessed by '%s' via %s",
            session_id, bound_agent, agent_id, tool_name
        )
```

### New Tools

| Tool                  | Signature                       | Purpose                                |
| --------------------- | ------------------------------- | -------------------------------------- |
| `sap_session_release` | `(session: str)`                | Unbind session, clears agent ownership |
| `sap_session_bind`    | `(session: str, agent_id: str)` | Bind/rebind session to an agent        |

### Modified Tools

Add `agent_id: str | None = None` parameter to:

- `sap_session_open` (for initial binding)
- All 25+ session-aware tools (for binding checks)

Use helper to minimize code changes:

```python
async def _get_page_with_binding_check(
    session: str | None,
    agent_id: str | None,
    tool_name: str,
) -> Page:
    registry = (await get_browser_manager()).session_registry
    session_id = session or "s1"
    registry.check_session_binding(session_id, agent_id, tool_name)
    return registry.get_page(session_id)
```

### Documentation Updates

**1. Tool docstrings (FastMCP exposes these):**

```python
async def sap_session_open(
    agent_id: str | None = None,
) -> SessionResult:
    """
    Open a new SAP session (browser tab).

    Args:
        agent_id: Optional identifier for the agent claiming this session.
                  When set, other agents using this session trigger warnings.
                  Use for parallel agent workflows to prevent cross-talk.
    """
```

**2. Update `sap_knowledge.md`:**

```markdown
## Multi-Agent Session Management

When running parallel agents, bind sessions to prevent interference:

1. **Claim a session:** `sap_session_open(agent_id="my-agent")` -> returns "s2"
2. **Use your session:** Pass `session="s2", agent_id="my-agent"` on all calls
3. **Release when done:** `sap_session_release(session="s2")`
4. **Transfer if needed:** `sap_session_bind(session="s2", agent_id="new-agent")`

Warning: Using a bound session without correct agent_id logs warnings.
```

## Backward Compatibility

Fully backward compatible:

- `agent_id` is optional everywhere (defaults to `None`)
- Sessions created without `agent_id` remain unbound
- Unbound sessions skip all binding checks
- Single-agent workflows are unchanged

## Testing

1. Unit tests for `SessionRegistry` binding methods
2. Unit tests for `check_session_binding` warning logic
3. Integration test: two agents, bound sessions, verify warnings logged on cross-use
4. Integration test: single agent, no `agent_id`, verify no warnings

## Implementation Notes

- Warnings use standard Python `logger.warning()`, no special audit system
- Operations always proceed (warn but allow)
- No deadlock risk since there's no locking
