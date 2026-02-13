"""Structured logging configuration for SAP Web GUI MCP Server.

Provides a dual-mode formatter (human-readable console or JSON) and
Pydantic models for type-safe structured log context.

Usage:
    from sapwebguimcp.logging_config import configure_logging, ToolLogContext

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
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        if self.json_mode:
            return self._format_json(record, extra, ts)
        return self._format_console(record, extra, ts)

    def _format_console(self, record: logging.LogRecord, extra: dict[str, Any], ts: str) -> str:
        parts = [
            ts,
            f"{record.levelname:<5s}",
            record.name,
            "",
            record.message,
        ]
        if extra:
            kv = "  ".join(f"{k}={v}" for k, v in extra.items())
            parts.append("")
            parts.append(kv)
        if record.exc_info and record.exc_info[1]:
            parts.append("\n" + self.formatException(record.exc_info))
        return " ".join(parts)

    def _format_json(self, record: logging.LogRecord, extra: dict[str, Any], ts: str) -> str:
        data: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
        }
        data.update(extra)
        if record.exc_info and record.exc_info[1]:
            data["exc"] = "".join(traceback.format_exception(*record.exc_info))
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
    # Only replace exact StreamHandlers; preserve subclasses (e.g., FileHandler)
    root.handlers = [h for h in root.handlers if type(h) is not logging.StreamHandler]
    root.addHandler(handler)
    root.setLevel(level)
