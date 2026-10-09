"""Parsing the labels of the SE09 request list: the owner is only printed when it changes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo
from sapguimcp.tools.se09_tools import _lookup_transports_desktop, _parse_labels_to_requests


def _owners_and_descriptions(labels: list[str], default_owner: str = "") -> list[tuple[str, str, str]]:
    return [(r.request_number, r.owner, r.description) for r in _parse_labels_to_requests(labels, default_owner)]


def test_the_owner_of_the_first_request_is_carried_over_to_the_requests_that_do_not_print_one() -> None:
    labels = [
        "Requests of user USER1",
        "ABCK900001",
        "USER1",
        "first description",
        "ABCK900002",
        "second description",
        "ABCK900003",
    ]
    assert _owners_and_descriptions(labels) == [
        ("ABCK900001", "USER1", "first description"),
        ("ABCK900002", "USER1", "second description"),
        ("ABCK900003", "USER1", ""),
    ]


def test_a_change_of_the_owner_is_picked_up_and_stays_until_the_next_change() -> None:
    labels = ["ABCK900001", "USER1", "a", "ABCK900002", "b", "ABCK900003", "USER2", "c", "ABCK900004", "d"]
    assert [owner for _, owner, _ in _owners_and_descriptions(labels)] == ["USER1", "USER1", "USER2", "USER2"]


def test_a_description_is_no_owner_and_the_default_owner_applies_before_the_first_printed_one() -> None:
    labels = [
        "ABCK900001",
        "a description with blanks",
        "ABCK900002",
        "lower case",
        "ABCK900003",
        "Z_A_LONG_OBJECT_NAME",
    ]
    assert _owners_and_descriptions(labels, default_owner="USER9") == [
        ("ABCK900001", "USER9", "a description with blanks"),
        ("ABCK900002", "USER9", "lower case"),
        ("ABCK900003", "USER9", "Z_A_LONG_OBJECT_NAME"),  # longer than a user name
    ]


def test_a_request_without_any_further_label_has_neither_owner_nor_description() -> None:
    assert _owners_and_descriptions(["ABCK900001"], default_owner="USER1") == [("ABCK900001", "USER1", "")]


def test_a_request_number_that_appears_twice_is_listed_once() -> None:
    assert len(_parse_labels_to_requests(["ABCK900001", "USER1", "x", "ABCK900001", "USER2", "y"], "")) == 1


def test_a_one_word_upper_case_description_is_no_owner_once_an_owner_is_known() -> None:
    labels = ["ABCK900001", "USER1", "first", "ABCK900002", "HOTFIX", "ABCK900003", "TEST", "ABCK900004"]
    assert _owners_and_descriptions(labels) == [
        ("ABCK900001", "USER1", "first"),
        ("ABCK900002", "USER1", "HOTFIX"),
        ("ABCK900003", "USER1", "TEST"),
        ("ABCK900004", "USER1", ""),
    ]


def test_the_owner_of_the_first_request_is_taken_even_without_a_description() -> None:
    assert _owners_and_descriptions(["ABCK900001", "USER1", "ABCK900002", "x"]) == [
        ("ABCK900001", "USER1", ""),
        ("ABCK900002", "USER1", "x"),
    ]


def test_the_owner_of_the_first_request_is_taken_with_a_username_filter_too() -> None:
    # a lookup for USER2: the default owner is the filter, the first request prints its owner without a description
    assert _owners_and_descriptions(["ABCK900001", "USER2", "ABCK900002", "x"], default_owner="USER2") == [
        ("ABCK900001", "USER2", ""),
        ("ABCK900002", "USER2", "x"),
    ]
    # and with a different printed owner than the filter (a pattern filter): the printed one wins
    assert _owners_and_descriptions(["ABCK900001", "USER3", "ABCK900002"], default_owner="USER*") == [
        ("ABCK900001", "USER3", ""),
        ("ABCK900002", "USER3", ""),
    ]


# --- the desktop lookup reads every label, including repeated ones ------------------------------------------------


def _desktop_backend(labels: list[str]) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    for name in ("wait_for_ready", "click_button"):
        setattr(backend, name, AsyncMock())
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.get_screen_info = AsyncMock(return_value=ScreenInfo(title="Requests", url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.get_screen_text = AsyncMock(return_value=SimpleNamespace(labels=labels))
    return backend


@pytest.mark.anyio
async def test_the_desktop_lookup_reads_the_labels_without_de_duplication() -> None:
    # USER1, then USER2, then USER1 again: the owner label that returns must not be dropped, and neither must a
    # description that two requests share
    labels = [
        "ABCK900001",
        "USER1",
        "shared description",
        "ABCK900002",
        "USER2",
        "shared description",
        "ABCK900003",
        "USER1",
        "shared description",
    ]
    backend = _desktop_backend(labels)
    with patch("sapguimcp.tools.se09_tools._set_se09_selection_screen", AsyncMock()):
        result = await _lookup_transports_desktop(backend, None, "all", "all")
    backend.get_screen_text.assert_awaited_once_with(keep_duplicate_labels=True)
    assert [(r.request_number, r.owner, r.description) for r in result.requests] == [
        ("ABCK900001", "USER1", "shared description"),
        ("ABCK900002", "USER2", "shared description"),
        ("ABCK900003", "USER1", "shared description"),
    ]


# --- DesktopBackend.get_screen_text -------------------------------------------------------------------------------


class _Window:
    text = "Requests"

    def __init__(self, labels: list[str]) -> None:
        self._labels = labels

    def dump_tree(self) -> list[Any]:
        return [
            SimpleNamespace(id=f"/wnd[0]/usr/lbl[0,{i}]", type_as_number=30, text=t, children=[])
            for i, t in enumerate(self._labels)
        ]


class _Session:
    def __init__(self, labels: list[str]) -> None:
        self._window = _Window(labels)

    def find_by_id(self, element_id: str, **_: Any) -> Any:
        return self._window if element_id == "wnd[0]" else None


async def _screen_text(labels: list[str], **kwargs: Any) -> Any:
    backend = DesktopBackend(com_thread=MagicMock())

    async def _run(function: Any, **_: Any) -> Any:
        return function()

    backend.com.run = _run  # type: ignore[method-assign]
    with patch.object(DesktopBackend, "require_session", return_value=_Session(labels)):
        return await backend.get_screen_text(**kwargs)


@pytest.mark.anyio
async def test_screen_text_labels_are_de_duplicated_by_default_and_complete_on_request() -> None:
    labels = ["a", "b", "a", "a", "c"]
    assert (await _screen_text(labels)).labels == ["a", "b", "c"]
    assert (await _screen_text(labels, keep_duplicate_labels=True)).labels == labels


def test_the_built_in_user_sap_star_is_an_owner() -> None:
    labels = ["ABCK900001", "SAP*", "a description", "ABCK900002", "another"]
    assert _owners_and_descriptions(labels) == [
        ("ABCK900001", "SAP*", "a description"),
        ("ABCK900002", "SAP*", "another"),
    ]
