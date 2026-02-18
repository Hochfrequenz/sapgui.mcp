"""Tests for logging configuration and structured formatter."""

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from sapwebguimcp.logging_config import (
    BrowserLogContext,
    QueryLogContext,
    StructuredFormatter,
    ToolLogContext,
    TransactionLogContext,
    _PapertrailTlsHandler,
    configure_logging,
)


class TestStructuredFormatter:
    """Tests for the dual-mode structured formatter."""

    def test_console_format_plain_message(self) -> None:
        """Plain message without extra fields uses simple format."""
        formatter = StructuredFormatter(json_mode=False)
        record = logging.LogRecord(
            name="sapwebguimcp.tools.sap_tools",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Server started",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "INFO" in output
        assert "sapwebguimcp.tools.sap_tools" in output
        assert "Server started" in output

    def test_console_format_with_extra_fields(self) -> None:
        """Extra fields are appended as key=value pairs."""
        formatter = StructuredFormatter(json_mode=False)
        record = logging.LogRecord(
            name="sapwebguimcp.tools.sap_tools",
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
            name="sapwebguimcp.server",
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
        assert data["logger"] == "sapwebguimcp.server"
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
        file_handler = logging.FileHandler(os.devnull)
        root.addHandler(file_handler)
        configure_logging()
        assert file_handler in root.handlers

    def test_configure_logging_papertrail_enabled(self) -> None:
        """Papertrail args add a TLS handler to root."""
        configure_logging(papertrail_host="localhost", papertrail_port=15514)
        root = logging.getLogger()
        tls_handlers = [h for h in root.handlers if isinstance(h, _PapertrailTlsHandler)]
        assert len(tls_handlers) == 1
        assert tls_handlers[0]._host == "localhost"
        assert tls_handlers[0]._port == 15514

    def test_configure_logging_papertrail_disabled_by_default(self) -> None:
        """No TLS handler when papertrail_host is empty."""
        configure_logging()
        root = logging.getLogger()
        tls_handlers = [h for h in root.handlers if isinstance(h, _PapertrailTlsHandler)]
        assert len(tls_handlers) == 0

    def test_configure_logging_papertrail_invalid_port(self, caplog: pytest.LogCaptureFixture) -> None:
        """Warns and skips handler when port is invalid."""
        with caplog.at_level(logging.WARNING):
            configure_logging(papertrail_host="localhost", papertrail_port=0)
        root = logging.getLogger()
        tls_handlers = [h for h in root.handlers if isinstance(h, _PapertrailTlsHandler)]
        assert len(tls_handlers) == 0
        assert "invalid" in caplog.text

    def test_configure_logging_papertrail_deduplication(self) -> None:
        """Calling configure_logging twice does not add duplicate handlers."""
        configure_logging(papertrail_host="localhost", papertrail_port=15514)
        configure_logging(papertrail_host="localhost", papertrail_port=15514)
        root = logging.getLogger()
        tls_handlers = [h for h in root.handlers if isinstance(h, _PapertrailTlsHandler)]
        assert len(tls_handlers) == 1


class TestPapertrailTlsHandler:
    """Behavioral tests for _PapertrailTlsHandler."""

    def _make_handler(self) -> _PapertrailTlsHandler:
        handler = _PapertrailTlsHandler("host", 1234)
        handler.setFormatter(logging.Formatter("%(message)s"))
        return handler

    def _make_record(self, msg: str = "hello", level: int = logging.INFO) -> logging.LogRecord:
        return logging.LogRecord("test", level, "", 0, msg, (), None)

    def test_emit_sends_correct_payload(self) -> None:
        """emit() sends PRI + timestamp + formatted message + newline."""
        handler = self._make_handler()
        mock_sock = MagicMock()
        handler._sock = mock_sock

        handler.emit(self._make_record("hello", logging.WARNING))

        mock_sock.sendall.assert_called_once()
        payload = mock_sock.sendall.call_args[0][0].decode("utf-8")
        # WARNING -> severity 4, USER facility -> PRI = 1*8+4 = 12
        assert payload.startswith("<12>")
        assert "hello" in payload
        assert payload.endswith("\n")

    def test_emit_sanitizes_newlines(self) -> None:
        """Newlines in messages are replaced with spaces."""
        handler = self._make_handler()
        mock_sock = MagicMock()
        handler._sock = mock_sock

        handler.emit(self._make_record("line1\nline2\r\nline3"))

        payload = mock_sock.sendall.call_args[0][0].decode("utf-8")
        # Only the trailing \n should remain (the framing newline)
        assert "\n" not in payload.rstrip("\n")
        assert "line1 line2 line3" in payload

    def test_emit_reconnects_after_failure(self) -> None:
        """Socket is cleared for reconnect on send failure."""
        handler = self._make_handler()
        mock_sock = MagicMock()
        mock_sock.sendall.side_effect = ConnectionResetError
        handler._sock = mock_sock

        handler.emit(self._make_record())

        assert handler._sock is None
        assert handler._consecutive_failures == 1

    @patch("sapwebguimcp.logging_config.socket.create_connection")
    def test_emit_handles_connect_failure(self, mock_conn: MagicMock) -> None:
        """Connection failure does not raise and triggers backoff."""
        mock_conn.side_effect = OSError("connection refused")
        handler = self._make_handler()

        handler.emit(self._make_record())  # should not raise

        assert handler._sock is None
        assert handler._consecutive_failures == 1
        assert handler._backoff_until > 0

    @patch("sapwebguimcp.logging_config.socket.create_connection")
    def test_emit_skips_during_backoff(self, mock_conn: MagicMock) -> None:
        """Messages are silently dropped during backoff period."""
        mock_conn.side_effect = OSError("connection refused")
        handler = self._make_handler()

        handler.emit(self._make_record())  # triggers backoff
        mock_conn.reset_mock()
        handler.emit(self._make_record())  # should be dropped

        mock_conn.assert_not_called()

    def test_close_closes_socket(self) -> None:
        """close() closes the underlying socket."""
        handler = self._make_handler()
        mock_sock = MagicMock()
        handler._sock = mock_sock

        handler.close()

        mock_sock.close.assert_called_once()
        assert handler._sock is None

    @pytest.mark.parametrize(
        ("level", "expected_pri"),
        [
            (logging.DEBUG, 15),  # 1*8+7
            (logging.INFO, 14),  # 1*8+6
            (logging.WARNING, 12),  # 1*8+4
            (logging.ERROR, 11),  # 1*8+3
            (logging.CRITICAL, 10),  # 1*8+2
        ],
    )
    def test_priority_mapping(self, level: int, expected_pri: int) -> None:
        """PRI values match syslog USER facility + level severity."""
        handler = self._make_handler()
        record = self._make_record(level=level)
        assert handler._priority(record) == expected_pri

    def test_priority_unknown_level_defaults_to_info(self) -> None:
        """Unknown log levels fall back to INFO severity (6)."""
        handler = self._make_handler()
        record = self._make_record()
        record.levelno = 99
        assert handler._priority(record) == 14  # 1*8+6
