"""Readiness predicates for ``DesktopBackend.wait_for_condition`` shared by several tools (#928).

Each factory takes a snapshot of state read right before the triggering action and returns a predicate
``f(session) -> bool`` that runs on the COM thread. Predicates must be cheap and may raise (an exception counts as
"not yet").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

_TYPE_TAB = 91
_TYPE_TABLE_CONTROL = 80


def screen_changed(before_title: str, before_status: str) -> Callable[[Any], bool]:
    """Build a predicate: True once a popup is open, the window title changed, or a new status bar text appeared.

    ``before_title`` / ``before_status`` are read right before the keypress or click. A status bar text identical
    to ``before_status`` predates the action and is ignored.
    """
    before_title = before_title.strip()
    before_status = before_status.strip()

    def _predicate(session: Any) -> bool:
        if session.find_by_id("wnd[1]", raise_error=False) is not None:
            return True
        if str(session.find_by_id("wnd[0]").text).strip() != before_title:
            return True
        sbar = session.find_by_id("wnd[0]/sbar", raise_error=False)
        if sbar is None:
            return False
        text = str(sbar.text).strip()
        return bool(text) and text != before_status

    return _predicate


def tab_table_control_loaded(tab_label: str) -> Callable[[Any], bool]:
    """Build a predicate: True once a table control exists below the tab page whose text matches ``tab_label``.

    SAP instantiates a tab page's subscreen lazily, so after selecting the tab its table control only appears in
    the tree once the tab is really active. The control's element id starts with the tab page's id.
    """
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    needle = tab_label.strip().lower()

    def _predicate(session: Any) -> bool:
        flat = _flatten(session.find_by_id("wnd[0]").dump_tree())
        tabs = [e for e in flat if e.type_as_number == _TYPE_TAB]
        tab = next((e for e in tabs if e.text.strip().lower() == needle), None) or next(
            (e for e in tabs if needle in e.text.strip().lower()), None
        )
        if tab is None:
            return False
        prefix = f"{tab.id}/"
        return any(e.type_as_number == _TYPE_TABLE_CONTROL and e.id.startswith(prefix) for e in flat)

    return _predicate
