"""Live integration tests for ``sap_tree_read`` (``_read_tree``) against a real SAP GUI session.

Read-only: nothing is expanded, selected or changed. Requires desktop SAP credentials
(see docs/SAP_TEST_PREREQUISITES.md); skipped without them. Every test returns to the
Easy Access screen in ``finally``.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from sapguimcp.tools.spro_tools import _spro_img_tree_loaded
from sapguimcp.tools.tree_tools import _read_tree
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

# Standard FI view cluster that exists on S/4HANA and ECC.
SM34_CLUSTER = "VC_055_D"
# Standard IMG area, in English and German logon languages.
IMG_AREA_TEXTS = ("Enterprise Structure", "Unternehmensstruktur")


async def _read(backend, **kwargs: Any) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    session = backend.require_session()
    kwargs.setdefault("tree_id", None)
    kwargs.setdefault("search", None)
    kwargs.setdefault("column", None)
    kwargs.setdefault("max_nodes", 200)
    kwargs.setdefault("root_key", None)
    tree_id = kwargs.pop("tree_id")
    return await backend.com.run(lambda: _read_tree(session, tree_id, **kwargs))


async def _loaded_key_count(backend, tree_id: str) -> int:  # type: ignore[no-untyped-def]
    session = backend.require_session()

    def _count() -> int:
        raw = getattr(session, "com", getattr(session, "_com", session))
        return int(raw.FindById(tree_id).GetAllNodeKeys().Count)

    return await backend.com.run(_count)


async def _open_img(backend) -> None:  # type: ignore[no-untyped-def]
    await go_home(backend)
    tx = await backend.enter_transaction("SPRO")
    assert tx.success, tx.error
    await backend.wait_for_ready()
    await backend.press_key("F5")
    await backend.wait_for_ready()
    assert await backend.wait_for_condition(_spro_img_tree_loaded, timeout_ms=30000), "IMG tree did not load"


@skip_no_sap
@pytest.mark.anyio
async def test_spro_img_top_level_and_truncation(backend):
    try:
        await _open_img(backend)
        result = await _read(backend)
        print("SPRO", {k: v for k, v in result.items() if k != "nodes"}, list(result["nodes"][:3]))
        assert result["tree_type"] in ("simple", "list", "column")
        assert result["nodes"], "IMG tree returned no nodes"
        assert all(n["text"] for n in result["nodes"]), "IMG node labels must not be empty"
        assert result["returned_nodes"] <= 200

        capped = await _read(backend, max_nodes=10)
        assert capped["returned_nodes"] == 10
        assert capped["truncated"] is True
        assert capped["total_nodes"] >= 10
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_spro_search_finds_standard_area_with_path_and_does_not_expand(backend):
    try:
        await _open_img(backend)
        before = await _read(backend, max_nodes=1)
        count_before = await _loaded_key_count(backend, before["tree_id"])

        result = None
        for text in IMG_AREA_TEXTS:
            result = await _read(backend, search=text)
            if result["nodes"]:
                break
        assert result is not None
        assert result["nodes"], f"none of {IMG_AREA_TEXTS} found in the loaded IMG nodes"
        print("SEARCH", result["nodes"][0]["text"], result["nodes"][0]["path"], result["nodes"][0]["level"])
        assert result["nodes"][0]["text"]
        assert result["nodes"][0]["path"], "match must carry its ancestor path"
        assert all(result["nodes"][0]["path"]), "ancestor labels must not be empty"

        count_after = await _loaded_key_count(backend, before["tree_id"])
        assert count_after == count_before == before["total_nodes"], "reading/searching must not expand nodes"
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se80_docking_tree_auto_discovery(backend):
    try:
        await go_home(backend)
        tx = await backend.enter_transaction("SE80")
        assert tx.success, tx.error
        await backend.wait_for_ready()
        result = await _read(backend, max_nodes=50)
        print("SE80", {k: v for k, v in result.items() if k != "nodes"}, list(result["nodes"][:3]))
        assert "shellcont" in result["tree_id"] or "cntl" in result["tree_id"]
        assert result["total_nodes"] >= 1
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm34_navigation_tree(backend):
    try:
        await go_home(backend)
        tx = await backend.enter_transaction("SM34")
        assert tx.success, tx.error
        await backend.wait_for_ready()
        session = backend.require_session()

        def _open_cluster() -> None:
            raw = getattr(session, "com", getattr(session, "_com", session))
            raw.FindById("wnd[0]/usr/ctxtVCLDIR-VCLNAME").Text = SM34_CLUSTER
            raw.FindById("wnd[0]/usr/btnSHOW_PUSH").Press()

        await backend.com.run(_open_cluster)
        await backend.wait_for_ready()
        result = await _read(backend)
        print("SM34", {k: v for k, v in result.items() if k != "nodes"}, list(result["nodes"][:3]))
        print("SM34 first node", result["nodes"][0] if result["nodes"] else None)
        assert result["tree_type"] == "column"
        assert result["nodes"]
    finally:
        await go_home(backend)
