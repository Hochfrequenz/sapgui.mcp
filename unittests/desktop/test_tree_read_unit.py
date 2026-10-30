"""Unit tests for ``sap_tree_read`` (``_read_tree`` and the tool wrapper) — no live SAP required.

Uses a declarative ``FakeTree`` / ``FakeSession`` instead of MagicMock chains. The fake records
every mutating call so tests can assert that reading never expands, collapses or selects.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.backend.desktop import DesktopBackend, _tree_helpers
from sapguimcp.backend.desktop.models.com_results import TreeColumn, TreeNode, TreeReadResult
from sapguimcp.tools.tree_tools import _read_tree, register_tree_tools

_MUTATING = ("ExpandNode", "CollapseNode", "SelectNode", "DoubleClickNode", "ClickLink", "DoubleClickItem")


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


class FakeTree:
    """Declarative GuiTree stand-in. Mutating methods record calls instead of acting."""

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
        for name in _MUTATING:
            setattr(self, name, self._recorder(name))

    def _recorder(self, name: str):
        def _call(*args: Any) -> None:
            self.calls.append(f"{name}{args}")

        return _call

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

    def GetNodeTextByKey(self, key: str) -> str:  # noqa: N802
        return self._node(key).text

    def GetItemText(self, key: str, column: str) -> str:  # noqa: N802
        return self._node(key).items.get(column, "")

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


def _simple_nodes() -> list[N]:
    return [
        N("          1", "Root", expandable=True, expanded=True),
        N("          2", "Child Alpha", parent="          1"),
        N("          3", "Child Beta", parent="          1", expandable=True),
        N("          4", "Grandchild alpha-two", parent="          3"),
        N("          5", "Sibling Root", expandable=True),
    ]


def _dock(tree: FakeTree) -> FakeSession:
    return FakeSession({"wnd[0]": [FakeContainer("wnd[0]/shellcont", [tree])]})


def _read(session: FakeSession, tree_id: str | None = None, **kw: Any) -> dict[str, Any]:
    kw.setdefault("search", None)
    kw.setdefault("column", None)
    kw.setdefault("max_nodes", 200)
    kw.setdefault("root_key", None)
    return _read_tree(session, tree_id, **kw)


def test_simple_tree_levels_paths_and_flags():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    result = _read(_dock(tree))
    assert result["tree_id"] == "wnd[0]/shellcont/shell"
    assert result["tree_type"] == "simple"
    assert result["columns"] == []
    by_key = {n["key"]: n for n in result["nodes"]}
    grand = by_key["          4"]
    assert grand["level"] == 2
    assert grand["path"] == ["Root", "Child Beta"]
    assert by_key["          1"]["is_folder"] is True
    assert by_key["          1"]["expanded"] is True
    assert by_key["          2"]["is_folder"] is False
    assert result["total_nodes"] == 5
    assert result["returned_nodes"] == 5
    assert result["truncated"] is False
    assert not tree.calls


def test_list_tree_has_no_columns():
    tree = FakeTree("wnd[0]/usr/tree", _simple_nodes(), tree_type=1)
    result = _read(FakeSession({"wnd[0]": [FakeContainer("wnd[0]/usr", [tree])]}))
    assert result["tree_type"] == "list"
    assert result["columns"] == []
    assert result["nodes"][0]["items"] == {}


def test_column_tree_reads_items_per_column():
    nodes = [
        N("A", "Cluster", expandable=True, expanded=True, items={"C1": "Cluster", "C2": "Display"}),
        N("B", "View", parent="A", items={"C1": "View", "C2": "Maintain"}),
    ]
    tree = FakeTree("wnd[0]/shellcont/shell", nodes, tree_type=2, columns={"C1": "Name", "C2": "Action"})
    result = _read(_dock(tree))
    assert result["tree_type"] == "column"
    assert result["columns"] == [{"name": "C1", "title": "Name"}, {"name": "C2", "title": "Action"}]
    assert result["nodes"][1]["items"] == {"C1": "View", "C2": "Maintain"}


def test_empty_node_label_falls_back_to_text_item():
    """The SPRO IMG column tree has an empty GetNodeTextByKey; the label lives in the TEXT item."""
    nodes = [
        N("R", "", expandable=True, expanded=True, items={"1": "", "TEXT": "Enterprise Structure"}),
        N("C", "", parent="R", items={"1": "", "TEXT": "Definition"}),
    ]
    tree = FakeTree("wnd[0]/usr/tree", nodes, tree_type=2, columns={"1": "Structure", "TEXT": ""})
    result = _read(FakeSession({"wnd[0]": [tree]}))
    assert [n["text"] for n in result["nodes"]] == ["Enterprise Structure", "Definition"]
    assert result["nodes"][1]["path"] == ["Enterprise Structure"]
    assert [n["key"] for n in _read(FakeSession({"wnd[0]": [tree]}), search="definition")["nodes"]] == ["C"]


def test_label_fallback_uses_only_text_item_never_other_columns():
    nodes = [N("R", "", items={"1": "Other column text", "TEXT": ""})]
    tree = FakeTree("wnd[0]/usr/tree", nodes, tree_type=2, columns={"1": "Structure", "TEXT": ""})
    node = _read(FakeSession({"wnd[0]": [tree]}))["nodes"][0]
    assert node["text"] == ""
    assert node["items"]["1"] == "Other column text"


def test_search_computes_path_level_flags_only_for_matches():
    nodes = [N(f"k{i}", f"other {i}") for i in range(20)] + [N("hit", "needle node", parent="k0")]
    tree = FakeTree("wnd[0]/shellcont/shell", nodes)
    result = _read(_dock(tree), search="needle")
    assert [n["key"] for n in result["nodes"]] == ["hit"]
    assert result["nodes"][0]["path"] == ["other 0"]
    # GetParent is only needed for the single match (hit -> k0 -> end), never for the 20 non-matching nodes.
    assert tree.counts["GetParent"] == 2
    assert tree.counts["GetHierarchyLevel"] == 1
    assert tree.counts["IsFolderExpandable"] == 1
    assert tree.counts["IsFolderExpanded"] == 1


def test_scan_limit_hit_and_ceiling(monkeypatch: pytest.MonkeyPatch):
    assert _tree_helpers.MAX_SCAN_NODES == 20000
    monkeypatch.setattr(_tree_helpers, "MAX_SCAN_NODES", 3)
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    result = _read(_dock(tree))
    assert result["scan_limit_hit"] is True
    assert result["returned_nodes"] == 3
    assert result["total_nodes"] == 5


def test_missing_get_parent_degrades_to_empty_path_and_level_from_control():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes(), broken_methods=("GetParent",))
    result = _read(_dock(tree))
    assert result["skipped_nodes"] == 0
    assert all(n["path"] == [] for n in result["nodes"])
    assert {n["key"]: n["level"] for n in result["nodes"]}["          4"] == 2


def test_missing_flag_methods_degrade():
    tree = FakeTree(
        "wnd[0]/shellcont/shell",
        _simple_nodes(),
        broken_methods=("IsFolderExpandable", "IsFolderExpanded", "GetHierarchyLevel"),
    )
    by_key = {n["key"]: n for n in _read(_dock(tree))["nodes"]}
    assert by_key["          1"]["is_folder"] is True  # from GetNodeChildrenCount
    assert by_key["          2"]["is_folder"] is False
    assert by_key["          1"]["expanded"] is None
    assert by_key["          4"]["level"] == 2  # len(path)


def test_explicit_tree_id_that_is_not_a_tree_gives_clear_error():
    button = FakeContainer("wnd[0]/usr/btn", [])
    button.Type = "GuiButton"
    with pytest.raises(ValueError, match="not a tree control"):
        _read(FakeSession({"wnd[0]": [button]}), "wnd[0]/usr/btn")


def test_popup_without_tree_falls_through_to_main_window():
    main = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    session = FakeSession({"wnd[0]": [main], "wnd[1]": [FakeContainer("wnd[1]/usr", [])]})
    assert _read(session)["tree_id"] == "wnd[0]/shellcont/shell"


def test_walk_depth_limit_is_logged(caplog: pytest.LogCaptureFixture):
    inner: Any = FakeTree("wnd[0]/deep/shell", _simple_nodes())
    for i in range(20):
        inner = FakeContainer(f"wnd[0]/c{i}", [inner])
    with caplog.at_level(logging.DEBUG, logger=_tree_helpers.logger.name):
        assert _tree_helpers.find_tree_shells(FakeSession({"wnd[0]": [inner]})) == []
    assert "depth limit" in caplog.text


def test_node_cap_truncates_and_reports_total():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    result = _read(_dock(tree), max_nodes=3)
    assert result["truncated"] is True
    assert result["returned_nodes"] == 3
    assert len(result["nodes"]) == 3
    assert result["total_nodes"] == 5


def test_exact_cap_is_not_truncated():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    result = _read(_dock(tree), max_nodes=5)
    assert result["truncated"] is False
    assert result["returned_nodes"] == 5


def test_search_is_case_insensitive_with_ancestor_path_and_never_expands():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    result = _read(_dock(tree), search="ALPHA")
    assert [n["text"] for n in result["nodes"]] == ["Child Alpha", "Grandchild alpha-two"]
    assert result["nodes"][1]["path"] == ["Root", "Child Beta"]
    assert not tree.calls


def test_search_restricted_to_column():
    nodes = [
        N("A", "Cluster", items={"C1": "Cluster", "C2": "Display"}),
        N("B", "Display view", items={"C1": "Display view", "C2": "Maintain"}),
    ]
    tree = FakeTree("wnd[0]/shellcont/shell", nodes, tree_type=2, columns={"C1": "Name", "C2": "Action"})
    assert [n["key"] for n in _read(_dock(tree), search="display")["nodes"]] == ["A", "B"]
    assert [n["key"] for n in _read(_dock(tree), search="display", column="C2")["nodes"]] == ["A"]


def test_search_column_validation():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    with pytest.raises(ValueError, match="pass search"):
        _read(_dock(tree), column="C1")
    with pytest.raises(ValueError, match="not a column"):
        _read(_dock(tree), search="x", column="C1")


def test_search_match_cap_and_scanned_nodes():
    nodes = [N(f"{i}", f"match {i}") for i in range(10)]
    tree = FakeTree("wnd[0]/shellcont/shell", nodes)
    result = _read(_dock(tree), search="match", max_nodes=4)
    assert result["returned_nodes"] == 4
    assert result["truncated"] is True
    assert result["scanned_nodes"] == 4
    assert result["total_nodes"] == 10
    assert not tree.calls


def test_root_key_restricts_to_descendants():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    result = _read(_dock(tree), root_key="          1")
    assert [n["text"] for n in result["nodes"]] == ["Child Alpha", "Child Beta", "Grandchild alpha-two"]


def test_root_key_unknown_lists_valid_keys():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    with pytest.raises(ValueError, match="valid keys"):
        _read(_dock(tree), root_key="nope")


def test_autodiscovery_finds_tree_in_docking_container():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    assert _read(_dock(tree))["tree_id"] == "wnd[0]/shellcont/shell"


def test_autodiscovery_no_tree_raises():
    with pytest.raises(ValueError, match="no tree control"):
        _read(FakeSession({"wnd[0]": [FakeContainer("wnd[0]/usr", [])]}))


def test_autodiscovery_two_trees_lists_both_ids():
    t1 = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    t2 = FakeTree("wnd[0]/usr/cntlOTHER/shellcont/shell", _simple_nodes())
    session = FakeSession({"wnd[0]": [FakeContainer("wnd[0]/shellcont", [t1]), FakeContainer("wnd[0]/usr", [t2])]})
    with pytest.raises(ValueError, match="trees found") as excinfo:
        _read(session)
    assert "wnd[0]/shellcont/shell" in str(excinfo.value)
    assert "wnd[0]/usr/cntlOTHER/shellcont/shell" in str(excinfo.value)


def test_explicit_tree_id_wins_over_discovery():
    t1 = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    t2 = FakeTree("wnd[0]/usr/shell", [N("X", "Only")])
    session = FakeSession({"wnd[0]": [t1, t2]})
    result = _read(session, "wnd[0]/usr/shell")
    assert [n["text"] for n in result["nodes"]] == ["Only"]


def test_unknown_explicit_tree_id_is_runtime_error():
    with pytest.raises(RuntimeError, match="not found"):
        _read(FakeSession({"wnd[0]": []}), "wnd[0]/usr/missing")


def test_popup_tree_preferred_over_main_window_tree():
    main = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    popup = FakeTree("wnd[1]/usr/shell", [N("P", "Popup node")])
    session = FakeSession({"wnd[0]": [main], "wnd[1]": [popup]})
    result = _read(session)
    assert result["tree_id"] == "wnd[1]/usr/shell"
    assert result["nodes"][0]["text"] == "Popup node"


def test_per_node_com_error_is_skipped_and_counted():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes(), broken_keys=("          3",))
    result = _read(_dock(tree))
    assert result["skipped_nodes"] == 1
    assert "Child Beta" not in [n["text"] for n in result["nodes"]]
    assert result["returned_nodes"] == 4


@pytest.mark.parametrize("bad", [0, 5000, -1])
def test_max_nodes_out_of_range_rejected(bad: int):
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    with pytest.raises(ValueError, match="max_nodes"):
        _read(_dock(tree), max_nodes=bad)


def test_non_ascii_text_and_padded_keys_preserved():
    nodes = [N("  K  7 ", "Währungen für Größe — 日本語", expandable=True)]
    tree = FakeTree("wnd[0]/shellcont/shell", nodes)
    node = _read(_dock(tree))["nodes"][0]
    assert node["key"] == "  K  7 "
    assert node["text"] == "Währungen für Größe — 日本語"


def test_model_round_trip():
    raw = _read(_dock(FakeTree("wnd[0]/shellcont/shell", _simple_nodes())), max_nodes=2)
    model = TreeReadResult(
        tree_id=raw["tree_id"],
        tree_type=raw["tree_type"],
        columns=[TreeColumn(**c) for c in raw["columns"]],
        nodes=[TreeNode(**n) for n in raw["nodes"]],
        total_nodes=raw["total_nodes"],
        returned_nodes=raw["returned_nodes"],
        scanned_nodes=raw["scanned_nodes"],
        skipped_nodes=raw["skipped_nodes"],
        truncated=raw["truncated"],
        scan_limit_hit=raw["scan_limit_hit"],
    )
    assert TreeReadResult.model_validate_json(model.model_dump_json()) == model
    assert model.success is True


# ---------------------------------------------------------------------------
# Tool level
# ---------------------------------------------------------------------------

_PATCH_GET_BACKEND = "sapguimcp.tools.tree_tools.get_backend"


def _tree_mcp() -> FastMCP:
    """A private server with only the tree tools (the global one registers per configured backend)."""
    local = FastMCP("tree-test")
    register_tree_tools(local)
    return local


class _InlineCom:
    async def run(self, fn, **kwargs):
        assert kwargs == {"retry_server_fault": True}
        return fn()


@pytest.mark.anyio
async def test_tool_returns_failure_on_non_desktop_backend():
    class _Web:
        backend_type = "webgui"

    with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=_Web())):
        async with Client(_tree_mcp()) as client:
            raw = await client.call_tool("sap_tree_read", {})
    data = json.loads(raw.content[0].text)
    assert data["success"] is False
    assert "desktop backend" in data["error"]


@pytest.mark.anyio
async def test_tool_reads_tree_via_desktop_backend():
    tree = FakeTree("wnd[0]/shellcont/shell", _simple_nodes())
    session = _dock(tree)
    backend = DesktopBackend(com_thread=_InlineCom())
    backend.require_session = lambda: session  # type: ignore[method-assign]
    with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
        async with Client(_tree_mcp()) as client:
            raw = await client.call_tool("sap_tree_read", {"search": "beta"})
    data = json.loads(raw.content[0].text)
    assert data["success"] is True
    assert [n["text"] for n in data["nodes"]] == ["Child Beta"]
    assert not tree.calls


@pytest.mark.anyio
async def test_tool_maps_value_error_to_failure():
    session = FakeSession({"wnd[0]": []})
    backend = DesktopBackend(com_thread=_InlineCom())
    backend.require_session = lambda: session  # type: ignore[method-assign]
    with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
        async with Client(_tree_mcp()) as client:
            raw = await client.call_tool("sap_tree_read", {})
    data = json.loads(raw.content[0].text)
    assert data["success"] is False
    assert "no tree control" in data["error"]


@pytest.mark.anyio
async def test_registration_exposes_tree_tools_with_read_only_annotation():
    async with Client(_tree_mcp()) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert "sap_tree_context_menu" in tools
    assert "sap_tree_read" in tools
    ann = tools["sap_tree_read"].annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
