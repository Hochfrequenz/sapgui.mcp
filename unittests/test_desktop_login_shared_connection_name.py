"""Regression tests for issue #659 (desktop side).

When two ``systems.json`` entries share the same ``connection_name`` — the
common topology of "one entry per Mandant on the same SAP system" — the
*second* ``sap_login`` call would silently land in the *first* entry's
already-logged-in client.

Root cause: SAP GUI's ``OpenConnection(name)`` returns the existing
connection by description rather than opening a fresh one. sapsucker's
credential-fill block (``if session.info.program == "SAPMSYST":``) is then
skipped because the returned session is already past the login dynpro, so
the requested ``client``/``user`` are never typed in.

Fix: ``DesktopBackend.login`` now closes any matching connection up front
(forcing ``OpenConnection`` to open fresh), and verifies the resulting
session is actually in the requested client (failing loudly on mismatch).

These tests run on Linux: they construct a ``DesktopBackend`` via
``__new__`` so no real ComThread is spawned, and stub ``com.run`` to a
synchronous pass-through.
"""

# pylint: disable=protected-access

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sapwebguimcp.backend.desktop import DesktopBackend, _close_existing_connections
from sapwebguimcp.backend.desktop._session_registry import DesktopSessionRegistry


def _make_backend() -> DesktopBackend:
    """DesktopBackend with a fresh registry, mocked com.run, and a real lock."""
    backend = DesktopBackend.__new__(DesktopBackend)
    backend.registry = DesktopSessionRegistry()
    backend.com = MagicMock()
    backend._mutation_lock = asyncio.Lock()

    async def passthrough(fn: Any) -> Any:
        return fn()

    backend.com.run = passthrough  # type: ignore[method-assign]
    return backend


def _make_session(client: str = "100", user: str = "TESTUSER") -> MagicMock:
    """Mock GuiSession whose ``info.client`` and ``info.user`` are configurable."""
    session = MagicMock()
    session.info.client = client
    session.info.user = user
    return session


# ---------------------------------------------------------------------------
# DesktopBackend.login wiring
# ---------------------------------------------------------------------------


class TestLoginClosesExistingConnection:
    """``DesktopBackend.login`` must close existing matches before sapsucker_login."""

    @pytest.mark.anyio
    async def test_close_runs_before_sapsucker_login(self) -> None:
        """The close-existing helper must be called *before* _sapsucker_login.

        Otherwise OpenConnection would dedupe to the existing connection and
        sapsucker would skip the credential-fill block — the exact bug.
        """
        backend = _make_backend()
        call_order: list[str] = []

        def fake_close(name: str) -> int:
            call_order.append(f"close:{name}")
            return 1

        def fake_login(**_kwargs: Any) -> MagicMock:
            call_order.append("sapsucker_login")
            return _make_session(client="210")

        with (
            patch("sapwebguimcp.backend.desktop._close_existing_connections", side_effect=fake_close),
            patch("sapwebguimcp.backend.desktop._sapsucker_login", side_effect=fake_login),
        ):
            result = await backend.login(
                url="ignored",
                username="MUSTERFRAUM",
                password="pw",
                client="210",
                language="DE",
                connection_name="HF S/4",
            )

        assert result.success is True
        assert call_order == ["close:HF S/4", "sapsucker_login"]

    @pytest.mark.anyio
    async def test_close_passes_requested_connection_name(self) -> None:
        """The connection_name argument must be forwarded verbatim — no munging."""
        backend = _make_backend()
        seen: list[str] = []

        with (
            patch(
                "sapwebguimcp.backend.desktop._close_existing_connections",
                side_effect=lambda name: seen.append(name) or 0,
            ),
            patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=_make_session(client="100")),
        ):
            await backend.login(
                url="x",
                username="u",
                password="p",
                client="100",
                language="EN",
                connection_name="HF S/4",
            )

        assert seen == ["HF S/4"]

    @pytest.mark.anyio
    async def test_close_returning_zero_does_not_block_login(self) -> None:
        """When no existing connection matches, login still proceeds normally."""
        backend = _make_backend()

        with (
            patch("sapwebguimcp.backend.desktop._close_existing_connections", return_value=0),
            patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=_make_session(client="100")),
        ):
            result = await backend.login(
                url="x",
                username="u",
                password="p",
                client="100",
                language="EN",
                connection_name="FRESH",
            )

        assert result.success is True
        assert backend.registry.list_sessions() == ["s1"]


# ---------------------------------------------------------------------------
# Post-login client verification
# ---------------------------------------------------------------------------


class TestLoginVerifiesActualClient:
    """``DesktopBackend.login`` must fail loudly if the new session lands in the wrong client."""

    @pytest.mark.anyio
    async def test_client_match_succeeds(self) -> None:
        """Happy path: actual client matches requested client → success, registered as s1."""
        backend = _make_backend()
        session = _make_session(client="210", user="MUSTERFRAUM")

        with (
            patch("sapwebguimcp.backend.desktop._close_existing_connections", return_value=0),
            patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=session),
        ):
            result = await backend.login(
                url="x",
                username="MUSTERFRAUM",
                password="pw",
                client="210",
                language="DE",
                connection_name="HF S/4",
            )

        assert result.success is True
        assert result.user == "MUSTERFRAUM"
        assert backend.registry.get_session("s1") is session

    @pytest.mark.anyio
    async def test_client_mismatch_returns_failure(self) -> None:
        """Mismatch: actual client differs from requested → loud failure, registry untouched."""
        backend = _make_backend()
        # Pre-existing session that must NOT be wiped by a failed login.
        existing = _make_session(client="100")
        backend.registry.register(existing)

        wrong_client = _make_session(client="100", user="MUSTERMANNM")  # but we asked for 210

        with (
            patch("sapwebguimcp.backend.desktop._close_existing_connections", return_value=0),
            patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=wrong_client),
        ):
            result = await backend.login(
                url="x",
                username="MUSTERFRAUM",
                password="pw",
                client="210",
                language="DE",
                connection_name="HF S/4",
            )

        assert result.success is False
        assert result.error is not None
        assert "'100'" in result.error and "'210'" in result.error
        assert "HF S/4" in result.error
        # Registry must be untouched on failure (#633 contract).
        assert backend.registry.get_session("s1") is existing

    @pytest.mark.anyio
    async def test_failure_does_not_call_keepalive_or_register(self) -> None:
        """A client-mismatch failure must NOT register the bogus session as s1."""
        backend = _make_backend()
        wrong = _make_session(client="100")

        with (
            patch("sapwebguimcp.backend.desktop._close_existing_connections", return_value=0),
            patch("sapwebguimcp.backend.desktop._sapsucker_login", return_value=wrong),
        ):
            result = await backend.login(
                url="x",
                username="u",
                password="p",
                client="999",
                language="EN",
                connection_name="X",
            )

        assert result.success is False
        assert backend.registry.list_sessions() == []


# ---------------------------------------------------------------------------
# _close_existing_connections internals
# ---------------------------------------------------------------------------


class TestCloseExistingConnectionsHelper:
    """Direct unit tests for the COM-side helper."""

    def _fake_app_with_connections(self, descriptions: list[str]) -> MagicMock:
        """Build a mock GuiApplication whose Children mimic SAP GUI's COM collection."""
        app = MagicMock()
        children = MagicMock()
        children.Count = len(descriptions)
        conns: list[MagicMock] = []
        for desc in descriptions:
            conn = MagicMock()
            conn.Description = desc
            conns.append(conn)

        # SAP GUI's Children collection is index-callable: ``children(i)`` → child.
        children.side_effect = lambda i: conns[i]
        app.com.Children = children
        # Expose for assertions in the tests
        app._mock_conns = conns  # type: ignore[attr-defined]
        return app

    def test_returns_zero_when_sap_gui_not_running(self) -> None:
        """``SapGui.connect()`` raising ``SapConnectionError`` is the no-op path."""
        from sapsucker._errors import SapConnectionError

        with patch("sapwebguimcp.backend.desktop.SapGui") as sap_gui:
            sap_gui.connect.side_effect = SapConnectionError("not running")
            assert _close_existing_connections("HF S/4") == 0

    def test_closes_only_matching_connection(self) -> None:
        """Connections with a different description must be left alone."""
        app = self._fake_app_with_connections(["HF S/4", "HFR3", "HF S/4"])

        with patch("sapwebguimcp.backend.desktop.SapGui") as sap_gui:
            sap_gui.connect.return_value = app
            closed = _close_existing_connections("HF S/4")

        assert closed == 2
        # Only the two HF S/4 connections were closed.
        app._mock_conns[0].CloseConnection.assert_called_once()  # type: ignore[attr-defined]
        app._mock_conns[2].CloseConnection.assert_called_once()  # type: ignore[attr-defined]
        # The HFR3 entry survives.
        app._mock_conns[1].CloseConnection.assert_not_called()  # type: ignore[attr-defined]

    def test_closes_zero_when_no_match(self) -> None:
        app = self._fake_app_with_connections(["HFR3", "OTHER"])

        with patch("sapwebguimcp.backend.desktop.SapGui") as sap_gui:
            sap_gui.connect.return_value = app
            closed = _close_existing_connections("HF S/4")

        assert closed == 0
        for conn in app._mock_conns:  # type: ignore[attr-defined]
            conn.CloseConnection.assert_not_called()

    def test_iterates_in_reverse(self) -> None:
        """Reverse iteration is required because Children mutates on close.

        We assert the access *order* on the children collection rather than
        introspecting source — that way the test fails for the right reason
        if a refactor switches to forward iteration.
        """
        app = self._fake_app_with_connections(["HF S/4", "HF S/4", "HF S/4"])
        access_order: list[int] = []
        app.com.Children.side_effect = lambda i: (access_order.append(i), app._mock_conns[i])[1]  # type: ignore[attr-defined]

        with patch("sapwebguimcp.backend.desktop.SapGui") as sap_gui:
            sap_gui.connect.return_value = app
            _close_existing_connections("HF S/4")

        assert access_order == [2, 1, 0]

    def test_close_failure_is_swallowed(self) -> None:
        """A single failing CloseConnection must not abort the loop or raise."""
        app = self._fake_app_with_connections(["HF S/4", "HF S/4"])
        app._mock_conns[1].CloseConnection.side_effect = RuntimeError("COM blew up")  # type: ignore[attr-defined]

        with patch("sapwebguimcp.backend.desktop.SapGui") as sap_gui:
            sap_gui.connect.return_value = app
            closed = _close_existing_connections("HF S/4")

        # The successful close still counts; the failure is swallowed.
        assert closed == 1
        app._mock_conns[0].CloseConnection.assert_called_once()  # type: ignore[attr-defined]
