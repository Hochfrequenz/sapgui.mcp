"""GuiTree — tree control wrapper."""

from __future__ import annotations

from sapsucker.components.shell import GuiShell

__all__ = ["GuiTree"]


class GuiTree(GuiShell):
    """Wraps the COM GuiTree shell (SubType 'Tree').

    Supports simple trees, list trees, and column trees.
    """

    @property
    def tree_type(self) -> int:
        """Return the tree type (calls GetTreeType)."""
        return int(self._com.GetTreeType())

    @property
    def selected_node(self) -> str:
        """Key of the currently selected node."""
        return str(self._com.SelectedNode)

    @selected_node.setter
    def selected_node(self, value: str) -> None:
        self._com.SelectedNode = value

    @property
    def top_node(self) -> str:
        """Key of the topmost visible node."""
        return str(self._com.TopNode)

    @top_node.setter
    def top_node(self, value: str) -> None:
        self._com.TopNode = value

    def get_node_text_by_key(self, key: str) -> str:
        """Return the text of a tree node identified by its key."""
        return str(self._com.GetNodeTextByKey(key))

    def get_node_text_by_path(self, path: str) -> str:
        """Return the text of a tree node identified by its path."""
        return str(self._com.GetNodeTextByPath(path))

    def get_item_text(self, key: str, column: str) -> str:
        """Return the text of an item in a column tree."""
        return str(self._com.GetItemText(key, column))

    def get_node_children_count(self, key: str) -> int:
        """Return the number of children for a given node."""
        return int(self._com.GetNodeChildrenCount(key))

    def get_all_node_keys(self) -> list[str]:
        """Return all node keys in the tree."""
        col = self._com.GetAllNodeKeys()
        return [str(col(i)) for i in range(col.Count)]

    def get_column_names(self) -> list[str]:
        """Return the column names as a list of strings."""
        col = self._com.GetColumnNames()
        return [str(col(i)) for i in range(col.Count)]

    def get_column_headers(self) -> list[str]:
        """Return the column headers as a list of strings."""
        col = self._com.GetColumnHeaders()
        return [str(col(i)) for i in range(col.Count)]

    def select_node(self, key: str) -> None:
        """Select a tree node by key."""
        self._com.SelectNode(key)

    def expand_node(self, key: str) -> None:
        """Expand a tree node."""
        self._com.ExpandNode(key)

    def collapse_node(self, key: str) -> None:
        """Collapse a tree node."""
        self._com.CollapseNode(key)

    def double_click_node(self, key: str) -> None:
        """Double-click a tree node."""
        self._com.DoubleClickNode(key)

    def click_node(self, key: str) -> None:
        """Single-click a tree node."""
        self._com.ClickNode(key)

    def press_button(self, key: str, column: str) -> None:
        """Press a button in a tree node."""
        self._com.PressButton(key, column)

    def click_link(self, key: str, column: str) -> None:
        """Click a link in a tree node."""
        self._com.ClickLink(key, column)

    def get_node_key_by_path(self, path: str) -> str:
        """Return the node key for a given path."""
        return str(self._com.GetNodeKeyByPath(path))

    # --- Checkbox methods ---

    def change_checkbox(self, node_key: str, item_name: str, checked: bool) -> None:
        """Set the checkbox state of a tree item."""
        self._com.ChangeCheckbox(node_key, item_name, checked)

    def get_checkbox_state(self, node_key: str, item_name: str) -> bool:
        """Return the checkbox state of a tree item."""
        return bool(self._com.GetCheckBoxState(node_key, item_name))

    # --- Node info methods ---

    def get_item_type(self, node_key: str, item_name: str) -> int:
        """Return the type of a tree item.

        Values: 0=Hierarchy, 1=Image, 2=Text, 3=Bool, 4=Button, 5=Link.
        """
        return int(self._com.GetItemType(node_key, item_name))

    def get_item_tooltip(self, node_key: str, item_name: str) -> str:
        """Return the tooltip text of a tree item."""
        return str(self._com.GetItemToolTip(node_key, item_name))

    def get_node_style(self, node_key: str) -> int:
        """Return the style of a tree node."""
        return int(self._com.GetNodeStyle(node_key))

    def is_folder(self, node_key: str) -> bool:
        """Return whether a tree node is a folder (expandable)."""
        return bool(self._com.IsFolder(node_key))
