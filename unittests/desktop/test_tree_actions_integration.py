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
from unittests.desktop.test_tree_read_integration import _open_img, _read

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
async def test_easy_access_activate_tool_toggles_a_folder(backend):
    """Double-click a collapsed folder of the SAP Easy Access menu through the tool layer.

    A double-click on a folder expands it and a second one collapses it again, independent of
    system data, and nothing is opened. SM34 view clusters are no reliable target: switching
    views there depends on the table entries of the system.
    """
    try:
        await go_home(backend)
        tree = await _read(backend)
        session = backend.require_session()

        def _first_collapsed_folder() -> str:
            raw = getattr(session, "com", getattr(session, "_com", session)).FindById(tree["tree_id"])
            return next(
                n["key"] for n in tree["nodes"] if raw.IsFolder(n["key"]) and not raw.IsFolderExpanded(n["key"])
            )

        def _expanded(key: str) -> bool:
            raw = getattr(session, "com", getattr(session, "_com", session)).FindById(tree["tree_id"])
            return bool(raw.IsFolderExpanded(key))

        key = await backend.com.run(_first_collapsed_folder)
        local = FastMCP("tree-live")
        register_tree_tools(local)
        with patch("sapguimcp.tools.tree_tools.get_backend", AsyncMock(return_value=backend)):
            async with Client(local) as client:
                for expected in (True, False):  # expand, then collapse again
                    raw_result = await client.call_tool("sap_tree_activate", {"node_key": key})
                    data = json.loads(raw_result.content[0].text)
                    assert data["success"] is True, data["error"]
                    assert data["node_key"] == key
                    assert data["current_session_title_after"], "title after the action was not read"
                    assert await backend.com.run(lambda: _expanded(key)) is expected
    finally:
        await go_home(backend)
