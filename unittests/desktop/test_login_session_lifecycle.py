"""Tests for ``DesktopBackend.login`` session lifecycle (issues #633 and #671).

Two contracts are pinned down here:

- **#633 — dead-session recovery**: a stale GuiSession proxy left in the
  registry after an external SAP GUI death must not shadow a fresh login.
  Originally fixed by calling ``self.registry.clear()`` on every login;
  #671 changed the mechanism to ``await self._reconcile_locked()`` (probe
  every tracked session, prune only the dead ones), which preserves #633
  while no longer dropping live sessions.

- **#671 — parallel-multi-mandant**: each successful ``login()`` adds a
  fresh session to the registry **without dropping any existing live
  sessions**. The LLM can be logged into the same SAP Logon entry as
  multiple distinct ``(client, user)`` tuples concurrently — they all
  coexist as ``s1``, ``s2``, ``s3``, ... and tools address them via
  the ``session_id`` parameter.

These tests run on Linux: they mock ``_sapsucker_login`` so no real COM
is needed, and use the same ``passthrough`` shape as
``test_desktop_backend_reconcile.py`` so the reconcile probe inside
``login()`` works against mock sessions.
"""

# pylint: disable=protected-access

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from unittests.desktop.conftest import make_mock_session


def _make_backend() -> DesktopBackend:
    """Build a DesktopBackend with a real mutation lock and a passthrough COM stub.

    Goes through ``__init__`` so ``self._mutation_lock`` is a real
    ``asyncio.Lock`` (the lock that ``login()`` now holds for the entire
    flow). The COM thread is mocked and ``com.run`` is replaced with a
    synchronous passthrough that accepts the ``max_retries`` keyword
    argument the reconcile probe passes.
    """
    backend = DesktopBackend(com_thread=MagicMock())

    async def passthrough(fn: Any, *, max_retries: int | None = None) -> Any:  # pylint: disable=unused-argument
        return fn()

    backend.com.run = passthrough  # type: ignore[method-assign]
    return backend


def _kill_session(session: MagicMock) -> None:
    """Configure a mock session so the reconcile probe treats it as dead.

    The reconcile probe at ``DesktopBackend._reconcile_locked`` calls
    ``s.com.FindById('wnd[0]').Type`` and treats any exception as "this
    session is dead". The conftest ``make_mock_session`` helper configures
    ``session.find_by_id`` (the Python wrapper) but does not touch
    ``session.com.FindById`` (raw COM), so by default the probe succeeds.
    Calling this helper makes the probe raise.
    """
    session.com = MagicMock()
    session.com.FindById.side_effect = RuntimeError("session is dead")


# ---------------------------------------------------------------------------
# Cold start
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_first_login_registers_as_s1() -> None:
    """A fresh backend's first login produces s1 and reports it in LoginResult."""
    backend = _make_backend()
    fresh = make_mock_session()

    with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is True
    assert result.session_id == "s1"
    assert backend.registry.list_sessions() == ["s1"]
    assert backend.registry.get_session("s1") is fresh


@pytest.mark.anyio
async def test_login_result_carries_session_id() -> None:
    """``LoginResult.session_id`` is the new contract for #671 — the LLM
    needs to know which registry slot it just got so it can address that
    specific login on subsequent tool calls when multiple are active.
    """
    backend = _make_backend()
    backend.registry.register(make_mock_session())  # pre-existing s1
    fresh = make_mock_session()

    with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="210",
            language="DE",
            connection_name="TEST_CONN",
        )

    assert result.success is True
    assert result.session_id == "s2"  # new id, not the pre-existing s1


# ---------------------------------------------------------------------------
# #671 — parallel multi-mandant: re-login keeps live sessions
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_relogin_with_alive_session_keeps_both() -> None:
    """The core #671 contract: a second ``login()`` does NOT drop the first
    live session. Both coexist in the registry, addressable via session_id.

    Scenario: agent logs in as user A in client 100, then later logs in as
    user B in client 210 via the same SAP Logon entry. Both sessions are
    alive at the same time (sapsucker 0.5.1 opens parallel COM connections).
    Pre-#671, the consumer-side ``registry.clear()`` would have dropped
    the first session even though its underlying COM session was alive.
    """
    backend = _make_backend()

    first = make_mock_session(client="100", user="MUSTERMANNM")
    with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=first):
        first_result = await backend.login(
            url="ignored",
            username="MUSTERMANNM",
            password="pw",
            client="100",
            language="DE",
            connection_name="HF S/4",
        )

    second = make_mock_session(client="210", user="MUSTERFRAUM")
    with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=second):
        second_result = await backend.login(
            url="ignored",
            username="MUSTERFRAUM",
            password="pw",
            client="210",
            language="DE",
            connection_name="HF S/4",
        )

    assert first_result.success is True
    assert second_result.success is True
    assert first_result.session_id == "s1"
    assert second_result.session_id == "s2"
    assert sorted(backend.registry.list_sessions()) == ["s1", "s2"]
    assert backend.registry.get_session("s1") is first
    assert backend.registry.get_session("s2") is second
    # primary still resolves to s1 — predictable, lowest-id wins
    assert backend.registry.primary_session == "s1"


@pytest.mark.anyio
async def test_relogin_preserves_multi_session_state_and_bindings() -> None:
    """Pre-existing /o sub-sessions (s2, s3, ...) and their agent bindings
    survive a re-login, as long as they're alive. Replaces the old
    ``test_relogin_drops_multi_session_state`` test which asserted the
    opposite (and was the wrong contract under #671).
    """
    backend = _make_backend()
    backend.registry.register(make_mock_session())  # s1
    backend.registry.register(make_mock_session())  # s2
    backend.registry.register(make_mock_session())  # s3
    backend.registry.bind("s2", "agent_a")
    assert sorted(backend.registry.list_sessions()) == ["s1", "s2", "s3"]
    assert backend.registry.get_bound_agent("s2") == "agent_a"

    fresh = make_mock_session()
    with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is True
    assert result.session_id == "s4"
    assert sorted(backend.registry.list_sessions()) == ["s1", "s2", "s3", "s4"]
    # The new session is in the registry alongside the others.
    assert backend.registry.get_session("s4") is fresh
    # Pre-existing agent binding survives.
    assert backend.registry.get_bound_agent("s2") == "agent_a"


# ---------------------------------------------------------------------------
# #633 — dead-session recovery (still works after #671)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_relogin_after_external_sap_gui_death_prunes_dead_session() -> None:
    """#633 regression: a stale ``s1`` left over from external SAP GUI death
    must NOT shadow a fresh login. The reconcile-on-login path probes the
    dead session, finds it unreachable, and prunes it before registering
    the new session.

    Pre-#671 this was achieved by ``self.registry.clear()`` (which dropped
    *every* session indiscriminately). Post-#671 the same outcome is
    delivered by ``await self._reconcile_locked()`` (which only drops the
    dead ones), so live multi-session state survives — see
    ``test_relogin_with_alive_session_keeps_both`` for the other half.
    """
    backend = _make_backend()

    # Pre-existing s1 from a successful login.
    dead = make_mock_session()
    backend.registry.register(dead)
    assert backend.registry.list_sessions() == ["s1"]

    # External event kills the SAP GUI (or just that connection). The
    # registry doesn't notice on its own — the next reconcile probe does.
    _kill_session(dead)

    # Re-login with a fresh session.
    fresh = make_mock_session()
    with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is True
    # The dead session was pruned by the reconcile call.
    assert dead not in backend.registry._sessions.values()
    # The fresh session is registered.
    assert fresh in backend.registry._sessions.values()
    # primary_session resolves to a LIVE session, never the dead one.
    primary = backend.registry.primary_session
    assert backend.registry.get_session(primary) is fresh


@pytest.mark.anyio
async def test_relogin_prunes_only_dead_keeps_alive() -> None:
    """Mixed registry: when re-login runs reconcile, only the dead session
    is pruned. The alive one survives alongside the new login.
    """
    backend = _make_backend()

    alive = make_mock_session()
    dead = make_mock_session()
    backend.registry.register(alive)  # s1
    backend.registry.register(dead)  # s2
    _kill_session(dead)

    fresh = make_mock_session()
    with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=fresh):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is True
    surviving = list(backend.registry._sessions.values())
    assert alive in surviving
    assert dead not in surviving
    assert fresh in surviving


# ---------------------------------------------------------------------------
# Failure path: existing registry must be untouched
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_failed_login_does_not_touch_registry() -> None:
    """If ``_sapsucker_login`` raises, the existing registry must be untouched
    — including no reconcile, no pruning, no new registration. A transient
    login failure (wrong password, COM hiccup, sapsucker post-login mismatch)
    must not silently destroy a working session that the user might still
    want to recover via a retry.
    """
    backend = _make_backend()
    existing = make_mock_session()
    backend.registry.register(existing)
    assert backend.registry.list_sessions() == ["s1"]

    def boom(**_kwargs: Any) -> Any:
        raise RuntimeError("connect refused")

    with patch("sapguimcp.backend.desktop._sapsucker_login", side_effect=boom):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is False
    assert result.session_id is None
    assert backend.registry.list_sessions() == ["s1"]
    assert backend.registry.get_session("s1") is existing


@pytest.mark.anyio
async def test_failed_login_does_not_prune_dead_sessions_either() -> None:
    """The failure path is pure no-op on the registry, even when a dead
    session is sitting there. The next *successful* login (or any other
    reconcile-bearing operation) will clean it up. Surfacing transient
    failures without touching the registry keeps the failure mode local
    and predictable.
    """
    backend = _make_backend()
    dead = make_mock_session()
    backend.registry.register(dead)
    _kill_session(dead)

    def boom(**_kwargs: Any) -> Any:
        raise RuntimeError("transient")

    with patch("sapguimcp.backend.desktop._sapsucker_login", side_effect=boom):
        result = await backend.login(
            url="ignored",
            username="user",
            password="pass",
            client="100",
            language="EN",
            connection_name="TEST_CONN",
        )

    assert result.success is False
    # Dead session still there — failed login does not run reconcile.
    assert backend.registry.list_sessions() == ["s1"]
