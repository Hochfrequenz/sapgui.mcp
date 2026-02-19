# SAP Identity Log Correlation Design

## Goal

Every tool call log line should include the SAP user, system hostname, and mandant so operators can answer "who did what on which system" from a single log line without joining by session ID.

## Principles

Following the "wide events / canonical log line" approach: emit one rich structured event per tool call containing all context needed for debugging and auditing. Prefer injecting context at the middleware level so individual tools get it for free.

## Architecture

One new model, one storage point, one injection point:

1. **`SapIdentity`** - Pydantic model: `sap_user`, `sap_host`, `sap_mandant`
2. **`SessionStats.sap_identity`** - stores identity after login
3. **`ToolCallLoggingMiddleware`** - injects identity fields into every log `extra={}`

## Data Flow

```
sap_login succeeds
  -> extracts hostname from URL (urllib.parse.urlparse, with fallback)
  -> tries to read SAP username from page DOM (status bar)
  -> if DOM read fails: leaves identity unset, logs warning
  -> calls set_sap_identity(session_id, SapIdentity(...))
  -> stored on SessionStats for that session

"Already logged in" path
  -> tries to read SAP username from page DOM
  -> if DOM read fails: identity left unset (no guessing from env vars)

Any tool call
  -> middleware reads self._sessions[session_id].sap_identity
  -> if set: injects sap_user, sap_host, sap_mandant into extra={}
  -> if not set (pre-login): fields omitted silently
```

## Communication Mechanism

Tools cannot use `Context.set_state()` because FastMCP deep-copies context for child scopes — state set inside `call_next` is invisible to the middleware after return. Instead, `middleware/logging.py` exposes a module-level `set_sap_identity(session_id, identity)` function that writes directly to the middleware's `_sessions` dict via a module-level reference. Both the middleware and `sap_login` import from the same module.

## Files Changed

| File                    | Change                                                                                                                                                                       |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `models/middleware.py`  | Add `SapIdentity`, add field to `SessionStats`                                                                                                                               |
| `middleware/logging.py` | Add module-level `set_sap_identity()`, inject fields in both success and error paths of `on_call_tool`                                                                       |
| `tools/sap_tools.py`    | Call `set_sap_identity` after login (with DOM-based username), inject `Context` for session_id, change existing `user` extra to `sap_user`, change full URL to hostname-only |

Note: Search-query logging for catalog/class/fm/table tools is a separate PR.

## Example Output

Console:

```
Tool completed  tool=sap_transaction  sap_user=JSMITH  sap_host=sap-prod.acme.com  sap_mandant=100  session=abc  duration_ms=1500
```

JSON:

```json
{
    "tool": "sap_transaction",
    "sap_user": "JSMITH",
    "sap_host": "sap-prod.acme.com",
    "sap_mandant": "100",
    "session": "abc",
    "duration_ms": 1500
}
```

## Security

- Password is never logged (already masked by middleware)
- Only hostname extracted from URL (not full URL with path/query)
- SAP user and mandant are non-sensitive operational identifiers

## Pre-login Behavior

Before `sap_login`, `sap_identity` is `None`. The middleware omits the 3 fields. No error, no placeholder values.

## "Already Logged In" Behavior

When `sap_login` detects the user is already logged in, it tries to read the SAP username from the page DOM (status bar). If that fails, identity is left unset — we do not guess from `settings.sap_user` because the actual session user may differ.

## Review Findings Addressed

- C1: Module-level accessor instead of Context.set_state() (deep-copy issue)
- C2: DOM-based username extraction with graceful fallback
- I7: Identity injected in both success and error log paths
- I12: Existing full-URL log changed to hostname-only
- I13: Existing `user` extra key renamed to `sap_user`
- I3: Search-query logging split into separate PR
