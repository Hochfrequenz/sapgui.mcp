"""Declarative fakes of SAP GUI tree controls for the offline tree tool tests.

``FakeTree`` records every mutating call in ``calls``. Expand, collapse and select also change the
fake's state, so the action tools can read it back; reading tests assert that ``calls`` stays empty.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


class FakeCollection:
    """COM-style collection: ``Count`` and ``Item(i)``."""

    def __init__(self, values: list[Any]) -> None:
        self._values = values
        self.Count = len(values)

    def Item(self, i: int) -> Any:  # noqa: N802
        return self._values[i]


@dataclass
class N:
    """Declarative node spec."""

    key: str
    text: str
    parent: str = ""
    items: dict[str, str] = field(default_factory=dict)
    expandable: bool = False
    expanded: bool = False
    #: State polls after ``ExpandNode`` before the node reports expanded (lazy load); -1 = never.
    expand_after: int = 0


class FakeTree:
    """Declarative GuiTree stand-in. Mutating methods are recorded in ``calls``."""

    Type = "GuiShell"
    SubType = "Tree"
    ContainerType = False

    def __init__(
        self,
        tree_id: str,
        nodes: list[N],
        tree_type: int = 0,
        columns: dict[str, str] | None = None,
        broken_keys: tuple[str, ...] = (),
        broken_methods: tuple[str, ...] = (),
    ) -> None:
        self.Id = tree_id
        self._nodes = {n.key: n for n in nodes}
        self._order = [n.key for n in nodes]
        self._tree_type = tree_type
        self._columns = columns or {}
        self._broken = set(broken_keys)
        self._broken_methods = set(broken_methods)
        self.counts: Counter[str] = Counter()
        self.calls: list[str] = []
        self.SelectedNode = ""
        self._pending: dict[str, int] = {}

    def _record(self, name: str, *args: Any) -> None:
        self.calls.append(f"{name}{args}")
        if name in self._broken_methods or args[0] not in self._nodes:
            raise RuntimeError(f"{name} failed")

    def ExpandNode(self, key: str) -> None:  # noqa: N802
        self._record("ExpandNode", key)
        self._pending[key] = self._nodes[key].expand_after

    def CollapseNode(self, key: str) -> None:  # noqa: N802
        self._record("CollapseNode", key)
        self._nodes[key].expanded = False

    def SelectNode(self, key: str) -> None:  # noqa: N802
        self._record("SelectNode", key)
        self.SelectedNode = key

    def DoubleClickNode(self, key: str) -> None:  # noqa: N802
        self._record("DoubleClickNode", key)

    def DoubleClickItem(self, key: str, item: str) -> None:  # noqa: N802
        self._record("DoubleClickItem", key, item)
        self._require_column(item)

    def ClickLink(self, key: str, item: str) -> None:  # noqa: N802
        self._record("ClickLink", key, item)
        self._require_column(item)

    def _require_column(self, item: str) -> None:
        if item not in self._columns:
            raise RuntimeError("The method got an invalid argument")

    def _node(self, key: str) -> N:
        if key in self._broken:
            raise RuntimeError("COM error for node")
        return self._nodes[key]

    def _count(self, method: str) -> None:
        self.counts[method] += 1
        if method in self._broken_methods:
            raise RuntimeError(f"{method} not supported")

    def GetTreeType(self) -> int:  # noqa: N802
        return self._tree_type

    def GetAllNodeKeys(self) -> FakeCollection:  # noqa: N802
        return FakeCollection(list(self._order))

    # Like real SAP GUI, the text getters return "" for an unknown key instead of failing.
    def GetNodeTextByKey(self, key: str) -> str:  # noqa: N802
        return self._node(key).text if key in self._nodes else ""

    def GetItemText(self, key: str, column: str) -> str:  # noqa: N802
        return self._node(key).items.get(column, "") if key in self._nodes else ""

    def GetParent(self, key: str) -> str:  # noqa: N802
        self._count("GetParent")
        return self._nodes[key].parent

    def GetHierarchyLevel(self, key: str) -> int:  # noqa: N802
        self._count("GetHierarchyLevel")
        level, current = 0, self._nodes[key].parent
        while current:
            level += 1
            current = self._nodes[current].parent
        return level

    def IsFolderExpandable(self, key: str) -> bool:  # noqa: N802
        self._count("IsFolderExpandable")
        return self._nodes[key].expandable

    def IsFolderExpanded(self, key: str) -> bool:  # noqa: N802
        self._count("IsFolderExpanded")
        pending = self._pending.get(key)
        if pending == 0:
            del self._pending[key]
            self._nodes[key].expanded = True
        elif pending is not None and pending > 0:
            self._pending[key] = pending - 1
        return self._nodes[key].expanded

    def GetNodeChildrenCount(self, key: str) -> int:  # noqa: N802
        self._count("GetNodeChildrenCount")
        return sum(1 for n in self._nodes.values() if n.parent == key)

    def GetColumnNames(self) -> FakeCollection:  # noqa: N802
        return FakeCollection(list(self._columns))

    def GetColumnTitleFromName(self, name: str) -> str:  # noqa: N802
        return self._columns[name]


class FakeContainer:
    """Container element (window, docking container) with children."""

    Type = "GuiContainerShell"
    ContainerType = True

    def __init__(self, ident: str, children: list[Any]) -> None:
        self.Id = ident
        self.Children = FakeCollection(children)


class FakeSession:
    """Raw-COM-style session: ``FindById`` over an id registry; missing ids raise."""

    def __init__(self, windows: dict[str, list[Any]]) -> None:
        self._registry: dict[str, Any] = {}
        for window_id, children in windows.items():
            self._registry[window_id] = FakeContainer(window_id, children)
            self._register(children)

    def _register(self, elements: list[Any]) -> None:
        for el in elements:
            self._registry[el.Id] = el
            if isinstance(el, FakeContainer):
                self._register(list(el.Children._values))

    def FindById(self, ident: str) -> Any:  # noqa: N802
        if ident not in self._registry:
            raise RuntimeError(f"The control could not be found by id {ident}")
        return self._registry[ident]


def simple_nodes() -> list[N]:
    return [
        N("          1", "Root", expandable=True, expanded=True),
        N("          2", "Child Alpha", parent="          1"),
        N("          3", "Child Beta", parent="          1", expandable=True),
        N("          4", "Grandchild alpha-two", parent="          3"),
        N("          5", "Sibling Root", expandable=True),
    ]


def dock(tree: FakeTree) -> FakeSession:
    return FakeSession({"wnd[0]": [FakeContainer("wnd[0]/shellcont", [tree])]})
