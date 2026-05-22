# SAP Identity Log Correlation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich every tool call log line with `sap_user`, `sap_host`, `sap_mandant` so operators can correlate logs to SAP sessions.

**Architecture:** Store `SapIdentity` on `SessionStats` after login. The middleware injects identity fields into every log `extra={}`. A module-level accessor bridges tools → middleware (Context.set_state is unusable due to deep-copy). Username is read from the SAP page DOM after login; if DOM read fails, identity is left unset.

**Tech Stack:** Pydantic models, Python stdlib logging, FastMCP middleware, Playwright (DOM extraction)

**Design doc:** `docs/plans/2026-02-18-sap-identity-log-correlation-design.md`

---

### Task 1: Add `SapIdentity` model and `SessionStats.sap_identity` field

**Files:**

- Modify: `src/sapguimcp/models/middleware.py`
- Test: `unittests/test_middleware_models.py` (or create if not exists)

**Step 1: Write the failing test**

```python
# In test file for middleware models
from sapguimcp.models.middleware import SapIdentity, SessionStats

def test_sap_identity_model():
    identity = SapIdentity(sap_user="KLEINK", sap_host="sap-prod.acme.com", sap_mandant="100")
    d = identity.model_dump(mode="json", exclude_none=True)
    assert d == {"sap_user": "KLEINK", "sap_host": "sap-prod.acme.com", "sap_mandant": "100"}

def test_session_stats_identity_default_none():
    stats = SessionStats()
    assert stats.sap_identity is None

def test_session_stats_with_identity():
    identity = SapIdentity(sap_user="KLEINK", sap_host="sap-prod.acme.com", sap_mandant="100")
    stats = SessionStats(sap_identity=identity)
    assert stats.sap_identity.sap_user == "KLEINK"
```

**Step 2: Run test to verify it fails**

Run: `pytest unittests/test_middleware_models.py -v -k "sap_identity"`
Expected: FAIL — `ImportError: cannot import name 'SapIdentity'`

**Step 3: Write minimal implementation**

In `src/sapguimcp/models/middleware.py`, add before `SessionStats`:

```python
class SapIdentity(BaseModel):
    """SAP login identity for log correlation."""
    sap_user: str
    sap_host: str
    sap_mandant: str
```

Add to `SessionStats`:

```python
    sap_identity: SapIdentity | None = Field(
        default=None,
        description="SAP identity captured after login, injected into log extra by middleware",
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest unittests/test_middleware_models.py -v -k "sap_identity"`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/models/middleware.py unittests/test_middleware_models.py
git commit -m "feat: add SapIdentity model and SessionStats.sap_identity field"
```

---

### Task 2: Add module-level `set_sap_identity()` and identity injection in middleware

**Files:**

- Modify: `src/sapguimcp/middleware/logging.py`
- Modify: `src/sapguimcp/middleware/__init__.py` (export `set_sap_identity`)
- Test: `unittests/test_tool_call_logging_middleware.py` (create)

**Context:** The middleware's `_sessions` dict is instance state. Tools run inside `call_next` (child context) so they can't use `Context.set_state()` — deep-copy prevents cross-boundary communication. Solution: a module-level reference to the middleware's `_sessions` dict, plus a `set_sap_identity(session_id, identity)` function.

**Step 1: Write the failing tests**

```python
# unittests/test_tool_call_logging_middleware.py
import pytest
from sapguimcp.middleware.logging import set_sap_identity, _sessions_ref
from sapguimcp.models.middleware import SapIdentity, SessionStats

def test_set_sap_identity_creates_session_if_needed():
    """set_sap_identity should work even if session doesn't exist yet."""
    identity = SapIdentity(sap_user="KLEINK", sap_host="myhost", sap_mandant="100")
    set_sap_identity("test-session", identity)
    assert _sessions_ref["test-session"].sap_identity == identity

def test_set_sap_identity_on_existing_session():
    """set_sap_identity on an existing session preserves other stats."""
    from sapguimcp.middleware.logging import _sessions_ref
    _sessions_ref["existing"] = SessionStats(call_count=5)
    identity = SapIdentity(sap_user="JSMITH", sap_host="host2", sap_mandant="200")
    set_sap_identity("existing", identity)
    assert _sessions_ref["existing"].sap_identity == identity
    assert _sessions_ref["existing"].call_count == 5
```

Tests for identity injection into log extra will use a real middleware instance — see integration test in step 1b:

```python
def test_identity_fields_in_success_log(caplog):
    """After set_sap_identity, Tool completed log should include sap_user/host/mandant."""
    # This is an integration test — needs a mock call_next and MiddlewareContext.
    # Details depend on how FastMCP middleware testing works.
    # At minimum, verify the extra dict building logic.
    pass  # Placeholder — implement after understanding FastMCP test patterns

def test_identity_fields_in_error_log(caplog):
    """After set_sap_identity, Tool failed log should also include identity fields."""
    pass  # Same pattern as above
```

**Step 2: Run tests to verify they fail**

Run: `pytest unittests/test_tool_call_logging_middleware.py -v`
Expected: FAIL — `ImportError: cannot import name 'set_sap_identity'`

**Step 3: Write implementation**

In `src/sapguimcp/middleware/logging.py`:

1. Add a module-level dict reference (the middleware will register itself here):

```python
# Module-level reference for cross-boundary communication (tools -> middleware).
# The middleware registers its _sessions dict here on __init__.
# Tools call set_sap_identity() which writes to this same dict.
_sessions_ref: dict[str, SessionStats] = {}
```

2. Add `set_sap_identity()`:

```python
def set_sap_identity(session_id: str, identity: SapIdentity) -> None:
    """Set SAP identity for a session. Called by sap_login after successful login.

    This uses a module-level dict shared with the middleware instance,
    because Context.set_state() deep-copies and cannot communicate
    back to the middleware after call_next returns.
    """
    key = session_id or "unknown"
    if key not in _sessions_ref:
        _sessions_ref[key] = SessionStats()
    _sessions_ref[key].sap_identity = identity
```

3. Update `ToolCallLoggingMiddleware.__init__` to register:

```python
def __init__(self) -> None:
    super().__init__()
    self._sessions: dict[str, SessionStats] = _sessions_ref  # share the module-level dict
```

4. Add a helper to build identity extra fields:

```python
def _identity_extra(self, session: SessionStats) -> dict[str, str]:
    """Extract identity fields from session for log extra."""
    if session.sap_identity is None:
        return {}
    return session.sap_identity.model_dump(mode="json")
```

5. Inject identity into both success and error log paths in `on_call_tool`:

In the **error path** (around line 94-103), add identity fields:

```python
extra = {
    "tool": tool_name,
    "session": session_id,
    "duration_ms": int(duration.total_seconds() * 1000),
    "error": str(e),
    "seq": session.format_sequence(last_n=20),
}
extra.update(self._identity_extra(session))
_logger.warning("Tool failed", extra=extra)
```

In the **success path** (around line 112-121), add identity fields after the existing extra dict:

```python
extra.update(self._identity_extra(session))
_logger.info("Tool completed", extra=extra)
```

6. Add import for `SapIdentity`:

```python
from sapguimcp.models.middleware import SapIdentity, SessionStats, ToolCall
```

7. Update `__all__`:

```python
__all__ = ["ToolCallLoggingMiddleware", "set_sap_identity"]
```

8. Export from `src/sapguimcp/middleware/__init__.py`:

```python
from sapguimcp.middleware.logging import set_sap_identity
```

**Step 4: Run tests to verify they pass**

Run: `pytest unittests/test_tool_call_logging_middleware.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/middleware/logging.py src/sapguimcp/middleware/__init__.py unittests/test_tool_call_logging_middleware.py
git commit -m "feat: add set_sap_identity() and inject identity into tool call logs"
```

---

### Task 3: Add JavaScript for DOM-based SAP username extraction

**Files:**

- Create: `src/sapguimcp/js/extract_sap_user.js`
- Test: Test via Python unit test with mock HTML

**Context:** After login, the SAP page has an element:

```html
<... id="sysInfoAreaMenuItemSAPITS_MBAR_USER" lsdata='{"0":"abc","1":"Benutzer","13":"KLEINK"}'
aria-label="User KLEINK" ...>
```

Two extraction strategies (in order of reliability):

1. `lsdata` JSON key `"13"` on element `#sysInfoAreaMenuItemSAPITS_MBAR_USER`
2. `aria-label` last word on the same element (fallback)

**Step 1: Write the JavaScript**

```javascript
// extract_sap_user.js
// Extracts the SAP username from the page DOM after login.
// Returns { user: "KLEINK" } or { user: null } if not found.
(() => {
    const el = document.getElementById('sysInfoAreaMenuItemSAPITS_MBAR_USER');
    if (!el) return { user: null };

    // Strategy 1: lsdata JSON, key "13"
    const lsdata = el.getAttribute('lsdata');
    if (lsdata) {
        try {
            const data = JSON.parse(lsdata);
            if (data['13']) return { user: String(data['13']) };
        } catch (e) {
            /* fall through */
        }
    }

    // Strategy 2: aria-label last word
    const label = el.getAttribute('aria-label');
    if (label) {
        const parts = label.trim().split(/\s+/);
        if (parts.length >= 2) return { user: parts[parts.length - 1] };
    }

    return { user: null };
})();
```

**Step 2: Write Python test with mock HTML**

```python
# In test file (can be part of test_tool_call_logging_middleware.py or a new test file)
def test_extract_sap_user_js_exists():
    """The JS file should be loadable."""
    from pathlib import Path
    js_path = Path("src/sapguimcp/js/extract_sap_user.js")
    assert js_path.exists()
    content = js_path.read_text()
    assert "sysInfoAreaMenuItemSAPITS_MBAR_USER" in content
```

Note: Full integration testing of the JS requires Playwright, which is covered by the existing snapshot-based tests. The JS itself is simple enough that a file-existence + content check suffices for unit tests.

**Step 3: Commit**

```bash
git add src/sapguimcp/js/extract_sap_user.js
git commit -m "feat: add JavaScript for DOM-based SAP username extraction"
```

---

### Task 4: Call `set_sap_identity` from `sap_login` after successful login

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py`
- Test: `unittests/test_sap_login_identity.py` (create)

**Context:** `sap_login` has 3 success paths:

1. **Already logged in** (line 635-648): OKCode field detected immediately
2. **Fresh login** (line 694-708): Login form filled, OK-Code appears
3. **"Already logged in" dialog** (line 714-737): Continue button clicked

All 3 paths need to: extract username from DOM, extract hostname from URL, call `set_sap_identity()`.

**Important:** `sap_login` currently does NOT receive the MCP `session_id`. It needs `Context` injected via FastMCP dependency injection to get it.

**Step 1: Check how to get session_id in a tool function**

FastMCP tools can declare a `ctx: Context` parameter to receive the context. Check existing tools that use `Context` for the pattern:

```python
from fastmcp import Context

async def sap_login(url: Optional[str] = None, ctx: Context = None) -> LoginResult:
    session_id = getattr(ctx, "session_id", None) if ctx else None
```

**Step 2: Write helper function for identity extraction**

Add near the top of `sap_tools.py`:

```python
from urllib.parse import urlparse
from sapguimcp.middleware.logging import set_sap_identity
from sapguimcp.models.middleware import SapIdentity

async def _capture_sap_identity(
    page: Any,
    effective_url: str,
    mandant: str,
    session_id: str | None,
) -> None:
    """Extract SAP username from DOM and store identity for log correlation.

    Tries DOM extraction first. If it fails, logs a warning and leaves
    identity unset (no guessing from env vars).
    """
    hostname = urlparse(effective_url).hostname or "unknown"

    try:
        js = _load_js("extract_sap_user.js")
        result = await page.evaluate(js)
        sap_user = result.get("user") if result else None
    except Exception:  # pylint: disable=broad-exception-caught
        sap_user = None

    if sap_user:
        identity = SapIdentity(sap_user=sap_user, sap_host=hostname, sap_mandant=mandant)
        set_sap_identity(session_id, identity)
        logger.info("SAP identity captured", extra=identity.model_dump(mode="json"))
    else:
        logger.warning("Could not extract SAP username from page DOM; identity not set for log correlation")
```

**Step 3: Call `_capture_sap_identity` in all 3 success paths**

In each success path, after `await _start_keepalive()` and before `return LoginResult(...)`:

```python
await _capture_sap_identity(page, effective_url, settings.sap_mandant, session_id)
```

For the "already logged in" path (line 635-648), mandant comes from `settings.sap_mandant` as a best-effort since we don't know the actual mandant used.

**Step 4: Fix existing log lines per review findings**

- Line 629: Change `extra={"url": effective_url}` to `extra={"sap_host": urlparse(effective_url).hostname or "unknown"}` (hostname only, not full URL — I12)
- Line 667: Change `extra={"user": settings.sap_user}` to `extra={"sap_user": settings.sap_user}` (consistent prefix — I13)

**Step 5: Write tests**

```python
# unittests/test_sap_login_identity.py
from unittest.mock import AsyncMock, patch, MagicMock
from sapguimcp.models.middleware import SapIdentity

@pytest.mark.anyio
async def test_capture_sap_identity_success():
    """When DOM returns a username, identity should be set."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": "KLEINK"}

    with patch("sapguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        await _capture_sap_identity(page, "https://sap-prod.acme.com/sap/bc/gui", "100", "session-1")

    mock_set.assert_called_once()
    identity = mock_set.call_args[0][1]
    assert identity.sap_user == "KLEINK"
    assert identity.sap_host == "sap-prod.acme.com"
    assert identity.sap_mandant == "100"

@pytest.mark.anyio
async def test_capture_sap_identity_dom_fails():
    """When DOM extraction fails, identity should NOT be set."""
    page = AsyncMock()
    page.evaluate.side_effect = Exception("Element not found")

    with patch("sapguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        await _capture_sap_identity(page, "https://sap.acme.com/path", "100", "session-1")

    mock_set.assert_not_called()

@pytest.mark.anyio
async def test_capture_sap_identity_null_user():
    """When DOM returns null user, identity should NOT be set."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": None}

    with patch("sapguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        await _capture_sap_identity(page, "https://sap.acme.com/path", "100", "session-1")

    mock_set.assert_not_called()

@pytest.mark.anyio
async def test_capture_sap_identity_schemeless_url():
    """URLs without scheme should fall back to 'unknown' hostname."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": "JSMITH"}

    with patch("sapguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        await _capture_sap_identity(page, "sap-server/path", "200", "s1")

    identity = mock_set.call_args[0][1]
    assert identity.sap_host == "unknown"
```

**Step 6: Run tests**

Run: `pytest unittests/test_sap_login_identity.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py src/sapguimcp/js/extract_sap_user.js unittests/test_sap_login_identity.py
git commit -m "feat: capture SAP identity after login and inject into tool call logs"
```

---

### Task 5: Add identity pass-through test for StructuredFormatter

**Files:**

- Modify: `unittests/test_logging_config.py`

**Context:** Verify that `sap_user`, `sap_host`, `sap_mandant` extra fields flow through the formatter correctly in both console and JSON modes.

**Step 1: Write the tests**

```python
def test_console_format_with_identity_fields(self) -> None:
    """SAP identity fields appear as key=value pairs in console mode."""
    formatter = StructuredFormatter(json_mode=False)
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Tool completed", args=(), exc_info=None,
    )
    record.sap_user = "KLEINK"
    record.sap_host = "sap-prod.acme.com"
    record.sap_mandant = "100"
    record.tool = "sap_transaction"
    output = formatter.format(record)
    assert "sap_user=KLEINK" in output
    assert "sap_host=sap-prod.acme.com" in output
    assert "sap_mandant=100" in output
    assert "tool=sap_transaction" in output

def test_json_format_with_identity_fields(self) -> None:
    """SAP identity fields appear as top-level JSON keys."""
    formatter = StructuredFormatter(json_mode=True)
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Tool completed", args=(), exc_info=None,
    )
    record.sap_user = "KLEINK"
    record.sap_host = "sap-prod.acme.com"
    record.sap_mandant = "100"
    output = formatter.format(record)
    data = json.loads(output)
    assert data["sap_user"] == "KLEINK"
    assert data["sap_host"] == "sap-prod.acme.com"
    assert data["sap_mandant"] == "100"

def test_identity_fields_not_present_pre_login(self) -> None:
    """Before login, identity fields should not appear in output."""
    formatter = StructuredFormatter(json_mode=True)
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Tool completed", args=(), exc_info=None,
    )
    record.tool = "browser_snapshot"
    output = formatter.format(record)
    data = json.loads(output)
    assert "sap_user" not in data
    assert "sap_host" not in data
    assert "sap_mandant" not in data
```

**Step 2: Run tests**

Run: `pytest unittests/test_logging_config.py -v`
Expected: PASS (these should pass immediately since the formatter already passes through all extra fields)

**Step 3: Commit**

```bash
git add unittests/test_logging_config.py
git commit -m "test: add identity field pass-through tests for StructuredFormatter"
```

---

### Task 6: Run full test suite and linting

**Step 1: Run all tests**

```bash
pytest unittests/ -v
```

**Step 2: Run linting**

```bash
tox -e linting
```

**Step 3: Fix any issues found**

**Step 4: Final commit if needed**

```bash
git commit -m "fix: address linting issues"
```

---

### Task 7: Run expert review

Dispatch a code reviewer with logging/MCP expertise to review the full implementation against the design doc. Verify:

- Identity injection works in both success and error log paths
- No password or full URL leakage
- Pre-login behavior (silent omission) is correct
- Module-level dict sharing is thread-safe for the single-threaded async case
- Tests cover all edge cases

---

## Execution Notes

- Tasks 1-4 are sequential (each builds on the previous)
- Task 5 can run in parallel with Task 4
- Task 6-7 must run after all implementation is complete
- Scope is limited to identity correlation only — search-query logging for catalog tools is a separate PR
