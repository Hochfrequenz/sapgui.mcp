"""Unit tests for the integration fixture's "which connections to close" decision (#1009)."""

from __future__ import annotations

import pytest

from unittests.desktop.conftest import connection_index_from_session_id, connections_to_close


def test_nothing_before_closes_everything_descending() -> None:
    assert connections_to_close([], ["a", "b"]) == [1, 0]


def test_preexisting_connection_survives() -> None:
    assert connections_to_close(["user"], ["user", "ours"]) == [1]


def test_nothing_new_closes_nothing() -> None:
    assert connections_to_close(["user"], ["user"]) == []


def test_preexisting_survives_when_renumbered() -> None:
    # A lower pre-existing connection was closed by the user during the run, so "user2" moved from con[1] to con[0].
    assert connections_to_close(["user1", "user2"], ["user2", "ours"]) == [1]


def test_preexisting_survives_when_fixture_connection_inserted_before_it() -> None:
    assert connections_to_close(["user"], ["ours", "user"]) == [0]


def test_duplicate_keys_are_matched_as_multiset() -> None:
    # Two identical pre-existing connections plus one identical new one: only one gets closed.
    assert connections_to_close(["x", "x"], ["x", "x", "x"]) == [2]


def test_owned_connection_is_closed_even_if_key_was_known_before() -> None:
    assert connections_to_close(["x"], ["x"], owned_indexes={0}) == [0]


def test_empty_current_list() -> None:
    assert connections_to_close(["user"], []) == []


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
