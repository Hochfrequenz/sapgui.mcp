"""Unit tests for the integration fixture's "which connections to close" decision (#1009)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from unittests.desktop.conftest import (
    connection_index_from_session_id,
    connections_to_close,
    read_connection_guids,
    snapshot_before_guids,
    snapshot_connection_guids,
)


def fs(*guids: str) -> frozenset[str]:
    return frozenset(guids)


def make_conn(*guids: object) -> MagicMock:
    """Fake connection; a guid that is an Exception instance makes reading that session raise."""
    conn = MagicMock()
    conn.Children.Count = len(guids)
    sessions = []
    for guid in guids:
        ses = MagicMock()
        if isinstance(guid, Exception):
            type(ses.Info).SystemSessionId = property(lambda _self, e=guid: (_ for _ in ()).throw(e))
        else:
            ses.Info.SystemSessionId = guid
        sessions.append(ses)
    conn.Children.side_effect = lambda j: sessions[j]
    return conn


def make_app(*conns: MagicMock) -> MagicMock:
    app = MagicMock()
    app.com.Children.Count = len(conns)
    app.com.Children.side_effect = lambda i: conns[i]
    return app


# --- connections_to_close ---------------------------------------------------


def test_new_connection_is_closed_preexisting_survives() -> None:
    assert connections_to_close({"u"}, [fs("u"), fs("n")]) == [1]


def test_nothing_new_closes_nothing() -> None:
    assert connections_to_close({"u"}, [fs("u")]) == []


def test_survives_renumbering() -> None:
    assert connections_to_close({"u1", "u2"}, [fs("u2"), fs("n")]) == [1]


def test_guid_overlap_with_before_is_not_closable() -> None:
    # Connection holds one old and one new session: the old one proves it is the user's.
    assert connections_to_close({"u"}, [fs("u", "n")]) == []


def test_unreadable_connection_is_not_closable() -> None:
    assert connections_to_close(set(), [None, fs("n")]) == [1]


def test_unreadable_but_owned_is_closed() -> None:
    assert connections_to_close({"u"}, [None, fs("u")], owned_indexes={0}) == [0]


def test_owned_closed_even_if_guid_known_before() -> None:
    assert connections_to_close({"x"}, [fs("x")], owned_indexes={0}) == [0]


def test_unknown_before_snapshot_closes_owned_only() -> None:
    assert connections_to_close(None, [fs("a"), fs("b"), fs("c")], owned_indexes={2}) == [2]


def test_unknown_before_snapshot_no_owned_closes_nothing() -> None:
    assert connections_to_close(None, [fs("a"), fs("b")]) == []


def test_empty_guid_set_is_not_closable() -> None:
    assert connections_to_close(set(), [fs()]) == []


def test_owned_index_out_of_range_ignored() -> None:
    assert connections_to_close(set(), [], owned_indexes={3}) == []


def test_descending_order() -> None:
    assert connections_to_close(set(), [fs("a"), fs("b"), fs("c")]) == [2, 1, 0]


# --- read_connection_guids --------------------------------------------------


def test_read_all_sessions() -> None:
    assert read_connection_guids(make_conn("a", "b")) == fs("a", "b")


def test_read_zero_sessions_is_none() -> None:
    assert read_connection_guids(make_conn()) is None


def test_read_empty_guid_is_none() -> None:
    assert read_connection_guids(make_conn("a", "")) is None


def test_read_raising_child_is_none() -> None:
    assert read_connection_guids(make_conn("a", RuntimeError("busy"))) is None


def test_read_raising_children_is_none() -> None:
    conn = MagicMock()
    type(conn).Children = property(lambda _self: (_ for _ in ()).throw(RuntimeError("disconnected")))
    assert read_connection_guids(conn) is None


# --- snapshots --------------------------------------------------------------


def test_snapshot_connection_guids() -> None:
    app = make_app(make_conn("a"), make_conn(), make_conn("b", "c"))
    assert snapshot_connection_guids(app) == [fs("a"), None, fs("b", "c")]


def test_before_snapshot_is_union() -> None:
    assert snapshot_before_guids(make_app(make_conn("a"), make_conn("b", "c"))) == fs("a", "b", "c")


def test_before_snapshot_no_connections_is_empty() -> None:
    assert snapshot_before_guids(make_app()) == fs()


def test_before_snapshot_with_unreadable_connection_is_none() -> None:
    assert snapshot_before_guids(make_app(make_conn("a"), make_conn("b", RuntimeError("popup")))) is None


def test_before_snapshot_failure_is_none() -> None:
    app = MagicMock()
    type(app.com).Children = property(lambda _self: (_ for _ in ()).throw(RuntimeError("com")))
    assert snapshot_before_guids(app) is None


def test_before_snapshot_failure_degrades_to_owned_only() -> None:
    app = MagicMock()
    type(app.com).Children = property(lambda _self: (_ for _ in ()).throw(RuntimeError("com")))
    before = snapshot_before_guids(app)
    assert connections_to_close(before, [fs("user"), fs("ours")], owned_indexes={1}) == [1]


# --- connection_index_from_session_id ---------------------------------------


@pytest.mark.parametrize(
    ("session_id", "expected"),
    [
        ("/app/con[0]/ses[0]", 0),
        ("/app/con[12]/ses[3]", 12),
        ("/app/con[1]", 1),
        ("garbage", None),
        ("", None),
    ],
)
def test_connection_index_from_session_id(session_id: str, expected: int | None) -> None:
    assert connection_index_from_session_id(session_id) == expected
