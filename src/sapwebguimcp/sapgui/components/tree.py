"""GuiTree — tree control wrapper."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.shell import GuiShell


class GuiTree(GuiShell):
    """Wraps the COM GuiTree shell (SubType 'Tree').

    Supports simple trees, list trees, and column trees.
    """

    @property
    def tree_type(self) -> int:
        """Return the tree type (calls GetTreeType)."""
        return self._com.GetTreeType()

    @property
    def selected_node(self) -> str:
        return self._com.SelectedNode

    @selected_node.setter
    def selected_node(self, value: str) -> None:
        self._com.SelectedNode = value

    @property
    def top_node(self) -> str:
        return self._com.TopNode

    @top_node.setter
    def top_node(self, value: str) -> None:
        self._com.TopNode = value

    def get_node_text_by_key(self, key: str) -> str:
        """Return the text of a tree node identified by its key."""
        return self._com.GetNodeTextByKey(key)

    def get_node_text_by_path(self, path: str) -> str:
        """Return the text of a tree node identified by its path."""
        return self._com.GetNodeTextByPath(path)

    def get_item_text(self, key: str, column: str) -> str:
        """Return the text of an item in a column tree."""
        return self._com.GetItemText(key, column)

    def get_node_children_count(self, key: str) -> int:
        """Return the number of children for a given node."""
        return self._com.GetNodeChildrenCount(key)

    def get_all_node_keys(self):
        """Return all node keys in the tree."""
        return self._com.GetAllNodeKeys()

    def get_column_names(self):
        """Return the column names collection."""
        return self._com.GetColumnNames()

    def get_column_headers(self):
        """Return the column headers collection."""
        return self._com.GetColumnHeaders()

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
        return self._com.GetNodeKeyByPath(path)
