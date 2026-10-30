"""Unit tests for the integration fixture's connection teardown (#1009)."""

from __future__ import annotations

from unittest.mock import MagicMock

from unittests.desktop.conftest import close_owned_connections


def make_session(conn_id: str, conn: MagicMock | None = None) -> MagicMock:
    ses = MagicMock()
    ses.com.Parent = conn if conn is not None else MagicMock()
    ses.com.Parent.Id = conn_id
    return ses


def test_no_sessions_closes_nothing() -> None:
    assert close_owned_connections([]) == 0


def test_closes_the_connection_of_each_session() -> None:
    a, b = MagicMock(), MagicMock()
    n = close_owned_connections([make_session("/app/con[0]", a), make_session("/app/con[1]", b)])
    assert n == 2
    a.CloseConnection.assert_called_once()
    b.CloseConnection.assert_called_once()


def test_two_sessions_on_one_connection_close_it_once() -> None:
    conn = MagicMock()
    n = close_owned_connections([make_session("/app/con[0]", conn), make_session("/app/con[0]", conn)])
    assert n == 1
    conn.CloseConnection.assert_called_once()


def test_session_with_unreadable_parent_is_skipped() -> None:
    bad = MagicMock()
    type(bad.com).Parent = property(lambda _self: (_ for _ in ()).throw(RuntimeError("gone")))
    good = MagicMock()
    assert close_owned_connections([bad, make_session("/app/con[1]", good)]) == 1
    good.CloseConnection.assert_called_once()


def test_close_error_does_not_stop_the_others() -> None:
    a, b = MagicMock(), MagicMock()
    a.CloseConnection.side_effect = RuntimeError("busy")
    assert close_owned_connections([make_session("/app/con[0]", a), make_session("/app/con[1]", b)]) == 2
    b.CloseConnection.assert_called_once()
