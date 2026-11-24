"""Live integration tests for the tree action helpers behind ``sap_tree_expand``, ``sap_tree_select``
and ``sap_tree_activate``.

Nothing is changed in the system: the tests only expand, collapse and select nodes, and the one
activation switches views in a view cluster opened in display mode. Requires desktop SAP
credentials (see docs/SAP_TEST_PREREQUISITES.md); skipped without them. Every test returns to the
Easy Access screen in ``finally``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from sapguimcp.backend.desktop._tree_helpers import activate_node, expand_node, select_node
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
async def test_sm34_double_click_switches_view(backend):
    try:
        await go_home(backend)
        tx = await backend.enter_transaction("SM34")
        assert tx.success, tx.error
        await backend.wait_for_ready()
        session = backend.require_session()

        def _open_cluster_in_display_mode() -> None:
            raw = getattr(session, "com", getattr(session, "_com", session))
            raw.FindById("wnd[0]/usr/ctxtVCLDIR-VCLNAME").Text = SM34_CLUSTER
            raw.FindById("wnd[0]/usr/btnSHOW_PUSH").Press()

        await backend.com.run(_open_cluster_in_display_mode)
        await backend.wait_for_ready()
        tree = await _read(backend)
        assert len(tree["nodes"]) >= 2, "view cluster needs at least two views"
        title_before = await backend.get_page_title()

        target = tree["nodes"][-1]
        result = await _act(backend, lambda raw: activate_node(raw, None, target["key"]))
        await backend.wait_for_ready()
        title_after = await backend.get_page_title()
        print("SM34 ACTIVATE", result, repr(title_before), "->", repr(title_after))
        assert result["node_text"] == target["text"]
        assert title_after != title_before, "double-click on another view did not switch the view"
    finally:
        await go_home(backend)
