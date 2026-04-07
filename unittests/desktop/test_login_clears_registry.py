"""Tests for ``DesktopBackend.login`` clearing the session registry (issue #633).

These tests run on Linux: they mock ``_sapsucker_login`` so no real COM is
needed, and they don't carry the file-level ``win32`` skip mark that
``test_desktop_backend.py`` has.

Background: before the fix, ``DesktopBackend.login()`` registered the new
session without dropping prior ones. After an external SAP GUI death + a
recovery ``sap_login``, the registry held both the dead ``s1`` and the fresh
``s2``, and ``primary_session`` resolved to the still-present (dead) ``s1``,
breaking every subsequent tool call. The fix calls ``self.registry.clear()``
before ``self.registry.register(session)`` so re-login produces a clean ``s1``.
"""

# pylint: disable=protected-access

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sapwebguimcp.backend.desktop import DesktopBackend
from unittests.desktop.conftest import make_mock_session


def _make_backend_with_passthrough_com() -> DesktopBackend:
    """Build a DesktopBackend whose ``com.run`` synchronously executes its arg."""
    backend = DesktopBackend(com_thread=MagicMock())

    async def passthrough(fn):
        return fn()

    backend.com.run = passthrough  # type: ignore[method-assign]
    return backend


@pytest.mark.anyio
async def test_first_login_registers_as_s1() -> None:
    """Sanity check: a fresh backend's first login produces s1."""
    backend = _make_backend_with_passthrough_com()
    fresh = make_mock_session()
    with patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )
    assert result.success is True
    assert backend.registry.list_sessions() == ["s1"]
    assert backend.registry.get_session("s1") is fresh


@pytest.mark.anyio
async def test_relogin_drops_stale_session_and_returns_clean_s1() -> None:
    """Regression for #633.

    Pre-fix sequence:
      1. login → registry has s1 (dead later)
      2. external SAP GUI death (registry doesn't notice)
      3. login → registry has s1 (dead) AND s2 (fresh)
      4. primary_session → "s1" (sticky), tools fail on dead proxy

    Post-fix: step 3's login calls registry.clear() first, so the registry
    only contains the fresh session, registered as s1, and primary_session
    resolves to it.
    """
    backend = _make_backend_with_passthrough_com()

    # Step 1: original login.
    dead = make_mock_session(transaction="DEAD")
    with patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=dead):
        await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )
    assert backend.registry.list_sessions() == ["s1"]
    assert backend.registry.get_session("s1") is dead

    # Step 3: re-login. Simulates a fresh SAP GUI process producing a new
    # GuiSession proxy distinct from the dead one.
    fresh = make_mock_session(transaction="FRESH")
    with patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is True
    # The dead session is gone.
    assert dead not in backend.registry._sessions.values()
    # Only one session remains.
    assert backend.registry.list_sessions() == ["s1"]
    # primary_session resolves to the FRESH session, not the dead one.
    assert backend.registry.primary_session == "s1"
    assert backend.registry.get_session(backend.registry.primary_session) is fresh
    assert backend.registry.get_session(None) is fresh


@pytest.mark.anyio
async def test_relogin_drops_multi_session_state() -> None:
    """Multi-session state from ``open_new_session`` is also dropped on re-login.

    Re-login is treated as a desktop reset, not an addition. If a user has
    multiple sessions open and re-logs in, all of them are wiped — that's
    the contract documented on ``DesktopSessionRegistry.clear()``.
    """
    backend = _make_backend_with_passthrough_com()
    backend.registry.register(make_mock_session())  # s1
    backend.registry.register(make_mock_session())  # s2
    backend.registry.register(make_mock_session())  # s3
    backend.registry.bind("s2", "agent_a")
    assert sorted(backend.registry.list_sessions()) == ["s1", "s2", "s3"]

    fresh = make_mock_session(transaction="FRESH")
    with patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert backend.registry.list_sessions() == ["s1"]
    assert backend.registry.get_session("s1") is fresh
    # Bindings from before the re-login are also gone.
    assert backend.registry.get_bound_agent("s1") is None


@pytest.mark.anyio
async def test_failed_login_does_not_clear_registry() -> None:
    """If ``_sapsucker_login`` raises, the existing registry must be untouched.

    Otherwise a transient login failure would silently destroy a working
    session that the user might still want to recover via a retry.
    """
    backend = _make_backend_with_passthrough_com()
    existing = make_mock_session(transaction="EXISTING")
    backend.registry.register(existing)
    assert backend.registry.list_sessions() == ["s1"]

    def boom(**_kwargs):
        raise RuntimeError("connect refused")

    with patch("sapwebguimcp.backend.desktop._sapsucker_login", side_effect=boom):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is False
    assert backend.registry.list_sessions() == ["s1"]
    assert backend.registry.get_session("s1") is existing
