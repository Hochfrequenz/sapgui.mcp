"""Unit tests for DesktopBackend.check_popup reporting the window title (issue #1027)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend


def _elem(type_as_number: int, text: str, elem_id: str = "x") -> SimpleNamespace:
    return SimpleNamespace(type_as_number=type_as_number, text=text, tooltip="", id=elem_id, children=[])


class _FakePopup:
    def __init__(self, title: str, tree: list[Any]) -> None:
        self.text = title
        self._tree = tree

    def dump_tree(self) -> list[Any]:
        return self._tree


class _FakeSession:
    def __init__(self, popup: _FakePopup | None) -> None:
        self._popup = popup

    def find_by_id(self, element_id: str, raise_error: bool = True) -> Any:  # noqa: ARG002
        assert element_id == "wnd[1]"
        return self._popup


def _make_backend(session: _FakeSession) -> DesktopBackend:
    backend = DesktopBackend.__new__(DesktopBackend)

    async def run(fn):  # type: ignore[no-untyped-def]
        return fn()

    backend.com = MagicMock()
    backend.com.run = run
    backend.require_session = lambda: session  # type: ignore[assignment,method-assign,return-value]
    return backend


@pytest.mark.anyio
async def test_check_popup_returns_title_separately_from_message() -> None:
    tree = [_elem(30, "Some explanatory label"), _elem(40, "Continue", "wnd[1]/tbar[0]/btn[0]")]
    backend = _make_backend(_FakeSession(_FakePopup("Inaktive Objekte", tree)))

    popup = await backend.check_popup()

    assert popup is not None
    assert popup.title == "Inaktive Objekte"
    assert popup.message == "Some explanatory label"


@pytest.mark.anyio
async def test_check_popup_message_falls_back_to_title_without_labels() -> None:
    backend = _make_backend(_FakeSession(_FakePopup("Inactive Objects", [])))

    popup = await backend.check_popup()

    assert popup is not None
    assert popup.title == "Inactive Objects"
    assert popup.message == "Inactive Objects"


@pytest.mark.anyio
async def test_check_popup_none_without_popup() -> None:
    backend = _make_backend(_FakeSession(None))

    assert await backend.check_popup() is None
