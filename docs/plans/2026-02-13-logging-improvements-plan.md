# Logging Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize Python logging for consistency and queryability using stdlib only -- no new dependencies.

**Architecture:** A custom `logging.Formatter` in a new `logging_config.py` module handles dual output (human-readable console or JSON via `LOG_FORMAT=json` env var). Pydantic models define structured log context for repeated patterns (tool calls, transactions, queries). All ~228 log statements across ~28 files get standardized messages and structured `extra={}` fields.

**Tech Stack:** Python stdlib `logging`, Pydantic (already a dependency)

---

### Task 1: Create logging_config.py with formatter and tests

**Files:**

- Create: `src/sapguimcp/logging_config.py`
- Create: `unittests/test_logging_config.py`

**Step 1: Write the failing tests**

```python
"""Tests for logging configuration and structured formatter."""

import json
import logging
import os
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from sapguimcp.logging_config import (
    StructuredFormatter,
    ToolLogContext,
    TransactionLogContext,
    QueryLogContext,
    BrowserLogContext,
    configure_logging,
)


class TestStructuredFormatter:
    """Tests for the dual-mode structured formatter."""

    def test_console_format_plain_message(self) -> None:
        """Plain message without extra fields uses simple format."""
        formatter = StructuredFormatter(json_mode=False)
        record = logging.LogRecord(
            name="sapguimcp.tools.sap_tools",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Server started",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "INFO" in output
        assert "sapguimcp.tools.sap_tools" in output
        assert "Server started" in output

    def test_console_format_with_extra_fields(self) -> None:
        """Extra fields are appended as key=value pairs."""
        formatter = StructuredFormatter(json_mode=False)
        record = logging.LogRecord(
            name="sapguimcp.tools.sap_tools",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Tool completed",
            args=(),
            exc_info=None,
        )
        record.tool = "sap_login"
        record.duration_ms = 2340
        output = formatter.format(record)
        assert "Tool completed" in output
        assert "tool=sap_login" in output
        assert "duration_ms=2340" in output

    def test_json_format_plain_message(self) -> None:
        """JSON mode outputs valid JSON with standard fields."""
        formatter = StructuredFormatter(json_mode=True)
        record = logging.LogRecord(
            name="sapguimcp.server",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Server started",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "sapguimcp.server"
        assert data["msg"] == "Server started"
        assert "ts" in data

    def test_json_format_with_extra_fields(self) -> None:
        """Extra fields are included as top-level JSON keys."""
        formatter = StructuredFormatter(json_mode=True)
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Slow query",
            args=(),
            exc_info=None,
        )
        record.table = "MARA"
        record.rows = 500
        output = formatter.format(record)
        data = json.loads(output)
        assert data["msg"] == "Slow query"
        assert data["table"] == "MARA"
        assert data["rows"] == 500

    def test_json_format_with_exception(self) -> None:
        """Exception info is included in JSON output."""
        formatter = StructuredFormatter(json_mode=True)
        try:
            raise ValueError("test error")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="Something broke",
                args=(),
                exc_info=True,
            )
            # LogRecord captures exc_info from sys.exc_info() when exc_info=True
            import sys
            record.exc_info = sys.exc_info()
        output = formatter.format(record)
        data = json.loads(output)
        assert data["msg"] == "Something broke"
        assert "exc" in data
        assert "ValueError" in data["exc"]

    def test_console_format_excludes_stdlib_attrs(self) -> None:
        """Standard LogRecord attributes are not repeated as extra fields."""
        formatter = StructuredFormatter(json_mode=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Hello",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        # Should not contain internal LogRecord fields like pathname, lineno, etc.
        assert "pathname=" not in output
        assert "lineno=" not in output

    def test_percent_formatting_resolved(self) -> None:
        """Messages with %-args are resolved before formatting."""
        formatter = StructuredFormatter(json_mode=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Loaded %d items from %s",
            args=(42, "catalog"),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["msg"] == "Loaded 42 items from catalog"


class TestLogContextModels:
    """Tests for Pydantic log context models."""

    def test_tool_log_context_full(self) -> None:
        ctx = ToolLogContext(tool="sap_login", session="s1", duration_ms=2340)
        d = ctx.model_dump(mode="json", exclude_none=True)
        assert d == {"tool": "sap_login", "session": "s1", "duration_ms": 2340}

    def test_tool_log_context_minimal(self) -> None:
        ctx = ToolLogContext(tool="sap_login")
        d = ctx.model_dump(mode="json", exclude_none=True)
        assert d == {"tool": "sap_login"}

    def test_transaction_log_context(self) -> None:
        ctx = TransactionLogContext(tool="sap_transaction", tcode="VA01", session="s1")
        d = ctx.model_dump(mode="json", exclude_none=True)
        assert d == {"tool": "sap_transaction", "tcode": "VA01", "session": "s1"}

    def test_query_log_context(self) -> None:
        ctx = QueryLogContext(tool="sap_se16_query", table="MARA", rows=100, total_hits=500)
        d = ctx.model_dump(mode="json", exclude_none=True)
        assert d["table"] == "MARA"
        assert d["rows"] == 100
        assert d["total_hits"] == 500

    def test_browser_log_context(self) -> None:
        ctx = BrowserLogContext(tool="browser_click", selector="#btn1")
        d = ctx.model_dump(mode="json", exclude_none=True)
        assert d == {"tool": "browser_click", "selector": "#btn1"}

    def test_exclude_none_drops_empty_fields(self) -> None:
        ctx = ToolLogContext(tool="test", session=None, agent_id=None)
        d = ctx.model_dump(mode="json", exclude_none=True)
        assert "session" not in d
        assert "agent_id" not in d


class TestConfigureLogging:
    """Tests for the configure_logging function."""

    @pytest.fixture(autouse=True)
    def _restore_root_handlers(self) -> None:
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        yield
        root.handlers = original_handlers
        root.level = original_level

    def test_configure_logging_default_console(self) -> None:
        """Default config uses console formatter."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_FORMAT", None)
            configure_logging()
            root = logging.getLogger()
            assert any(isinstance(h.formatter, StructuredFormatter) for h in root.handlers)

    def test_configure_logging_json_mode(self) -> None:
        """LOG_FORMAT=json uses JSON formatter."""
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}):
            configure_logging()
            root = logging.getLogger()
            structured_handlers = [h for h in root.handlers if isinstance(h.formatter, StructuredFormatter)]
            assert len(structured_handlers) > 0
            assert structured_handlers[0].formatter.json_mode is True

    def test_configure_logging_preserves_non_stream_handlers(self) -> None:
        """configure_logging does not remove non-StreamHandler handlers."""
        root = logging.getLogger()
        file_handler = logging.FileHandler("/dev/null")
        root.addHandler(file_handler)
        configure_logging()
        assert file_handler in root.handlers
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/test_logging_config.py -v -x`
Expected: FAIL with `ModuleNotFoundError: No module named 'sapguimcp.logging_config'`

**Step 3: Write the implementation**

```python
"""Structured logging configuration for SAP Web GUI MCP Server.

Provides a dual-mode formatter (human-readable console or JSON) and
Pydantic models for type-safe structured log context.

Usage:
    from sapguimcp.logging_config import configure_logging, ToolLogContext

    configure_logging()  # Call once at startup

    ctx = ToolLogContext(tool="sap_login", session="s1", duration_ms=2340)
    logger.info("Tool completed", extra=ctx.model_dump(mode="json", exclude_none=True))

Environment variables:
    LOG_FORMAT: Set to "json" for JSON output. Default is human-readable console.
    LOG_LEVEL: Set log level (DEBUG, INFO, WARNING, ERROR). Default is INFO.
"""

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

__all__ = [
    "StructuredFormatter",
    "ToolLogContext",
    "TransactionLogContext",
    "QueryLogContext",
    "BrowserLogContext",
    "configure_logging",
]

# Standard LogRecord attributes to exclude from extra fields
_LOGRECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "relativeCreated",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "pathname",
        "filename",
        "module",
        "thread",
        "threadName",
        "process",
        "processName",
        "levelname",
        "levelno",
        "msecs",
        "message",
        "asctime",
        "taskName",
    }
)


class ToolLogContext(BaseModel):
    """Structured context for tool call log events."""

    tool: str
    session: str | None = None
    agent_id: str | None = None
    duration_ms: int | None = None
    error: str | None = None


class TransactionLogContext(ToolLogContext):
    """Structured context for SAP transaction log events."""

    tcode: str


class QueryLogContext(ToolLogContext):
    """Structured context for SE16 query log events."""

    table: str
    rows: int | None = None
    total_hits: int | None = None


class BrowserLogContext(ToolLogContext):
    """Structured context for browser interaction log events."""

    selector: str | None = None
    url: str | None = None


class StructuredFormatter(logging.Formatter):
    """Dual-mode formatter: human-readable console or JSON.

    Extra fields from the log record (set via ``extra={}``) are appended
    as ``key=value`` pairs in console mode or as top-level JSON keys in
    JSON mode.
    """

    def __init__(self, json_mode: bool = False) -> None:
        super().__init__()
        self.json_mode = json_mode

    def _extract_extra(self, record: logging.LogRecord) -> dict[str, Any]:
        """Extract non-standard fields from the log record."""
        extra: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _LOGRECORD_ATTRS:
                continue
            extra[key] = value
        return extra

    def format(self, record: logging.LogRecord) -> str:
        # Resolve %-formatting
        record.message = record.getMessage()
        extra = self._extract_extra(record)
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        if self.json_mode:
            return self._format_json(record, extra, ts)
        return self._format_console(record, extra, ts)

    def _format_console(
        self, record: logging.LogRecord, extra: dict[str, Any], ts: str
    ) -> str:
        parts = [
            ts,
            f"{record.levelname:<5s}",
            record.name,
            "",
            record.message,
        ]
        if extra:
            kv = "  ".join(f"{k}={v}" for k, v in extra.items())
            parts.append(f"  {kv}")
        if record.exc_info and record.exc_info[1]:
            parts.append("\n" + self.formatException(record.exc_info))
        return " ".join(parts)

    def _format_json(
        self, record: logging.LogRecord, extra: dict[str, Any], ts: str
    ) -> str:
        data: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
        }
        data.update(extra)
        if record.exc_info and record.exc_info[1]:
            data["exc"] = "".join(
                traceback.format_exception(*record.exc_info)
            )
        return json.dumps(data, default=str)


def configure_logging() -> None:
    """Configure root logger with structured formatter.

    Reads LOG_FORMAT and LOG_LEVEL from environment.
    Call once at startup before any log statements.
    """
    json_mode = os.environ.get("LOG_FORMAT", "").lower() == "json"
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = StructuredFormatter(json_mode=json_mode)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Only replace StreamHandlers; preserve others (e.g., IntentFileHandler)
    root.handlers = [h for h in root.handlers if not isinstance(h, logging.StreamHandler)]
    root.addHandler(handler)
    root.setLevel(level)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/test_logging_config.py -v`
Expected: All PASS

**Step 5: Format and commit**

```bash
python -m black src/sapguimcp/logging_config.py unittests/test_logging_config.py
git add src/sapguimcp/logging_config.py unittests/test_logging_config.py
git commit -m "feat: add structured logging formatter and context models"
```

---

### Task 2: Wire up configure_logging in server.py

**Files:**

- Modify: `src/sapguimcp/server.py:42-47`

**Step 1: Replace basicConfig with configure_logging**

Change:

```python
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
```

To:

```python
# Configure logging
from sapguimcp.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)
```

**Step 2: Run existing tests to verify nothing breaks**

Run: `python -m pytest unittests/test_server.py -v -x`
Expected: All PASS (36 tests)

**Step 3: Commit**

```bash
git add src/sapguimcp/server.py
git commit -m "chore: wire up structured logging in server.py"
```

---

### Task 3: Migrate middleware/logging.py

**Files:**

- Modify: `src/sapguimcp/middleware/logging.py`

**Step 1: Replace pipe-delimited strings with structured extra**

The middleware currently logs:

```python
_logger.warning(
    "TOOL_FAIL | session=%s | tool=%s | duration=%s | error=%s | seq=%s",
    session_id, tool_name, duration, e, session.format_sequence(last_n=20),
)
```

Replace with:

```python
_logger.warning(
    "Tool failed",
    extra={
        "tool": tool_name,
        "session": session_id,
        "duration_ms": int(duration.total_seconds() * 1000),
        "error": str(e),
        "seq": session.format_sequence(last_n=20),
    },
)
```

Similarly for the two `TOOL_DONE` log statements -- replace both with:

```python
extra = {
    "tool": tool_name,
    "session": session_id,
    "duration_ms": int(duration.total_seconds() * 1000),
    "total_ms": int(session.total_duration.total_seconds() * 1000),
    "seq": session.format_sequence(last_n=20, current_round_only=True),
}
if round_time is not None:
    extra["round_time_ms"] = int(round_time.total_seconds() * 1000)
_logger.info("Tool completed", extra=extra)
```

This collapses two branches into one log statement.

**Step 2: Run existing tests**

Run: `python -m pytest unittests/ -v -x -k "not integration"`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/middleware/logging.py
git commit -m "refactor: migrate middleware logging to structured extra"
```

---

### Task 4: Migrate browser_tools.py

**Files:**

- Modify: `src/sapguimcp/tools/browser_tools.py`

**Step 1: Standardize exception messages**

All 10 exception log statements follow the same pattern. Remove "Error" prefix:

| Before                                             | After                                        |
| -------------------------------------------------- | -------------------------------------------- |
| `logger.exception("Error getting snapshot")`       | `logger.exception("Getting snapshot")`       |
| `logger.exception("Error taking screenshot")`      | `logger.exception("Taking screenshot")`      |
| `logger.exception("Error clicking element")`       | `logger.exception("Clicking element")`       |
| `logger.exception("Error filling element")`        | `logger.exception("Filling element")`        |
| `logger.exception("Error sending keyboard input")` | `logger.exception("Sending keyboard input")` |
| `logger.exception("Error navigating")`             | `logger.exception("Navigating")`             |
| `logger.exception("Error evaluating script")`      | `logger.exception("Evaluating script")`      |
| `logger.exception("Error waiting")`                | `logger.exception("Waiting")`                |
| `logger.exception("Error getting HTML")`           | `logger.exception("Getting HTML")`           |
| `logger.exception("Error selecting option")`       | `logger.exception("Selecting option")`       |

For the debug statement, add structured context:

```python
# Before
logger.debug("HTML size %.1fKB exceeds threshold, returning as File", size_kb)

# After
logger.debug("HTML exceeds threshold, returning as file", extra={"size_kb": round(size_kb, 1)})
```

**Step 2: Run existing tests**

Run: `python -m pytest unittests/ -v -x -k "not integration"`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/browser_tools.py
git commit -m "refactor: standardize browser_tools logging"
```

---

### Task 5: Migrate sap_tool_impl.py

**Files:**

- Modify: `src/sapguimcp/tools/sap_tool_impl.py`

**Step 1: Standardize messages and add structured context**

```python
# Before
logger.info("Attempting to enter transaction code: %s", transaction_input)
# After
logger.info("Entering transaction", extra={"tcode": transaction_input})

# Before
logger.info("OK-Code field not found, attempting to enable it")
# After
logger.info("OK-Code field not found, enabling it")

# Before
logger.info("Enable OK-Code result: %s - %s", success, message)
# After
logger.info("OK-Code field enabled", extra={"success": success, "message": message})

# Before
logger.warning("sap_fill_form debug: %s", debug_info)
# After
logger.debug("Fill form debug info", extra={"debug_info": debug_info})

# Before
logger.exception("Error executing transaction")
# After
logger.exception("Executing transaction")

# Before
logger.exception("Error sending keyboard shortcut")
# After
logger.exception("Sending keyboard shortcut")

# Before
logger.exception("Error filling form fields")
# After
logger.exception("Filling form fields")

# Before
logger.exception("Error reading status bar")
# After
logger.exception("Reading status bar")

# Before
logger.exception("Error extracting screen text")
# After
logger.exception("Extracting screen text")

# Before
logger.exception("Error getting screen info")
# After
logger.exception("Getting screen info")
```

Note: the `sap_fill_form debug` warning should be `debug` level -- it's diagnostic info, not a warning.

**Step 2: Run existing tests**

Run: `python -m pytest unittests/ -v -x -k "not integration"`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/sap_tool_impl.py
git commit -m "refactor: standardize sap_tool_impl logging"
```

---

### Task 6: Migrate sap_tools.py (largest file, 45 statements)

**Files:**

- Modify: `src/sapguimcp/tools/sap_tools.py`

**Step 1: Read the file and identify all log statements**

This is the largest file. Read it fully before making changes. Apply the same patterns:

1. Remove "Error" / "Failed" prefix from exception messages
2. Move dynamic values from message string to `extra={}` dict
3. Ensure consistent sentence case, no trailing periods
4. Use `ToolLogContext` for tool-related logs where they repeat

**Guidelines for this file:**

- Keepalive logs: `logger.info("Keepalive started", extra={"interval_s": interval})`
- Login logs: use `extra={"url": url}` rather than embedding in message
- Transaction logs: use `extra={"tcode": tcode}`
- Exception logs: just clean up the message prefix

**Step 2: Run existing tests**

Run: `python -m pytest unittests/ -v -x -k "not integration"`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/sap_tools.py
git commit -m "refactor: standardize sap_tools logging"
```

---

### Task 7: Migrate SE\* tools (se11, se16, se24, se37, se93)

**Files:**

- Modify: `src/sapguimcp/tools/se11_tools.py` (8 statements)
- Modify: `src/sapguimcp/tools/se16_tools.py` (32 statements)
- Modify: `src/sapguimcp/tools/se24_tools.py` (4 statements)
- Modify: `src/sapguimcp/tools/se37_tools.py` (4 statements)
- Modify: `src/sapguimcp/tools/se93_tools.py` (3 statements)
- Modify: `src/sapguimcp/parsers/se16_parser.py` (2 statements)

**Step 1: Apply standard patterns**

These files share common patterns. Apply consistently:

```python
# SE* debug snapshots -- all follow same pattern
# Before
logger.debug("SE11: Got snapshot for %s, length: %d chars", name, len(snapshot))
# After
logger.debug("Got snapshot", extra={"object": name, "length": len(snapshot)})

# SE* exception logs -- all follow same pattern
# Before
logger.exception("Error looking up %s in SE11", name)
# After
logger.exception("Looking up in SE11", extra={"object": name})

# SE16 specific -- use QueryLogContext for table operations
# Before
logger.info("SE16: Got %d fields from SE11 for table %s", len(field_order), table)
# After
logger.info("Got field order from SE11", extra={"table": table, "fields": len(field_order)})

# SE16 parser warnings
# Before
logger.warning("SE16 parser: No grid found in snapshot")
# After
logger.warning("No grid found in snapshot")
```

Remove module-name prefixes from messages (e.g., "SE16: ..." or "SE11: ...") -- the logger name `sapguimcp.tools.se16_tools` already identifies the module.

**Step 2: Run existing tests**

Run: `python -m pytest unittests/ -v -x -k "not integration"`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/se11_tools.py src/sapguimcp/tools/se16_tools.py \
    src/sapguimcp/tools/se24_tools.py src/sapguimcp/tools/se37_tools.py \
    src/sapguimcp/tools/se93_tools.py src/sapguimcp/parsers/se16_parser.py
git commit -m "refactor: standardize SE* tools and parser logging"
```

---

### Task 8: Migrate models (browser.py, session_registry.py, workflow_storage.py)

**Files:**

- Modify: `src/sapguimcp/models/browser.py` (10 statements)
- Modify: `src/sapguimcp/models/session_registry.py` (7 statements)
- Modify: `src/sapguimcp/models/workflow_storage.py` (4 statements)

**Step 1: Apply standard patterns**

```python
# browser.py
# Before
logger.info("Launching %s browser...", browser_type)
# After
logger.info("Launching browser", extra={"browser_type": browser_type})

# Before
logger.info("Using existing page: %s (from %d available)", url, count)
# After
logger.info("Using existing page", extra={"url": url, "available": count})

# session_registry.py
# Before
logger.info("Registered session '%s'%s", session_id, f" bound to '{agent_id}'" if agent_id else "")
# After
logger.info("Registered session", extra={"session": session_id, "agent_id": agent_id} if agent_id else {"session": session_id})

# Before
logger.warning("Session '%s' bound to '%s' accessed by '%s' via %s", ...)
# After
logger.warning("Cross-agent session access", extra={"session": session_id, "bound_to": bound_agent, "accessed_by": agent_id, "tool": tool_name})

# workflow_storage.py -- similar pattern
```

**Step 2: Run existing tests**

Run: `python -m pytest unittests/ -v -x -k "not integration"`
Expected: All PASS. Pay special attention to `test_session_registry.py` which uses `caplog` to check log messages -- update expected strings if needed.

**Step 3: Commit**

```bash
git add src/sapguimcp/models/browser.py src/sapguimcp/models/session_registry.py \
    src/sapguimcp/models/workflow_storage.py
git commit -m "refactor: standardize models logging"
```

---

### Task 9: Migrate remaining tools and catalog loaders

**Files:**

- Modify: `src/sapguimcp/tools/abapgit_tools.py` (28 statements)
- Modify: `src/sapguimcp/tools/session_tools.py` (4 statements)
- Modify: `src/sapguimcp/tools/workflow_tools.py` (10 statements)
- Modify: `src/sapguimcp/tools/feedback_tools.py` (4 statements)
- Modify: `src/sapguimcp/tools/intent_tools.py` (1 statement)
- Modify: `src/sapguimcp/catalog/loader.py` (3 statements)
- Modify: `src/sapguimcp/catalog/scraper.py` (3 statements)
- Modify: `src/sapguimcp/tables/loader.py` (3 statements)
- Modify: `src/sapguimcp/tables/scraper.py` (7 statements)
- Modify: `src/sapguimcp/classcatalog/loader.py` (3 statements)
- Modify: `src/sapguimcp/fmcatalog/loader.py` (3 statements)
- Modify: `src/sapguimcp/prompts/__init__.py` (3 statements)

**Step 1: Apply standard patterns**

All catalog loaders follow the identical pattern -- standardize together:

```python
# All loaders: catalog/loader.py, tables/loader.py, classcatalog/loader.py, fmcatalog/loader.py
# Before
logger.warning("Transaction catalog not found at %s", path)
# After
logger.warning("Catalog not found", extra={"path": str(path)})

# Before
logger.info("Loaded transaction catalog: %d transactions (%d enriched)", count, enriched)
# After
logger.info("Loaded catalog", extra={"transactions": count, "enriched": enriched})

# Before
logger.exception("Failed to load transaction catalog from %s", path)
# After
logger.exception("Loading catalog", extra={"path": str(path)})
```

For `abapgit_tools.py` (28 statements): same cleanup -- remove "Error" prefix from exceptions, move dynamic values to `extra={}`.

**DO NOT change `intent_tools.py` or `feedback_tools.py`.** Their pipe-delimited format (`INTENT | session=...`, `FEEDBACK | session=...`) is parsed by `IntentFileHandler` and `FeedbackIssueHandler` via `message.startswith("INTENT |")`. Changing the format would silently break audit logging and GitHub issue creation. These are a separate concern and should only be migrated if the handlers are rewritten simultaneously.

**Step 2: Run existing tests**

Run: `python -m pytest unittests/ -v -x -k "not integration"`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/abapgit_tools.py src/sapguimcp/tools/session_tools.py \
    src/sapguimcp/tools/workflow_tools.py src/sapguimcp/catalog/loader.py \
    src/sapguimcp/catalog/scraper.py src/sapguimcp/tables/loader.py \
    src/sapguimcp/tables/scraper.py src/sapguimcp/classcatalog/loader.py \
    src/sapguimcp/fmcatalog/loader.py src/sapguimcp/prompts/__init__.py
git commit -m "refactor: standardize remaining tools and catalog logging"
```

---

### Task 10: Add pytest logging config and fix caplog tests

**Files:**

- Modify: `pyproject.toml`
- Modify: `unittests/test_session_registry.py` (if caplog assertions break)
- Modify: `unittests/test_agent_binding_integration.py` (if caplog assertions break)

**Step 1: Add pytest logging configuration**

In `pyproject.toml`, add to `[tool.pytest.ini_options]`:

```toml
log_cli = true
log_cli_level = "INFO"
log_format = "%(asctime)s %(levelname)-5s %(name)s  %(message)s"
```

**Step 2: Fix any caplog assertions that broke**

The session registry tests check log message content with `caplog`. Since we changed message formats, search for assertions like:

```python
assert "agent-1" in caplog.text
```

These may need updating if the message format changed. Check all `caplog` usage in:

- `unittests/test_session_registry.py`
- `unittests/test_agent_binding_integration.py`
- `unittests/test_session_tools.py` -- has 4 assertions checking `"tcode=VA01"`, `"/o prefix"`, `"pages: 1 -> 1"`, `"no new page detected"` that will break when `sap_tools.py` messages become structured

**Step 3: Run full test suite**

Run: `python -m pytest unittests/ -v -k "not integration"`
Expected: All PASS

**Step 4: Format all changed files**

```bash
python -m black src/sapguimcp/ unittests/
npm run format
```

**Step 5: Commit**

```bash
git add pyproject.toml unittests/
git commit -m "chore: add pytest logging config and fix caplog assertions"
```

---

### Task 11: Final verification

**Step 1: Run full test suite**

```bash
python -m pytest unittests/ -v -k "not integration"
```

Expected: All PASS

**Step 2: Verify console output looks right**

```bash
LOG_LEVEL=DEBUG python -c "
from sapguimcp.logging_config import configure_logging, ToolLogContext
import logging
configure_logging()
logger = logging.getLogger('sapguimcp.test')
logger.info('Plain message')
ctx = ToolLogContext(tool='sap_login', session='s1', duration_ms=2340)
logger.info('Tool completed', extra=ctx.model_dump(mode='json', exclude_none=True))
logger.warning('Something recoverable', extra={'retries': 3})
try:
    raise ValueError('boom')
except:
    logger.exception('Caught exception')
"
```

**Step 3: Verify JSON output**

```bash
LOG_FORMAT=json LOG_LEVEL=DEBUG python -c "
from sapguimcp.logging_config import configure_logging, ToolLogContext
import logging
configure_logging()
logger = logging.getLogger('sapguimcp.test')
ctx = ToolLogContext(tool='sap_login', session='s1', duration_ms=2340)
logger.info('Tool completed', extra=ctx.model_dump(mode='json', exclude_none=True))
"
```

Expected: Valid JSON line with `ts`, `level`, `logger`, `msg`, `tool`, `session`, `duration_ms` fields.

**Step 4: Format everything and commit**

```bash
python -m black src/sapguimcp/ unittests/
npm run format
git add -A
git commit -m "chore: final formatting pass"
```
