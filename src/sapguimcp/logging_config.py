"""Structured logging configuration for SAP Web GUI MCP Server.

Provides a dual-mode formatter (human-readable console or JSON) and
Pydantic models for type-safe structured log context.

Usage:
    from sapguimcp.logging_config import configure_logging, ToolLogContext

    configure_logging()  # Call once at startup

    ctx = ToolLogContext(tool="sap_login", session="s1", duration_ms=2340)
    logger.info("Tool completed", extra=ctx.model_dump(mode="json", exclude_none=True))

LOG_FORMAT and LOG_LEVEL are read from SapGuiSettings (pydantic-settings).
"""

import importlib.metadata
import json
import logging
import socket
import ssl
import time
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
    "build_info",
]

# Sentinel returned by build_info when no commit identifier can be derived
# from the installed package version (e.g. wheel built without VCS metadata,
# or running from a source tree without hatch-vcs).
COMMIT_UNKNOWN = "unknown"
VERSION_UNKNOWN = "dev"

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
    request_id: str | None = None


def build_info() -> tuple[str, str]:
    """Return (version, commit) for the installed sapguimcp package.

    The version string emitted by hatch-vcs has the shape
    ``<base>+g<sha>.d<date>`` for dev/dirty builds and just ``<base>`` for
    tagged releases. We split on the first ``+`` to recover the base
    version, then look for a ``g<sha>`` segment to recover the commit
    short-SHA. The presence of any ``d<date>`` segment marks the working
    tree as dirty.

    Falls back to ``("dev", "unknown")`` when the package isn't installed
    (e.g. running tests from a source tree without an editable install)
    or when the version string carries no local segment.
    """
    try:
        full = importlib.metadata.version("sapguimcp")
    except importlib.metadata.PackageNotFoundError:
        return (VERSION_UNKNOWN, COMMIT_UNKNOWN)
    if "+" not in full:
        return (full, COMMIT_UNKNOWN)
    base, local = full.split("+", 1)
    commit = COMMIT_UNKNOWN
    dirty = False
    for part in local.split("."):
        if part.startswith("g") and len(part) > 1:
            commit = part[1:]
            if len(commit) > 7:
                commit = commit[:7]
        elif part.startswith("d") and len(part) > 1:
            dirty = True
    if dirty and commit != COMMIT_UNKNOWN:
        commit += "+dirty"
    return (base, commit)


class _BuildContextFilter(logging.Filter):  # pylint: disable=too-few-public-methods
    """Inject build version+commit into every log record passing through.

    Attached to handlers (not loggers) in ``configure_logging`` so that
    records propagated up from child loggers also receive the fields —
    Python only runs logger-level filters for records emitted directly
    on that logger, while handler-level filters apply to everything the
    handler emits.
    """

    def __init__(self, version: str, commit: str) -> None:
        super().__init__()
        self._version = version
        self._commit = commit

    def filter(self, record: logging.LogRecord) -> bool:
        record.version = self._version
        record.commit = self._commit
        return True


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


class _PapertrailTlsHandler(logging.Handler):
    """Send syslog messages to Papertrail over TCP+TLS.

    Each log record is sent as a newline-terminated BSD syslog message
    (RFC 3164 with PRI, timestamp, hostname) over a persistent TLS
    connection.  The connection is established lazily on the first
    emit() call and automatically reconnected on failure with
    exponential backoff to avoid flooding stderr or blocking threads
    when Papertrail is unreachable.

    Newlines in messages are replaced with spaces to prevent syslog
    injection and message splitting.

    This replaces the previous UDP SysLogHandler which silently dropped
    messages without delivery confirmation.
    """

    # Syslog facility USER (1) and default severity INFO (6) → PRI = 1*8+6 = 14
    FACILITY_USER = 1
    _SEVERITY_MAP = {
        logging.DEBUG: 7,  # syslog debug
        logging.INFO: 6,  # syslog info
        logging.WARNING: 4,  # syslog warning
        logging.ERROR: 3,  # syslog err
        logging.CRITICAL: 2,  # syslog crit
    }
    _MAX_BACKOFF = 300  # 5 minutes

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._sock: ssl.SSLSocket | None = None
        self._ctx = ssl.create_default_context()
        self._backoff_until: float = 0.0
        self._consecutive_failures: int = 0

    def _connect(self) -> None:
        # socket.create_connection handles IPv4/IPv6 resolution
        raw = socket.create_connection((self._host, self._port), timeout=5.0)
        try:
            raw.settimeout(None)  # blocking mode after connect
            self._sock = self._ctx.wrap_socket(raw, server_hostname=self._host)
        except Exception:
            raw.close()  # prevent FD leak if TLS handshake fails
            raise

    def _priority(self, record: logging.LogRecord) -> int:
        """Compute syslog PRI value from facility and log level."""
        severity = self._SEVERITY_MAP.get(record.levelno, 6)
        return self.FACILITY_USER * 8 + severity

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._sock is None:
                if time.monotonic() < self._backoff_until:
                    return  # silently drop during backoff
                self._connect()
                self._consecutive_failures = 0
            msg = self.format(record)
            # Sanitize newlines to prevent syslog injection / message splitting
            msg = msg.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
            # BSD syslog: <PRI>TIMESTAMP HOSTNAME MSG\n
            pri = self._priority(record)
            ts = time.strftime("%b %d %H:%M:%S")
            payload = f"<{pri}>{ts} {msg}\n".encode("utf-8")
            self._sock.sendall(payload)  # type: ignore[union-attr]  # _connect() ensures not None
        except Exception:  # pylint: disable=broad-exception-caught
            self._close_socket()
            self._consecutive_failures += 1
            delay = min(2**self._consecutive_failures, self._MAX_BACKOFF)
            self._backoff_until = time.monotonic() + delay
            # Only log the first failure to stderr; suppress subsequent noise
            if self._consecutive_failures <= 1:
                self.handleError(record)

    def _close_socket(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def close(self) -> None:
        self.acquire()
        try:
            self._close_socket()
        finally:
            self.release()
        super().close()


def configure_logging(
    *,
    log_format: str = "",
    log_level: str = "INFO",
    papertrail_host: str = "",
    papertrail_port: int = 0,
) -> None:
    """Configure root logger with structured formatter.

    Call once at startup before any log statements.

    Args:
        log_format: Set to "json" for JSON output. Default is human-readable console.
        log_level: Log level (DEBUG, INFO, WARNING, ERROR). Default is INFO.
        papertrail_host: Papertrail syslog destination host. Empty to disable.
        papertrail_port: Papertrail syslog destination port.

    Build context (version + commit) is attached to every record passing
    through the StreamHandler and Papertrail TLS handler installed here, via
    a ``_BuildContextFilter``. This is intentional handler-scoped behaviour:
    handlers added externally to the root logger (e.g. a user-installed
    ``FileHandler`` for local file logging) will **not** receive the filter
    and their output will not carry version/commit. Re-attach the filter
    explicitly if you wire up a custom handler outside this function.
    """
    json_mode = log_format.lower() == "json"
    level_name = log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = StructuredFormatter(json_mode=json_mode)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Build-context filter: attaches version+commit to every log record so
    # remote bug reports identify the build from a single line.
    build_filter = _BuildContextFilter(*build_info())
    handler.addFilter(build_filter)

    root = logging.getLogger()
    # Only replace exact StreamHandlers; preserve subclasses (e.g., FileHandler)
    root.handlers = [
        h for h in root.handlers if type(h) is not logging.StreamHandler  # pylint: disable=unidiomatic-typecheck
    ]
    root.addHandler(handler)
    root.setLevel(level)

    # Remove any previous Papertrail handler before (re-)adding
    root.handlers = [h for h in root.handlers if not isinstance(h, _PapertrailTlsHandler)]

    if papertrail_host and not 1 <= papertrail_port <= 65535:
        logging.getLogger(__name__).warning(
            "Papertrail host set to %s but port %d is invalid (must be 1-65535). Papertrail logging disabled.",
            papertrail_host,
            papertrail_port,
        )
    elif papertrail_host:
        logging.getLogger(__name__).info(
            "[OK] Papertrail logging configured (TLS): %s:%d", papertrail_host, papertrail_port
        )
        tls_handler = _PapertrailTlsHandler(papertrail_host, papertrail_port)
        # Filter MUST be added before the formatter renders, since
        # %(version)s/%(commit)s in the format string would KeyError if the
        # attributes weren't set on the record yet. Python runs handler
        # filters before the formatter, so this ordering is correct.
        tls_handler.addFilter(build_filter)
        syslog_formatter = logging.Formatter(
            fmt=(
                f"{socket.gethostname()} sapguimcp: %(name)s [%(levelname)s] "
                "version=%(version)s commit=%(commit)s %(message)s"
            ),
        )
        tls_handler.setFormatter(syslog_formatter)
        root.addHandler(tls_handler)
