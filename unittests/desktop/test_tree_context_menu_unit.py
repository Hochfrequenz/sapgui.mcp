"""Unit tests for ``sap_tree_context_menu`` core logic.

Tests the pure COM-interaction function ``_invoke_tree_context_menu``
with a mocked shell — no live SAP required. Covers:

- Enumerate items only (no selection arg)
- Select by exact text
- Select by function code (Name)
- Select by position
- Mutually-exclusive select args
- Invalid shell / node key surfacing
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sapguimcp.tools.tree_tools import _invoke_tree_context_menu


def _mock_shell(items: list[tuple[str, str]]) -> tuple[MagicMock, MagicMock]:
    """Build a mock shell whose CurrentContextMenu.Children yields ``items``.

    Returns ``(session, shell)``. ``session.com.FindById(...)`` returns shell.
    """
    mocked_items = []
    for text, fcode in items:
        mi = MagicMock()
        mi.Text = text
        mi.Name = fcode
        mocked_items.append(mi)

    ccm = MagicMock()
    ccm.Children.Count = len(items)
    ccm.Children.Item.side_effect = lambda i: mocked_items[i]

    shell = MagicMock()
    shell.CurrentContextMenu = ccm

    raw_session = MagicMock()
    raw_session.FindById.return_value = shell

    session = MagicMock()
    session.com = raw_session
    return session, shell


DCS_MENU = [
    ("Task: Anlegen", "T_1310"),
    ("Task: mehrere Tasks anlegen", "T_1312"),
    ("Taskgruppe: Anlegen mit Vorlage", "T_1232"),
]


def test_enumerates_items_without_selection():
    session, shell = _mock_shell(DCS_MENU)
    result = _invoke_tree_context_menu(
        session,
        "wnd[0]/shellcont/shell",
        "TAGR__   16",
        select_text=None,
        select_fcode=None,
        select_position=None,
    )
    assert result["items"] == [
        {"position": 0, "text": "Task: Anlegen", "fcode": "T_1310"},
        {"position": 1, "text": "Task: mehrere Tasks anlegen", "fcode": "T_1312"},
        {"position": 2, "text": "Taskgruppe: Anlegen mit Vorlage", "fcode": "T_1232"},
    ]
    assert result["selected"] is None
    shell.SelectNode.assert_called_once_with("TAGR__   16")
    shell.NodeContextMenu.assert_called_once_with("TAGR__   16")
    shell.SelectContextMenuItemByText.assert_not_called()
    shell.SelectContextMenuItem.assert_not_called()
    shell.SelectContextMenuItemByPosition.assert_not_called()


def test_select_by_text_invokes_correct_method_with_exact_label():
    """Regression for #717 follow-up: reporter's 'Task anlegen' missed the colon."""
    session, shell = _mock_shell(DCS_MENU)
    result = _invoke_tree_context_menu(
        session,
        "wnd[0]/shellcont/shell",
        "TAGR__   16",
        select_text="Task: Anlegen",
        select_fcode=None,
        select_position=None,
    )
    shell.SelectContextMenuItemByText.assert_called_once_with("Task: Anlegen")
    shell.SelectContextMenuItem.assert_not_called()
    shell.SelectContextMenuItemByPosition.assert_not_called()
    assert result["selected"] == {"position": 0, "text": "Task: Anlegen", "fcode": "T_1310"}


def test_select_by_fcode_invokes_select_context_menu_item():
    session, shell = _mock_shell(DCS_MENU)
    result = _invoke_tree_context_menu(
        session,
        "wnd[0]/shellcont/shell",
        "TAGR__   16",
        select_text=None,
        select_fcode="T_1310",
        select_position=None,
    )
    shell.SelectContextMenuItem.assert_called_once_with("T_1310")
    shell.SelectContextMenuItemByText.assert_not_called()
    assert result["selected"] == {"position": 0, "text": "Task: Anlegen", "fcode": "T_1310"}


def test_select_by_position_invokes_by_position():
    session, shell = _mock_shell(DCS_MENU)
    result = _invoke_tree_context_menu(
        session,
        "wnd[0]/shellcont/shell",
        "TAGR__   16",
        select_text=None,
        select_fcode=None,
        select_position=2,
    )
    shell.SelectContextMenuItemByPosition.assert_called_once_with(2)
    assert result["selected"] == {"position": 2, "text": "Taskgruppe: Anlegen mit Vorlage", "fcode": "T_1232"}


def test_mutually_exclusive_select_args_raise():
    session, _ = _mock_shell(DCS_MENU)
    with pytest.raises(ValueError, match="mutually exclusive"):
        _invoke_tree_context_menu(
            session,
            "wnd[0]/shellcont/shell",
            "K",
            select_text="A",
            select_fcode="B",
            select_position=None,
        )


def test_select_by_unknown_text_still_reports_list_and_raises():
    """If the LLM passed bad text, we want the items list back in the error so it can retry."""
    session, shell = _mock_shell(DCS_MENU)
    shell.SelectContextMenuItemByText.side_effect = Exception("613 invalid")
    with pytest.raises(RuntimeError) as exc_info:
        _invoke_tree_context_menu(
            session,
            "wnd[0]/shellcont/shell",
            "K",
            select_text="Task anlegen",  # missing colon / wrong case
            select_fcode=None,
            select_position=None,
        )
    assert "available items" in str(exc_info.value)
    assert "Task: Anlegen" in str(exc_info.value)


def test_empty_menu_returns_empty_items():
    session, shell = _mock_shell([])
    result = _invoke_tree_context_menu(
        session,
        "wnd[0]/shellcont/shell",
        "K",
        select_text=None,
        select_fcode=None,
        select_position=None,
    )
    assert result["items"] == []
    assert result["selected"] is None


def test_select_by_text_with_duplicates_leaves_selected_unresolved():
    """When two items share the same label, we can't tell which SAP picked — surface as unknown."""
    session, shell = _mock_shell([("Dup", "F_1"), ("Dup", "F_2"), ("Other", "F_3")])
    result = _invoke_tree_context_menu(
        session,
        "wnd[0]/shellcont/shell",
        "K",
        select_text="Dup",
        select_fcode=None,
        select_position=None,
    )
    shell.SelectContextMenuItemByText.assert_called_once_with("Dup")
    # The menu fired, but we cannot pin which entry — explicit unknown.
    assert result["selected"] is None
    # The items list still carries both for the LLM to reason about.
    assert len(result["items"]) == 3


def test_null_current_context_menu_raises_helpful_error():
    """If the shell returns None for CurrentContextMenu, surface a clear message."""
    shell = MagicMock()
    shell.CurrentContextMenu = None
    raw_session = MagicMock()
    raw_session.FindById.return_value = shell
    session = MagicMock()
    session.com = raw_session

    with pytest.raises(RuntimeError, match="no context menu opened"):
        _invoke_tree_context_menu(
            session,
            "wnd[0]/shellcont/shell",
            "BADKEY",
            select_text=None,
            select_fcode=None,
            select_position=None,
        )


def test_tree_context_menu_item_is_a_plain_payload():
    """Regression: TreeContextMenuItem must NOT inherit ToolResult's envelope fields."""
    from sapguimcp.backend.desktop.models.com_results import TreeContextMenuItem

    item = TreeContextMenuItem(position=0, text="A", fcode="F_1")
    # These are ToolResult-only fields; they MUST NOT appear on a payload item.
    dumped = item.model_dump()
    assert "success" not in dumped
    assert "error" not in dumped
    assert "popup" not in dumped
    assert "active_window" not in dumped
    assert dumped == {"position": 0, "text": "A", "fcode": "F_1"}
