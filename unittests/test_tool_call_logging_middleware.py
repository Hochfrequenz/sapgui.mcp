"""Tests for tool call logging middleware identity injection."""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from sapguimcp.middleware.logging import (
    ToolCallLoggingMiddleware,
    _sessions_ref,
    new_request_id,
    set_sap_identity,
)

_LOGGER_NAME = "sapguimcp.middleware.logging"
from sapguimcp.models.middleware import SapIdentity, SessionStats


@dataclass
class _FakeMessage:
    """Minimal stand-in for CallToolRequestParams."""

    name: str
    arguments: dict[str, Any] | None = None


@dataclass
class _FakeCtx:
    """Minimal stand-in for fastmcp Context."""

    session_id: str | None = None


@dataclass
class _FakeMiddlewareContext:
    """Minimal stand-in for MiddlewareContext."""

    message: _FakeMessage
    fastmcp_context: _FakeCtx | None = None


@pytest.fixture(autouse=True)
def _clean_sessions():
    """Clear shared sessions dict between tests."""
    _sessions_ref.clear()
    yield
    _sessions_ref.clear()


def test_set_sap_identity_creates_session_if_needed():
    identity = SapIdentity(sap_user="KLEINK", sap_host="myhost", sap_mandant="100")
    set_sap_identity("test-session", identity)
    assert "test-session" in _sessions_ref
    assert _sessions_ref["test-session"].sap_identity == identity


def test_set_sap_identity_on_existing_session():
    _sessions_ref["existing"] = SessionStats(call_count=5)
    identity = SapIdentity(sap_user="JSMITH", sap_host="host2", sap_mandant="200")
    set_sap_identity("existing", identity)
    assert _sessions_ref["existing"].sap_identity == identity
    assert _sessions_ref["existing"].call_count == 5  # preserved


def test_set_sap_identity_none_session_id():
    identity = SapIdentity(sap_user="TEST", sap_host="h", sap_mandant="300")
    set_sap_identity(None, identity)
    assert "unknown" in _sessions_ref
    assert _sessions_ref["unknown"].sap_identity == identity


def test_middleware_shares_sessions_ref():
    """Middleware instance uses the module-level _sessions_ref."""
    mw = ToolCallLoggingMiddleware()
    assert mw._sessions is _sessions_ref


def test_extract_sap_user_js_exists():
    """The JS file should be loadable and contain expected selectors."""
    from importlib import resources

    content = resources.files("sapguimcp.backend.webgui.js").joinpath("extract_sap_user.js").read_text(encoding="utf-8")
    assert "sysInfoAreaMenuItemSAPITS_MBAR_USER" in content
    assert "lsdata" in content
    assert "aria-label" in content


# ---------------------------------------------------------------------------
# on_call_tool: identity fields in log records
# ---------------------------------------------------------------------------

_IDENTITY = SapIdentity(sap_user="KLEINK", sap_host="myhost.example.com", sap_mandant="100")


def _make_context(tool_name: str = "sap_read_screen", session_id: str | None = "sess-1") -> _FakeMiddlewareContext:
    return _FakeMiddlewareContext(
        message=_FakeMessage(name=tool_name),
        fastmcp_context=_FakeCtx(session_id=session_id),
    )


def test_on_call_tool_success_includes_identity(caplog):
    """On success, the log record must contain sap_user/sap_host/sap_mandant."""
    mw = ToolCallLoggingMiddleware()
    set_sap_identity("sess-1", _IDENTITY)

    async def _call_next(_ctx):
        return "ok"

    with caplog.at_level("INFO", logger=_LOGGER_NAME):
        asyncio.run(mw.on_call_tool(_make_context(), _call_next))

    assert len(caplog.records) == 1
    rec = caplog.records[0]
    assert rec.sap_user == "KLEINK"
    assert rec.sap_host == "myhost.example.com"
    assert rec.sap_mandant == "100"


def test_on_call_tool_failure_includes_identity(caplog):
    """On failure, the warning log record must also contain identity fields."""
    mw = ToolCallLoggingMiddleware()
    set_sap_identity("sess-1", _IDENTITY)

    async def _call_next(_ctx):
        raise RuntimeError("boom")

    with caplog.at_level("WARNING", logger=_LOGGER_NAME):
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(mw.on_call_tool(_make_context(), _call_next))

    assert len(caplog.records) == 1
    rec = caplog.records[0]
    assert rec.sap_user == "KLEINK"
    assert rec.sap_host == "myhost.example.com"
    assert rec.sap_mandant == "100"


def test_on_call_tool_without_identity_omits_fields(caplog):
    """Without sap_identity, identity fields should not appear on the log record."""
    mw = ToolCallLoggingMiddleware()

    async def _call_next(_ctx):
        return "ok"

    with caplog.at_level("INFO", logger=_LOGGER_NAME):
        asyncio.run(mw.on_call_tool(_make_context(), _call_next))

    assert len(caplog.records) == 1
    rec = caplog.records[0]
    assert not hasattr(rec, "sap_user")
    assert not hasattr(rec, "sap_host")
    assert not hasattr(rec, "sap_mandant")


# ---------------------------------------------------------------------------
# request_id: per-call correlation
# ---------------------------------------------------------------------------


def test_new_request_id_returns_valid_uuid_v7():
    """new_request_id must produce a parseable UUID with version bits = 7."""
    raw = new_request_id()
    parsed = uuid.UUID(raw)
    assert parsed.version == 7


def test_new_request_id_is_unique_across_calls():
    """Two consecutive calls must yield distinct IDs (collision practically impossible)."""
    a = new_request_id()
    b = new_request_id()
    assert a != b


def test_on_call_tool_success_includes_request_id(caplog):
    """The success log record must carry a UUID v7 request_id."""
    mw = ToolCallLoggingMiddleware()

    async def _call_next(_ctx):
        return "ok"

    with caplog.at_level("INFO", logger=_LOGGER_NAME):
        asyncio.run(mw.on_call_tool(_make_context(), _call_next))

    assert len(caplog.records) == 1
    rec = caplog.records[0]
    parsed = uuid.UUID(rec.request_id)
    assert parsed.version == 7


def test_on_call_tool_failure_includes_request_id(caplog):
    """Failure path must also emit a request_id on the warning record."""
    mw = ToolCallLoggingMiddleware()

    async def _call_next(_ctx):
        raise RuntimeError("boom")

    with caplog.at_level("WARNING", logger=_LOGGER_NAME):
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(mw.on_call_tool(_make_context(), _call_next))

    assert len(caplog.records) == 1
    rec = caplog.records[0]
    parsed = uuid.UUID(rec.request_id)
    assert parsed.version == 7


def test_on_call_tool_request_id_distinct_across_calls(caplog):
    """Two consecutive tool calls must produce two distinct request_ids in log records."""
    mw = ToolCallLoggingMiddleware()

    async def _call_next(_ctx):
        return "ok"

    with caplog.at_level("INFO", logger=_LOGGER_NAME):
        asyncio.run(mw.on_call_tool(_make_context(), _call_next))
        asyncio.run(mw.on_call_tool(_make_context(), _call_next))

    assert len(caplog.records) == 2
    assert caplog.records[0].request_id != caplog.records[1].request_id
