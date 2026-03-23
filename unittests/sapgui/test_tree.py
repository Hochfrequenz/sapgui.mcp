"""Tests for GuiTree missing methods — issue #474."""

from unittest.mock import MagicMock

from sapsucker.components.tree import GuiTree


def _make_tree():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "Tree"
    return GuiTree(com)


class TestGuiTreeCheckbox:
    def test_change_checkbox(self):
        tree = _make_tree()
        tree.change_checkbox("KEY1", "COL1", True)
        tree._com.ChangeCheckbox.assert_called_once_with("KEY1", "COL1", True)

    def test_get_checkbox_state(self):
        tree = _make_tree()
        tree._com.GetCheckBoxState.return_value = True
        assert tree.get_checkbox_state("KEY1", "COL1") is True


class TestGuiTreeNodeInfo:
    def test_get_item_type(self):
        tree = _make_tree()
        tree._com.GetItemType.return_value = 1
        assert tree.get_item_type("KEY1", "COL1") == 1

    def test_get_item_tooltip(self):
        tree = _make_tree()
        tree._com.GetItemToolTip.return_value = "tip"
        assert tree.get_item_tooltip("KEY1", "COL1") == "tip"

    def test_get_node_style(self):
        tree = _make_tree()
        tree._com.GetNodeStyle.return_value = 2
        assert tree.get_node_style("KEY1") == 2

    def test_is_folder(self):
        tree = _make_tree()
        tree._com.IsFolder.return_value = True
        assert tree.is_folder("KEY1") is True
