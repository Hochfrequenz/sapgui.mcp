"""Live integration tests for the tree action helpers behind ``sap_tree_expand``, ``sap_tree_select``
and ``sap_tree_activate``.

Nothing is changed in the system: the tests only expand, collapse and select nodes, and the one
activation switches views in a view cluster opened in display mode (selecting a table row
first when only a dependent view is available). Requires desktop SAP
credentials (see docs/SAP_TEST_PREREQUISITES.md); skipped without them. Every test returns to the
Easy Access screen in ``finally``.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.backend.desktop._tree_helpers import expand_node, select_node
from sapguimcp.tools.tree_tools import register_tree_tools
from unittests.desktop.conftest import go_home, skip_no_sap
from unittests.desktop.test_tree_read_integration import SM34_CLUSTER, _open_img, _read

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


async def _act(backend, action: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    session = backend.require_session()
    return await backend.com.run(lambda: action(getattr(session, "com", getattr(session, "_com", session))))


@skip_no_sap
@pytest.mark.anyio
async def test_spro_expand_read_collapse_select(backend):
    try:
        await _open_img(backend)
        top = await _read(backend)
        folder = next((n for n in top["nodes"] if n["is_folder"] and n["expanded"] is False), None)
        assert folder is not None, "no collapsed folder among the loaded IMG nodes"
        key = folder["key"]

        expanded = await _act(backend, lambda raw: expand_node(raw, None, key))
        print("EXPAND", expanded)
        assert expanded["expanded"] is True
        assert expanded["child_count"] > 0
        assert expanded["node_text"] == folder["text"]

        children = await _read(backend, root_key=key)
        assert children["nodes"], "expanded folder shows no loaded descendants"
        assert all(folder["text"] in n["path"] for n in children["nodes"])

        collapsed = await _act(backend, lambda raw: expand_node(raw, None, key, expand=False))
        assert collapsed["expanded"] is False

        selected = await _act(backend, lambda raw: select_node(raw, None, key))
        assert selected["node_key"] == key
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_spro_unknown_node_key_is_value_error(backend):
    try:
        await _open_img(backend)
        with pytest.raises(ValueError, match="not found"):
            await _act(backend, lambda raw: select_node(raw, None, "NO_SUCH_NODE_KEY"))
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se80_select_in_docking_tree(backend):
    try:
        await go_home(backend)
        tx = await backend.enter_transaction("SE80")
        assert tx.success, tx.error
        await backend.wait_for_ready()
        tree = await _read(backend, max_nodes=1)
        assert tree["nodes"], "SE80 object tree has no loaded node"
        key = tree["nodes"][0]["key"]
        result = await _act(backend, lambda raw: select_node(raw, None, key))
        print("SE80 SELECT", result)
        assert result["tree_id"] == tree["tree_id"]
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm34_activate_tool_switches_view(backend):
    """Double-click another view of a view cluster through the tool layer; the window title changes.

    The target is chosen from the tree structure: another top-level view when there is one, else a
    dependent view of the current one, which needs a selected entry first (the first table row).
    """
    try:
        await go_home(backend)
        tx = await backend.enter_transaction("SM34")
        assert tx.success, tx.error
        await backend.wait_for_ready()
        session = backend.require_session()

        def _raw() -> Any:
            return getattr(session, "com", getattr(session, "_com", session))

        def _open_cluster_in_display_mode() -> None:
            _raw().FindById("wnd[0]/usr/ctxtVCLDIR-VCLNAME").Text = SM34_CLUSTER
            _raw().FindById("wnd[0]/usr/btnSHOW_PUSH").Press()

        await backend.com.run(_open_cluster_in_display_mode)
        await backend.wait_for_ready()
        tree = await _read(backend)
        top_level = min(n["level"] for n in tree["nodes"])
        top = [n for n in tree["nodes"] if n["level"] == top_level]

        def _selected_node() -> str:
            try:
                return str(_raw().FindById(tree["tree_id"]).SelectedNode or "")
            except Exception:  # some trees do not expose a single selected node
                return ""

        selected = await backend.com.run(_selected_node)
        current = selected if selected in {n["key"] for n in top} else top[0]["key"]

        others = [n for n in top if n["key"] != current]
        if others:
            target = others[0]
        else:
            dependents = (await _read(backend, root_key=current))["nodes"]
            assert dependents, "view cluster has neither a second view nor a dependent view"
            target = dependents[0]

            def _select_first_row() -> None:
                usr = _raw().FindById("wnd[0]/usr")
                tables = [usr.Children.Item(i) for i in range(usr.Children.Count)]
                table = next(t for t in tables if t.Type == "GuiTableControl")
                table.GetAbsoluteRow(0).Selected = True

            await backend.com.run(_select_first_row)

        title_before = await backend.get_page_title()
        local = FastMCP("tree-live")
        register_tree_tools(local)
        with patch("sapguimcp.tools.tree_tools.get_backend", AsyncMock(return_value=backend)):
            async with Client(local) as client:
                raw = await client.call_tool("sap_tree_activate", {"node_key": target["key"]})
        data = json.loads(raw.content[0].text)
        print("SM34 ACTIVATE", "dependent" if not others else "top-level", data, repr(title_before))
        assert data["success"] is True, data["error"]
        assert data["node_text"] == target["text"]
        assert data["status_bar_type"] is not None
        assert data["current_session_title_after"], "title after the action was not read"
        assert data["current_session_title_after"] != title_before, "activating another view did not switch"
    finally:
        await go_home(backend)
