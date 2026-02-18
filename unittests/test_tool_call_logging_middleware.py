"""Tests for tool call logging middleware identity injection."""

import pytest

from sapwebguimcp.middleware.logging import (
    ToolCallLoggingMiddleware,
    _sessions_ref,
    set_sap_identity,
)
from sapwebguimcp.models.middleware import SapIdentity, SessionStats


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
    from pathlib import Path

    js_path = Path("src/sapwebguimcp/js/extract_sap_user.js")
    assert js_path.exists()
    content = js_path.read_text()
    assert "sysInfoAreaMenuItemSAPITS_MBAR_USER" in content
    assert "lsdata" in content
    assert "aria-label" in content
