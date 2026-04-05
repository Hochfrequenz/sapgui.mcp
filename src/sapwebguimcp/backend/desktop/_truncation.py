"""Tree truncation for LLM-facing tool responses.

Internal backend code always operates on the full tree. This module
provides helpers to truncate the tree to a given depth for tool results,
while reporting how much was hidden.
"""

from __future__ import annotations

from sapsucker.models import ElementInfo


def compute_tree_depth(tree: list[ElementInfo]) -> int:
    """Return the maximum depth of the tree (1-indexed, 0 if empty)."""
    if not tree:
        return 0
    max_child = 0
    for elem in tree:
        if elem.children:
            max_child = max(max_child, compute_tree_depth(elem.children))
    return 1 + max_child


def _count_all(elem: ElementInfo) -> int:
    """Count an element and all its descendants."""
    total = 1
    for child in elem.children:
        total += _count_all(child)
    return total


def truncate_tree(tree: list[ElementInfo], depth: int) -> tuple[list[ElementInfo], int, int]:
    """Truncate a full tree to a given depth.

    Returns:
        (truncated_tree, max_depth_found, elements_hidden)
        - truncated_tree: copy with children beyond depth replaced by []
        - max_depth_found: deepest level in the original tree
        - elements_hidden: total elements beyond the cutoff
    """
    max_depth_found = compute_tree_depth(tree)
    hidden = [0]  # mutable counter

    def _truncate(nodes: list[ElementInfo], current_depth: int) -> list[ElementInfo]:
        result = []
        for elem in nodes:
            if current_depth >= depth:
                hidden[0] += _count_all(elem)
                continue
            truncated_children = _truncate(elem.children, current_depth + 1) if elem.children else []
            result.append(elem.model_copy(update={"children": truncated_children}))
        return result

    truncated = _truncate(tree, 0)
    return truncated, max_depth_found, hidden[0]
