"""Readiness predicates for ``DesktopBackend.wait_for_condition`` shared by several tools (#928).

Each factory takes a snapshot of state read right before the triggering action and returns a predicate
``f(session) -> bool`` that runs on the COM thread. Predicates must be cheap and may raise (an exception counts as
"not yet").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

_TYPE_TAB = 91
_TYPE_TABLE_CONTROL = 80
_TYPES_TEXT_FIELD = (31, 32)  # GuiTextField, GuiCTextField


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


def popup_closed_and_screen_changed(before_title: str, before_status: str) -> Callable[[Any], bool]:
    """Build a predicate: True once no popup is open and the window title changed or a new status text appeared.

    For the step after a keypress that dismisses a popup: ``screen_changed`` is already true while that very popup
    is still open, so it cannot tell that the dialog has gone. ``before_title`` / ``before_status`` are read right
    before the action that led to the popup.
    """
    before_title = before_title.strip()
    before_status = before_status.strip()

    def _predicate(session: Any) -> bool:
        if session.find_by_id("wnd[1]", raise_error=False) is not None:
            return False
        if str(session.find_by_id("wnd[0]").text).strip() != before_title:
            return True
        sbar = session.find_by_id("wnd[0]/sbar", raise_error=False)
        if sbar is None:
            return False
        text = str(sbar.text).strip()
        return bool(text) and text != before_status

    return _predicate


def usr_child_count_changed(before_count: int) -> Callable[[Any], bool]:
    """Build a predicate: True once the number of direct children of ``wnd[0]/usr`` differs from ``before_count``.

    For tree-like list screens whose nodes are rendered as labels (e.g. SE09 request nodes): expanding a node adds
    labels, collapsing it removes them. ``before_count`` is read right before the triggering action.
    """

    def _predicate(session: Any) -> bool:
        # One dump_tree() call instead of one COM call per child.
        return len(session.find_by_id("wnd[0]/usr").dump_tree()) != before_count

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


def editor_loaded(session: Any) -> bool:
    """Predicate: True once the active window holds an ABAP editor control (``GuiAbapEditor`` or ``GuiTextedit``)."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    return DesktopBackend._find_editor_shell_raw(session) is not None  # pylint: disable=protected-access


def editor_loaded_or_popup_open(session: Any) -> bool:
    """Predicate: True once the active window holds an ABAP editor control or a popup is open.

    A popup that appears while the editor is still being built hides the editor for good, so waiting for the editor
    alone would run into its full timeout.
    """
    return session.find_by_id("wnd[1]", raise_error=False) is not None or editor_loaded(session)


def editor_loaded_after(title_with_editor: str | None) -> Callable[[Any], bool]:
    """Build a predicate: True once an editor exists whose source can be read, for the step after opening a source.

    ``title_with_editor`` is the title of ``wnd[0]`` read right before the click if an editor was already open then
    (None if there was none). An editor that predates the click does not tell that the new source has loaded, so in
    that case the window title has to change as well.
    """

    def _predicate(session: Any) -> bool:
        if not editor_loaded(session):
            return False
        return title_with_editor is None or str(session.find_by_id("wnd[0]").text).strip() != title_with_editor

    return _predicate


def window_title_changed(before_title: str) -> Callable[[Any], bool]:
    """Build a predicate: True once the title of ``wnd[0]`` differs from ``before_title`` (read before the action)."""
    before_title = before_title.strip()

    def _predicate(session: Any) -> bool:
        return str(session.find_by_id("wnd[0]").text).strip() != before_title

    return _predicate


def named_text_field_present(names: Collection[str]) -> Callable[[Any], bool]:
    """Build a predicate: True once a text field (GuiTextField / GuiCTextField) whose name is one of ``names`` exists.

    For the step after selecting a tab whose subscreen SAP instantiates lazily and that has no table control to wait
    for: the tab's own header field is in the tree only once the tab is really active (idle does not prove that).
    """
    from sapguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    wanted = frozenset(names)

    def _predicate(session: Any) -> bool:
        flat = _flatten(session.find_by_id("wnd[0]").dump_tree())
        return any(getattr(e, "name", "") in wanted and e.type_as_number in _TYPES_TEXT_FIELD for e in flat)

    return _predicate
