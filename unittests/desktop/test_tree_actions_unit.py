"""Unit tests for ``sap_tree_expand``, ``sap_tree_select`` and ``sap_tree_activate`` — no live SAP required."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.backend.desktop import DesktopBackend, _tree_helpers
from sapguimcp.backend.desktop._tree_helpers import activate_node, expand_node, select_node
from sapguimcp.models.sap_results import StatusBarInfo
from sapguimcp.tools.tree_tools import register_tree_tools
from unittests.desktop.tree_fakes import FakeContainer, FakeSession, FakeTree, N, dock, simple_nodes

TREE_ID = "wnd[0]/shellcont/shell"


@pytest.fixture(autouse=True)
def _no_poll_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tree_helpers, "_EXPAND_POLL_S", 0)


def _tree(**kw: Any) -> FakeTree:
    return FakeTree(TREE_ID, simple_nodes(), **kw)


def _column_tree() -> FakeTree:
    nodes = [N("A", "Cluster", items={"C1": "Cluster", "LINK": "Open"})]
    return FakeTree(TREE_ID, nodes, tree_type=2, columns={"C1": "Name", "LINK": "Link"})


# ---------------------------------------------------------------------------
# expand / collapse
# ---------------------------------------------------------------------------


def test_expand_calls_expand_once_and_reads_state_back():
    tree = _tree()
    result = expand_node(dock(tree), None, "          3")
    assert tree.calls == ["ExpandNode('          3',)"]
    assert result == {
        "tree_id": TREE_ID,
        "node_key": "          3",
        "node_text": "Child Beta",
        "expanded": True,
        "child_count": 1,
    }


def test_collapse_calls_collapse_node():
    tree = _tree()
    result = expand_node(dock(tree), TREE_ID, "          1", expand=False)
    assert tree.calls == ["CollapseNode('          1',)"]
    assert result["expanded"] is False


def test_expand_waits_for_lazy_load_on_a_later_poll():
    nodes = simple_nodes()
    nodes[2].expand_after = 2
    tree = FakeTree(TREE_ID, nodes)
    result = expand_node(dock(tree), None, "          3")
    assert result["expanded"] is True
    assert result["child_count"] == 1
    assert tree.counts["IsFolderExpanded"] == 3


def test_expand_that_never_takes_effect_fails_clearly():
    nodes = simple_nodes()
    nodes[2].expand_after = -1
    tree = FakeTree(TREE_ID, nodes)
    with pytest.raises(RuntimeError, match="still collapsed after ExpandNode"):
        expand_node(dock(tree), None, "          3")
    assert tree.counts["IsFolderExpanded"] == _tree_helpers._EXPAND_POLLS


def test_expand_empty_folder_reports_zero_children_without_extra_polls():
    tree = _tree()
    result = expand_node(dock(tree), None, "          5")
    assert result["expanded"] is True
    assert result["child_count"] == 0
    assert tree.counts["IsFolderExpanded"] == 1


def test_expand_reads_state_from_refetched_tree():
    """After the server round trip the old reference may be stale; the state is read from a fresh FindById."""
    fresh = FakeTree(TREE_ID, simple_nodes())

    class _Stale(FakeTree):
        def ExpandNode(self, key: str) -> None:  # noqa: N802
            self._record("ExpandNode", key)
            session._registry[TREE_ID] = fresh
            fresh._nodes[key].expanded = True

        def IsFolderExpanded(self, key: str) -> bool:  # noqa: N802, ARG002
            raise AssertionError("stale reference used")

    session = dock(_Stale(TREE_ID, simple_nodes()))
    result = expand_node(session, None, "          3")
    assert result["expanded"] is True
    assert fresh.counts["IsFolderExpanded"] == 1


def test_expand_leaf_is_value_error_without_calling_the_control():
    tree = _tree()
    with pytest.raises(ValueError, match="not an expandable folder"):
        expand_node(dock(tree), None, "          2")
    assert not tree.calls


def test_expand_com_failure_names_tree_node_and_operation():
    tree = _tree(broken_methods=("ExpandNode",))
    with pytest.raises(RuntimeError, match=r"ExpandNode on node '          3' failed") as excinfo:
        expand_node(dock(tree), None, "          3")
    assert TREE_ID in str(excinfo.value)


# ---------------------------------------------------------------------------
# select / activate
# ---------------------------------------------------------------------------


def test_select_sets_selection_and_keeps_padding():
    tree = _tree()
    result = select_node(dock(tree), None, "          4")
    assert tree.calls == ["SelectNode('          4',)"]
    assert tree.SelectedNode == "          4"
    assert result["node_text"] == "Grandchild alpha-two"


def test_select_that_leaves_another_node_selected_fails():
    class _Stuck(FakeTree):
        def SelectNode(self, key: str) -> None:  # noqa: N802
            self._record("SelectNode", key)
            self.SelectedNode = "          1"

    with pytest.raises(RuntimeError, match="selected node is"):
        select_node(dock(_Stuck(TREE_ID, simple_nodes())), None, "          4")


@pytest.mark.parametrize(
    ("mode", "item_name", "expected_call"),
    [
        ("double_click", None, "DoubleClickNode('A',)"),
        ("double_click", "C1", "DoubleClickItem('A', 'C1')"),
        ("click_link", "LINK", "ClickLink('A', 'LINK')"),
    ],
)
def test_activate_dispatch(mode: str, item_name: str | None, expected_call: str):
    tree = _column_tree()
    result = activate_node(dock(tree), None, "A", mode=mode, item_name=item_name)
    assert tree.calls == [expected_call]
    assert result["node_text"] == "Cluster"


def test_click_link_requires_item_name():
    tree = _column_tree()
    with pytest.raises(ValueError, match="needs item_name"):
        activate_node(dock(tree), None, "A", mode="click_link")
    assert not tree.calls


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="mode must be"):
        activate_node(dock(_column_tree()), None, "A", mode="right_click")


def test_rejected_item_name_lists_column_names():
    with pytest.raises(RuntimeError, match=r"column names of this tree: \['C1', 'LINK'\]"):
        activate_node(dock(_column_tree()), None, "A", mode="click_link", item_name="NOPE")


# ---------------------------------------------------------------------------
# node key and tree discovery (shared by all actions)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action",
    [
        lambda s: expand_node(s, None, "3"),
        lambda s: select_node(s, None, "3"),
        lambda s: activate_node(s, None, "3"),
    ],
)
def test_bad_node_key_lists_valid_keys_and_calls_nothing(action):
    tree = _tree()
    with pytest.raises(ValueError, match="not found") as excinfo:
        action(dock(tree))
    assert "'          1'" in str(excinfo.value)  # a valid, padded key as hint
    assert not tree.calls


def test_actions_need_explicit_tree_id_when_several_trees_exist():
    t1 = _tree()
    t2 = FakeTree("wnd[0]/usr/shell", simple_nodes())
    session = FakeSession({"wnd[0]": [FakeContainer("wnd[0]/shellcont", [t1]), t2]})
    with pytest.raises(ValueError, match="trees found"):
        select_node(session, None, "          1")
    assert select_node(session, "wnd[0]/usr/shell", "          1")["tree_id"] == "wnd[0]/usr/shell"
    assert t2.calls
    assert not t1.calls


def test_actions_without_any_tree_fail():
    with pytest.raises(ValueError, match="no tree control"):
        expand_node(FakeSession({"wnd[0]": []}), None, "          1")


# ---------------------------------------------------------------------------
# Tool level
# ---------------------------------------------------------------------------


class _InlineCom:
    async def run(self, fn, **kwargs):
        assert not kwargs.get("retry_server_fault"), "actions must not be retried after a server fault"
        return fn()


def _backend(session: Any) -> DesktopBackend:
    backend = DesktopBackend(com_thread=_InlineCom())
    backend.require_session = lambda: session  # type: ignore[method-assign]
    backend.get_page_title = AsyncMock(return_value="Next screen")  # type: ignore[method-assign]
    backend.get_status_bar = AsyncMock(  # type: ignore[method-assign]
        return_value=StatusBarInfo(type="S", message="Done")
    )
    return backend


async def _call(backend: DesktopBackend, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    local = FastMCP("tree-test")
    register_tree_tools(local)
    with patch("sapguimcp.tools.tree_tools.get_backend", new=AsyncMock(return_value=backend)):
        async with Client(local) as client:
            raw = await client.call_tool(tool, args)
    return json.loads(raw.content[0].text)


@pytest.mark.anyio
async def test_activate_tool_reports_title_and_status_bar():
    tree = _column_tree()
    data = await _call(_backend(dock(tree)), "sap_tree_activate", {"node_key": "A"})
    assert data["success"] is True
    assert data["node_text"] == "Cluster"
    assert data["current_session_title_after"] == "Next screen"
    assert data["status_bar_type"] == "S"
    assert data["status_bar_message"] == "Done"
    assert tree.calls == ["DoubleClickNode('A',)"]


@pytest.mark.anyio
async def test_expand_tool_tolerates_title_lookup_failure():
    backend = _backend(dock(_tree()))
    backend.get_page_title = AsyncMock(side_effect=RuntimeError("popup"))  # type: ignore[method-assign]
    data = await _call(backend, "sap_tree_expand", {"node_key": "          3"})
    assert data["success"] is True
    assert data["expanded"] is True
    assert data["current_session_title_after"] is None


@pytest.mark.anyio
async def test_com_error_becomes_failure_not_exception():
    data = await _call(
        _backend(dock(_tree(broken_methods=("SelectNode",)))), "sap_tree_select", {"node_key": "          1"}
    )
    assert data["success"] is False
    assert "SelectNode on node '          1' failed" in data["error"]


@pytest.mark.anyio
async def test_click_link_without_item_name_is_failure():
    data = await _call(_backend(dock(_column_tree())), "sap_tree_activate", {"node_key": "A", "mode": "click_link"})
    assert data["success"] is False
    assert "needs item_name" in data["error"]


@pytest.mark.anyio
async def test_annotations_per_tool():
    local = FastMCP("tree-test")
    register_tree_tools(local)
    async with Client(local) as client:
        tools = {t.name: t.annotations for t in await client.list_tools()}
    assert tools["sap_tree_expand"].destructive_hint is False
    assert tools["sap_tree_expand"].idempotent_hint is True
    assert tools["sap_tree_select"].destructive_hint is False
    assert tools["sap_tree_select"].read_only_hint is False
    assert tools["sap_tree_activate"].destructive_hint is True
    assert tools["sap_tree_activate"].idempotent_hint is False


def test_key_lookup_stops_at_the_requested_key(monkeypatch: pytest.MonkeyPatch):
    tree = _tree()
    read: list[int] = []
    original = tree.GetAllNodeKeys

    def _counting_keys() -> Any:
        collection = original()
        item = collection.Item
        collection.Item = lambda i: (read.append(i), item(i))[1]  # type: ignore[method-assign]
        return collection

    monkeypatch.setattr(tree, "GetAllNodeKeys", _counting_keys)
    select_node(dock(tree), None, "          1")
    assert read == [0], "a key found first must not scan the rest of the tree"


@pytest.mark.anyio
async def test_action_tool_reports_a_missing_session_as_failure():
    backend = _backend(dock(_tree()))

    def _no_session() -> Any:
        raise ValueError("No active SAP session")

    backend.require_session = _no_session  # type: ignore[method-assign]
    data = await _call(backend, "sap_tree_select", {"node_key": "          1"})
    assert data["success"] is False
    assert "No active SAP session" in data["error"]
