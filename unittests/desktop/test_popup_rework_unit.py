"""Unit tests for active window detection and element finder wnd_id support."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_session(*, has_wnd1: bool = False, has_wnd2: bool = False, has_wnd3: bool = False) -> MagicMock:
    """Create a mock session with configurable open windows."""
    session = MagicMock()
    windows = {"wnd[0]": MagicMock()}
    if has_wnd1:
        windows["wnd[1]"] = MagicMock()
    if has_wnd2:
        windows["wnd[2]"] = MagicMock()
    if has_wnd3:
        windows["wnd[3]"] = MagicMock()

    def find_by_id(element_id: str, raise_error: bool = True):
        result = windows.get(element_id)
        if result is None and raise_error:
            raise Exception(f"Element not found: {element_id}")
        return result

    session.find_by_id = find_by_id
    return session


def test_active_window_no_popup():
    from sapwebguimcp.backend.desktop import _active_window_id

    session = _make_session()
    assert _active_window_id(session) == "wnd[0]"


def test_active_window_wnd1():
    from sapwebguimcp.backend.desktop import _active_window_id

    session = _make_session(has_wnd1=True)
    assert _active_window_id(session) == "wnd[1]"


def test_active_window_wnd2():
    from sapwebguimcp.backend.desktop import _active_window_id

    session = _make_session(has_wnd1=True, has_wnd2=True)
    assert _active_window_id(session) == "wnd[2]"


def test_active_window_wnd3():
    from sapwebguimcp.backend.desktop import _active_window_id

    session = _make_session(has_wnd1=True, has_wnd2=True, has_wnd3=True)
    assert _active_window_id(session) == "wnd[3]"
