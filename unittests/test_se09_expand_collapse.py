"""Tests for the desktop SE09 expand/collapse path: tree-based lookup instead of per-child COM scans (#928)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.tools.desktop_wait_predicates import usr_child_count_changed
from sapguimcp.tools.se09_tools import (
    _collapse_request_node_desktop,
    _expand_request_node_desktop,
    _select_edit_menu_item_for_label,
)

_LABEL = 30  # GuiLabel
_MENU = 110  # GuiMenu


def _el(element_id: str, text: str = "", type_as_number: int = _LABEL, children: list[Any] | None = None) -> Any:
    return SimpleNamespace(id=element_id, text=text, type_as_number=type_as_number, children=children or [])


class _FakeSession:
    """Fake GuiSession serving dump_tree() for usr and mbar and recording the actions on elements by id."""

    def __init__(self, usr_tree: list[Any], menu_tree: list[Any]) -> None:
        self.dump_calls: list[str] = []
        self.actions: list[tuple[str, str]] = []
        self._trees = {"wnd[0]/usr": usr_tree, "wnd[0]/mbar": menu_tree}

    def find_by_id(self, element_id: str) -> Any:
        if element_id in self._trees:
            node = MagicMock()

            def _dump(_id: str = element_id) -> list[Any]:
                self.dump_calls.append(_id)
                return self._trees[_id]

            node.dump_tree = _dump
            return node
        node = MagicMock()
        node.set_focus = lambda: self.actions.append(("set_focus", element_id))
        node.select = lambda: self.actions.append(("select", element_id))
        return node


def _edit_menu(*item_texts: str) -> Any:
    items = [_el(f"wnd[0]/mbar/menu[1]/menu[{i}]", text, _MENU) for i, text in enumerate(item_texts)]
    return _el("wnd[0]/mbar/menu[1]", "Bearbeiten", _MENU, items)


def _menu_bar(edit_menu: Any) -> list[Any]:
    return [_el("wnd[0]/mbar/menu[0]", "Transportauftrag", _MENU), edit_menu]


def _usr(*texts: str) -> list[Any]:
    return [_el(f"wnd[0]/usr/lbl[3,{i}]", text) for i, text in enumerate(texts)]


# --- _select_edit_menu_item_for_label -----------------------------------------------------------------------------


def test_select_focuses_label_opens_edit_menu_and_selects_item_by_id() -> None:
    session = _FakeSession(_usr("ABCK900001", "ABCK900002"), _menu_bar(_edit_menu("Ausschneiden", "Expandieren")))
    performed, before = _select_edit_menu_item_for_label(session, "ABCK900002", ("Expandieren", "Expand"))
    assert performed is True
    assert before == 2
    assert session.actions == [
        ("set_focus", "wnd[0]/usr/lbl[3,1]"),
        ("select", "wnd[0]/mbar/menu[1]"),
        ("select", "wnd[0]/mbar/menu[1]/menu[1]"),
    ]


def test_select_reads_each_container_with_a_single_tree_dump() -> None:
    session = _FakeSession(_usr(*[f"ABCK9{i:05d}" for i in range(30)]), _menu_bar(_edit_menu("Expand")))
    _select_edit_menu_item_for_label(session, "ABCK900029", ("Expandieren", "Expand"))
    assert session.dump_calls == ["wnd[0]/usr", "wnd[0]/mbar"]


def test_select_matches_english_item_and_trims_label_text() -> None:
    session = _FakeSession(_usr("  ABCK900001  "), _menu_bar(_edit_menu("Cut", "Compress")))
    performed, _ = _select_edit_menu_item_for_label(session, "ABCK900001", ("Komprimieren", "Compress"))
    assert performed is True
    assert ("select", "wnd[0]/mbar/menu[1]/menu[1]") in session.actions


def test_select_unknown_label_does_nothing() -> None:
    session = _FakeSession(_usr("ABCK900001"), _menu_bar(_edit_menu("Expandieren")))
    performed, before = _select_edit_menu_item_for_label(session, "ABCK999999", ("Expandieren", "Expand"))
    assert (performed, before) == (False, 1)
    assert session.actions == []


def test_select_ignores_labels_nested_in_containers() -> None:
    """The old raw-COM scan only looked at direct usr children; a nested label must not match."""
    nested = _el("wnd[0]/usr/cntl", "", 62, [_el("wnd[0]/usr/cntl/lbl[1,1]", "ABCK900001")])
    session = _FakeSession([nested], _menu_bar(_edit_menu("Expandieren")))
    performed, before = _select_edit_menu_item_for_label(session, "ABCK900001", ("Expandieren", "Expand"))
    assert (performed, before) == (False, 1)
    assert session.actions == []


def test_select_ignores_non_label_elements_with_the_same_text() -> None:
    usr = [_el("wnd[0]/usr/txt[1,1]", "ABCK900001", type_as_number=31)]
    session = _FakeSession(usr, _menu_bar(_edit_menu("Expandieren")))
    performed, _ = _select_edit_menu_item_for_label(session, "ABCK900001", ("Expandieren", "Expand"))
    assert performed is False
    assert session.actions == []


def test_select_missing_menu_item_reports_not_performed_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    session = _FakeSession(_usr("ABCK900001"), _menu_bar(_edit_menu("Ausschneiden", "Kopieren")))
    with caplog.at_level(logging.WARNING):
        performed, before = _select_edit_menu_item_for_label(session, "ABCK900001", ("Expandieren", "Expand"))
    assert (performed, before) == (False, 1)
    assert "menu item" in caplog.text
    # The Edit menu is not opened when the item is missing (no menu left open).
    assert not any(action == "select" for action, _ in session.actions)


# --- usr_child_count_changed ---------------------------------------------------------------------------------------


def _usr_session(count: int) -> Any:
    usr = SimpleNamespace(dump_tree=lambda: [object()] * count)
    return SimpleNamespace(find_by_id=lambda element_id: usr if element_id == "wnd[0]/usr" else None)


def test_usr_child_count_unchanged_is_not_ready() -> None:
    assert not usr_child_count_changed(5)(_usr_session(5))


@pytest.mark.parametrize("count", [3, 9])
def test_usr_child_count_change_is_ready_in_both_directions(count: int) -> None:
    assert usr_child_count_changed(5)(_usr_session(count))


# --- wiring: readiness waits instead of fixed sleeps ---------------------------------------------------------------


def _backend(job_result: bool) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(return_value=job_result)
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    return backend


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("operation", "item"),
    [(_expand_request_node_desktop, "Expandieren"), (_collapse_request_node_desktop, "Komprimieren")],
)
async def test_after_the_action_waits_for_ready_and_the_tree_change(operation: Any, item: str) -> None:
    """Run the real COM job against a fake session and check the wait is built from the pre-action child count."""
    session = _FakeSession(_usr("ABCK900001", "ABCK900002", "ABCK900003"), _menu_bar(_edit_menu(item)))
    backend = _backend(job_result=True)
    backend.require_session = MagicMock(return_value=session)
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    await operation(backend, "ABCK900002")
    backend.wait_for_ready.assert_awaited_once()
    backend.wait_for_condition.assert_awaited_once()
    assert backend.wait_for_condition.await_args.kwargs == {"timeout_ms": 2000, "poll_ms": 50}
    predicate = backend.wait_for_condition.await_args.args[0]
    assert predicate.__qualname__.startswith("usr_child_count_changed.")
    # Built from the 3 children seen before the action: unchanged is not ready, a changed count is.
    assert not predicate(_usr_session(3))
    assert predicate(_usr_session(5))


@pytest.mark.anyio
async def test_expand_without_a_matching_label_skips_the_tree_wait() -> None:
    backend = _backend(job_result=False)
    assert await _expand_request_node_desktop(backend, "ABCK900001") is False
    backend.wait_for_condition.assert_not_awaited()


@pytest.mark.anyio
async def test_collapse_without_a_matching_label_skips_the_tree_wait() -> None:
    backend = _backend(job_result=False)
    await _collapse_request_node_desktop(backend, "ABCK900001")
    backend.wait_for_condition.assert_not_awaited()
