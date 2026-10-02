"""Tests for the SE11 desktop readiness predicate (#928)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from sapguimcp.tools.se11_tools import _se11_display_screen_reached


def _session(elements: dict[str, object]) -> MagicMock:
    session = MagicMock()
    session.find_by_id = lambda element_id, **_kwargs: elements.get(element_id)
    return session


def _wnd(title: str) -> SimpleNamespace:
    return SimpleNamespace(text=title)


def test_initial_screen_with_empty_status_bar_is_not_ready() -> None:
    session = _session({"wnd[0]": _wnd("ABAP Dictionary: Initial Screen"), "wnd[0]/sbar": SimpleNamespace(text="")})
    assert not _se11_display_screen_reached("")(session)


def test_initial_screen_with_status_bar_text_is_ready() -> None:
    session = _session(
        {"wnd[0]": _wnd("ABAP Dictionary: Initial Screen"), "wnd[0]/sbar": SimpleNamespace(text="XYZ does not exist")}
    )
    assert _se11_display_screen_reached("")(session)


def test_display_screen_is_ready() -> None:
    assert _se11_display_screen_reached("")(_session({"wnd[0]": _wnd("Dictionary: Display Table")}))


def test_popup_is_ready() -> None:
    session = _session({"wnd[0]": _wnd("ABAP Dictionary: Initial Screen"), "wnd[1]": object()})
    assert _se11_display_screen_reached("")(session)


def test_status_text_from_before_f7_is_ignored() -> None:
    session = _session(
        {"wnd[0]": _wnd("ABAP Dictionary: Initial Screen"), "wnd[0]/sbar": SimpleNamespace(text=" Old message ")}
    )
    assert not _se11_display_screen_reached("Old message")(session)
    assert _se11_display_screen_reached("Different")(session)


def test_screen_transition_and_popup_accepted_despite_same_status() -> None:
    sbar = SimpleNamespace(text="Old message")
    assert _se11_display_screen_reached("Old message")(
        _session({"wnd[0]": _wnd("Dictionary: Display Table"), "wnd[0]/sbar": sbar})
    )
    assert _se11_display_screen_reached("Old message")(
        _session({"wnd[0]": _wnd("ABAP Dictionary: Initial Screen"), "wnd[1]": object(), "wnd[0]/sbar": sbar})
    )
