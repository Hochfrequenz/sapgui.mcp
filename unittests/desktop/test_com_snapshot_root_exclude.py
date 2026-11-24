"""sap_com_snapshot: ``root`` starts the dump at an element, ``exclude`` prunes subtrees (#998)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from sapsucker.models import ElementInfo

from sapguimcp.backend.desktop import DesktopBackend
from unittests.desktop.conftest import go_home, skip_no_sap

_W = "/app/con[0]/ses[0]/wnd[0]"


def _elem(elem_id: str, children: list[ElementInfo] | None = None) -> ElementInfo:
    return ElementInfo(
        id=elem_id,
        type="GuiTextField",
        type_as_number=31,
        name=elem_id,
        text="",
        changeable=False,
        children=children or [],
    )


class _FakeComThread:
    async def run(self, fn: Any, **_: Any) -> Any:
        return fn()


def _backend(elements: dict[str, list[ElementInfo]]) -> DesktopBackend:
    """A backend whose session knows the elements in *elements* (id -> what its dump_tree returns)."""

    def find_by_id(elem_id: str, raise_error: bool = True) -> Any:  # noqa: ARG001 - mirrors sapsucker
        if elem_id not in elements:
            return None
        return MagicMock(dump_tree=MagicMock(return_value=elements[elem_id]))

    backend = DesktopBackend(com_thread=_FakeComThread())  # type: ignore[arg-type]
    backend.require_session = lambda: MagicMock(find_by_id=find_by_id)  # type: ignore[method-assign]
    return backend


_USR = [_elem(f"{_W}/usr/txtFIELD")]
_WINDOW = [
    _elem(f"{_W}/mbar", children=[_elem(f"{_W}/mbar/menu[0]")]),
    _elem(f"{_W}/usr", children=_USR),
]


@pytest.mark.anyio
async def test_exclude_leaves_out_the_menu_bar() -> None:
    snapshot, _, _, excluded = await _backend({"wnd[0]": _WINDOW}).get_snapshot_with_depth(
        depth=5, exclude=["wnd[0]/mbar"]
    )
    assert "mbar" not in str(snapshot)
    assert "usr/txtFIELD" in str(snapshot)
    assert excluded == 2


@pytest.mark.anyio
async def test_root_starts_the_tree_and_the_depth_there() -> None:
    snapshot, max_depth, hidden, excluded = await _backend(
        {"wnd[0]": _WINDOW, "wnd[0]/usr": _USR}
    ).get_snapshot_with_depth(depth=1, root="wnd[0]/usr")
    assert "txtFIELD" in str(snapshot)
    assert "mbar" not in str(snapshot)
    assert (max_depth, hidden, excluded) == (1, 0, 0)


@pytest.mark.anyio
async def test_unknown_root_is_an_error() -> None:
    with pytest.raises(ValueError, match="wnd\\[0\\]/nope"):
        await _backend({"wnd[0]": _WINDOW}).get_snapshot_with_depth(root="wnd[0]/nope")


@skip_no_sap
@pytest.mark.anyio
async def test_live_root_and_exclude(backend: Any) -> None:
    await go_home(backend)
    full, *_ = await backend.get_snapshot_with_depth(depth=4)
    pruned, _, _, excluded = await backend.get_snapshot_with_depth(depth=4, exclude=["wnd[0]/mbar"])
    usr, *_ = await backend.get_snapshot_with_depth(depth=2, root="wnd[0]/usr")
    assert "GuiMenubar" in str(full)
    assert "GuiMenubar" not in str(pruned)
    assert excluded
    assert len(str(pruned)) < len(str(full))
    assert "GuiToolbar" not in str(usr)
