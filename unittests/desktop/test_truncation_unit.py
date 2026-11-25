"""Unit tests for tree truncation helper."""

from __future__ import annotations

from sapsucker.models import ElementInfo

from sapguimcp.backend.desktop._truncation import compute_tree_depth, prune_tree, truncate_tree


def _elem(id: str, children: list | None = None) -> ElementInfo:
    return ElementInfo(
        id=id,
        type="GuiTextField",
        type_as_number=31,
        name=id,
        text="",
        changeable=False,
        children=children or [],
    )


def test_flat_tree_no_truncation():
    tree = [_elem("a"), _elem("b")]
    result, max_depth, hidden = truncate_tree(tree, depth=5)
    assert len(result) == 2
    assert max_depth == 1
    assert hidden == 0


def test_truncation_at_depth_1():
    tree = [_elem("a", children=[_elem("a1"), _elem("a2")])]
    result, max_depth, hidden = truncate_tree(tree, depth=1)
    assert len(result) == 1
    assert result[0].children == []
    assert max_depth == 2
    assert hidden == 2


def test_truncation_preserves_shallow_children():
    tree = [_elem("a", children=[_elem("a1", children=[_elem("a1a")])])]
    result, max_depth, hidden = truncate_tree(tree, depth=2)
    assert len(result[0].children) == 1
    assert result[0].children[0].children == []
    assert max_depth == 3
    assert hidden == 1


def test_no_truncation_when_depth_exceeds_tree():
    tree = [_elem("a", children=[_elem("a1")])]
    result, max_depth, hidden = truncate_tree(tree, depth=99)
    assert len(result[0].children) == 1
    assert max_depth == 2
    assert hidden == 0


def test_compute_tree_depth_empty():
    assert compute_tree_depth([]) == 0


def test_compute_tree_depth_nested():
    tree = [_elem("a", children=[_elem("b", children=[_elem("c")])])]
    assert compute_tree_depth(tree) == 3


_W = "/app/con[0]/ses[0]/wnd[0]"


def _window_tree() -> list[ElementInfo]:
    return [
        _elem(f"{_W}/mbar", children=[_elem(f"{_W}/mbar/menu[0]"), _elem(f"{_W}/mbar/menu[1]")]),
        _elem(f"{_W}/mbarX"),
        _elem(f"{_W}/usr", children=[_elem(f"{_W}/usr/txtFIELD")]),
    ]


def test_prune_tree_drops_the_prefix_and_its_subtree():
    result, pruned = prune_tree(_window_tree(), ["wnd[0]/mbar"])
    assert [e.id for e in result] == [f"{_W}/mbarX", f"{_W}/usr"]  # mbarX is not below mbar (path boundary)
    assert pruned == 3
    assert result[1].children[0].id == f"{_W}/usr/txtFIELD"


def test_prune_tree_matches_nested_and_absolute_prefixes():
    result, pruned = prune_tree(_window_tree(), [f"{_W}/usr/txtFIELD/", "wnd[0]/mbar/menu[1]"])
    assert result[2].children == []
    assert [e.id for e in result[0].children] == [f"{_W}/mbar/menu[0]"]
    assert pruned == 2


def test_prune_tree_without_prefixes_keeps_everything():
    result, pruned = prune_tree(_window_tree(), [])
    assert result == _window_tree()
    assert pruned == 0
