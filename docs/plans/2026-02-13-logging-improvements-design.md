# Logging Improvements Design

## Goal

Standardize Python logging across the codebase for consistency and queryability, using stdlib only (no new dependencies). Guided by [loggingsucks.com](https://loggingsucks.com/) principles: logs should be optimized for querying, not just writing.

## Current State

- 228 log statements across 28 files
- Consistent `logging.getLogger(__name__)` everywhere
- Good lazy %-formatting (no f-strings)
- Proper `logger.exception()` with stack traces
- But: all messages are plain text strings, no structured data
- Inconsistent message patterns (mixed prefixes, capitalization, punctuation)
- Middleware uses pipe-delimited pseudo-structured text (`TOOL_DONE | session=s1 | tool=...`)

## Design

### 1. Log Format and Configuration

New file `src/sapguimcp/logging_config.py` with:

- Custom `Formatter` that reads structured data from log record's `extra` dict
- `configure_logging()` function replacing `basicConfig()` in `server.py`
- Two output modes controlled by `LOG_FORMAT` env var:

```
# Console mode (default, human-readable):
2026-02-13T14:23:01 INFO  sapguimcp.tools.sap_tools  Tool completed  tool=sap_login duration_ms=2340 session=s1

# JSON mode (LOG_FORMAT=json):
{"ts":"2026-02-13T14:23:01","level":"INFO","logger":"sapguimcp.tools.sap_tools","msg":"Tool completed","tool":"sap_login","duration_ms":2340,"session":"s1"}
```

ISO8601 timestamps in both modes.

### 2. Message Consistency Conventions

1. **No "Error"/"Failed" prefix on exception logs** -- the level says ERROR already
    - Before: `logger.exception("Error getting snapshot")`
    - After: `logger.exception("Getting snapshot")`

2. **Sentence case, no trailing period**

3. **Messages describe what happened; context goes in structured fields**
    - Before: `logger.info("Attempting to enter transaction code: %s", tcode)`
    - After: `logger.info("Entering transaction", extra={"tcode": tcode})`

4. **Log level contract:**
    - `DEBUG` -- internal flow (selector searches, HTML sizes, parsing)
    - `INFO` -- significant operations (login, transaction, save, session lifecycle)
    - `WARNING` -- recoverable issues (fallback used, cross-agent access, retries)
    - `EXCEPTION` -- caught exceptions with stack traces

### 3. Pydantic Models for Structured Log Context

For patterns that repeat across many files, define Pydantic models for type safety and consistency:

```python
class ToolLogContext(BaseModel):
    tool: str
    session: str | None = None
    agent_id: str | None = None
    duration_ms: int | None = None
    error: str | None = None

class TransactionLogContext(ToolLogContext):
    tcode: str

class QueryLogContext(ToolLogContext):
    table: str
    rows: int | None = None
    total_hits: int | None = None

class BrowserLogContext(ToolLogContext):
    selector: str | None = None
    url: str | None = None
```

Usage: `logger.info("Tool completed", extra=ctx.model_dump(mode="json", exclude_none=True))`

Plain `extra={}` dicts are fine for one-off log statements where a model is overkill.

### 4. Migration Scope

**New file:** `src/sapguimcp/logging_config.py`

**Modified:** ~28 files, ~228 log statements (mechanical: message cleanup + `extra=`)

**Not touched:** `loghandlers/audit_handler.py`, `loghandlers/feedback_issue_handler.py` (intent/feedback logging is a separate concern)

**Pytest config** added to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
log_cli = true
log_cli_level = "INFO"
log_format = "%(asctime)s %(levelname)-5s %(name)s  %(message)s"
```

## Approach

Stdlib only. No structlog or other dependencies. Custom `logging.Formatter` + Pydantic models for structured context.
