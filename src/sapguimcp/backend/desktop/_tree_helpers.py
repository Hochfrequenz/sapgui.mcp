"""Pure COM-layer helpers for reading ``GuiTree`` controls (desktop backend).

Everything here runs on the COM thread and is synchronous. The helpers take a *raw* COM session
(``FindById`` / ``Children``) so they work with both sapsucker-wrapped and raw sessions and are
easy to fake in unit tests. Reading never expands, collapses or selects anything: it only sees the
nodes the control has already loaded (``GetAllNodeKeys``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sapguimcp.backend.desktop._com_thread import _RPC_E_DISCONNECTED, RERAISE_COM_ERRORS, _get_com_error_code

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_SCAN_NODES",
    "TREE_TYPE_NAMES",
    "find_tree_shells",
    "read_tree",
    "resolve_tree",
]

#: Hard ceiling on nodes scanned per call: a huge scan blocks the single COM engine for every agent.
MAX_SCAN_NODES = 20000
#: Upper bound for ``max_nodes`` (also enforced via the tool's ``Field``).
MAX_NODES_CEILING = 1000
#: ``GetTreeType`` values (SAP GUI Scripting API: 0 simple, 1 list, 2 column).
TREE_TYPE_NAMES = {0: "simple", 1: "list", 2: "column"}

_MAX_WALK_DEPTH = 12
_ANCESTOR_LIMIT = 200
_KEY_HINT_COUNT = 5


def _reraise_if_transient(exc: Exception) -> None:
    """Re-raise a lost connection, the errors the COM thread retries and server faults.

    Swallowing them would turn a failed read into missing parents or text, or even a "successful"
    empty result, instead of letting ``ComThread`` retry or report the failure.
    """
    if _get_com_error_code(exc) in (_RPC_E_DISCONNECTED, *RERAISE_COM_ERRORS):
        raise exc


def _collection(coll: Any, limit: int | None = None) -> list[Any]:
    """Materialise a COM collection (``Count`` + ``Item(i)``) into a list, at most ``limit`` items."""
    count = int(coll.Count)
    if limit is not None:
        count = min(count, limit)
    items: list[Any] = []
    for i in range(count):
        try:
            items.append(coll.Item(i))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _reraise_if_transient(exc)
            items.append(coll(i))
    return items


def _try(call: Callable[..., Any], *args: Any) -> Any | None:
    """Return ``call(*args)``, or ``None`` when the method is missing or raises.

    Transient COM errors (see ``_reraise_if_transient``) are not swallowed.
    """
    try:
        return call(*args)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _reraise_if_transient(exc)
        return None


def _walk(element: Any, found: list[dict[str, Any]], depth: int = 0) -> None:
    """Collect ``GuiShell`` elements with ``SubType == "Tree"`` below ``element``."""
    if depth > _MAX_WALK_DEPTH:
        logger.debug("tree discovery: depth limit %d exceeded below %r, subtree skipped", _MAX_WALK_DEPTH, element)
        return
    children = _try(lambda: _collection(element.Children))
    for child in children or []:
        if _try(getattr, child, "Type") == "GuiShell" and _try(getattr, child, "SubType") == "Tree":
            tree_type = _try(child.GetTreeType)
            if tree_type is not None:
                found.append({"id": str(child.Id), "tree_type": TREE_TYPE_NAMES.get(int(tree_type), "simple")})
                continue
        if _try(getattr, child, "ContainerType"):
            _walk(child, found, depth + 1)


def find_tree_shells(raw_session: Any) -> list[dict[str, Any]]:
    """Find tree shells in the topmost window that contains any (``wnd[3]`` down to ``wnd[0]``).

    A popup without a tree falls through to the next window below it.

    Trees often live in docking containers (``wnd[0]/shellcont/...``), outside ``wnd[0]/usr``,
    so the whole window is walked, not just ``usr``.
    """
    for window_id in ("wnd[3]", "wnd[2]", "wnd[1]", "wnd[0]"):
        window = _try(raw_session.FindById, window_id)
        if window is None:
            continue
        found: list[dict[str, Any]] = []
        _walk(window, found)
        if found:
            return found
    return []


def resolve_tree(raw_session: Any, tree_id: str | None) -> tuple[Any, str]:
    """Return ``(tree_shell, tree_id)``; auto-discover the single tree when ``tree_id`` is None.

    An explicit ``tree_id`` must name a ``GuiShell`` with ``SubType == "Tree"``; anything else raises
    ``ValueError`` naming the actual type. A missing element raises ``RuntimeError``.
    """
    if tree_id is not None:
        try:
            shell = raw_session.FindById(tree_id)
        except Exception as exc:
            _reraise_if_transient(exc)
            raise RuntimeError(f"tree {tree_id!r} not found (FindById failed: {exc})") from exc
        kind, subtype = _try(getattr, shell, "Type"), _try(getattr, shell, "SubType")
        if kind != "GuiShell" or subtype != "Tree":
            raise ValueError(f"{tree_id!r} is not a tree control (Type={kind!r}, SubType={subtype!r})")
        return shell, tree_id
    candidates = find_tree_shells(raw_session)
    if not candidates:
        raise ValueError("no tree control found in the active window; pass tree_id explicitly")
    if len(candidates) > 1:
        ids = [c["id"] for c in candidates]
        raise ValueError(f"{len(ids)} trees found in the active window; pass tree_id. Candidates: {ids}")
    found_id = candidates[0]["id"]
    return raw_session.FindById(found_id), found_id


class _TreeReader:
    """Caches per-call COM lookups (node text, parent) to avoid quadratic round trips."""

    def __init__(self, tree: Any, tree_id: str) -> None:
        self.tree = tree
        self.tree_id = tree_id
        self._text: dict[str, str] = {}
        self._parent: dict[str, str] = {}

    def text(self, key: str) -> str:
        if key not in self._text:
            label = str(self.tree.GetNodeTextByKey(key))
            if not label:
                # The SPRO IMG column tree keeps the node label empty and puts it in the TEXT item.
                # Only that item is used; other columns are never guessed (empty stays empty).
                value = _try(self.tree.GetItemText, key, "TEXT")
                if value:
                    label = str(value)
            self._text[key] = label
        return self._text[key]

    def parent(self, key: str) -> str:
        if key not in self._parent:
            value = _try(self.tree.GetParent, key)
            self._parent[key] = "" if value is None else str(value)
        return self._parent[key]

    def ancestors(self, key: str) -> list[str]:
        """Ancestor keys from the root down to (excluding) ``key``."""
        chain: list[str] = []
        current = self.parent(key)
        while current and len(chain) < _ANCESTOR_LIMIT:
            chain.append(current)
            current = self.parent(current)
        chain.reverse()
        return chain

    def path(self, key: str) -> list[str]:
        texts: list[str] = []
        for ancestor in self.ancestors(key):
            texts.append(_try(self.text, ancestor) or "")
        return texts


def _read_columns(tree: Any, tree_type: str) -> list[dict[str, str]]:
    """Named columns (column trees only); missing methods degrade to no columns."""
    if tree_type != "column":
        return []
    names = _try(lambda: [str(n) for n in _collection(tree.GetColumnNames())]) or []
    columns = []
    for name in names:
        title = _try(tree.GetColumnTitleFromName, name)
        title = "" if title is None else str(title)
        columns.append({"name": name, "title": title})
    return columns


def _read_fields(reader: _TreeReader, key: str, columns: list[dict[str, str]]) -> tuple[str, dict[str, str]]:
    """Cheap, searchable fields of a node: label and column items."""
    text = reader.text(key)
    items: dict[str, str] = {}
    for col in columns:
        value = _try(reader.tree.GetItemText, key, col["name"])
        if value is not None:
            items[col["name"]] = str(value)
    return text, items


def _build_node(reader: _TreeReader, key: str, text: str, items: dict[str, str]) -> dict[str, Any]:
    """Complete a node with path, level and folder flags (extra COM calls; only for returned nodes)."""
    tree = reader.tree
    path = reader.path(key)
    level = _try(tree.GetHierarchyLevel, key)
    expandable = _try(tree.IsFolderExpandable, key)
    expanded = _try(tree.IsFolderExpanded, key)
    if expandable is None:
        count = _try(tree.GetNodeChildrenCount, key)
        expandable = bool(count)
    return {
        "key": key,
        "text": text,
        "level": int(level) if level is not None else len(path),
        "path": path,
        "is_folder": bool(expandable),
        "expanded": None if expanded is None else bool(expanded),
        "items": items,
    }


def _matches(text: str, items: dict[str, str], needle: str, column: str | None) -> bool:
    if column is not None:
        return needle in items.get(column, "").casefold()
    if needle in text.casefold():
        return True
    return any(needle in v.casefold() for v in items.values())


def read_tree(  # pylint: disable=too-many-locals
    raw_session: Any,
    tree_id: str | None,
    *,
    search: str | None = None,
    column: str | None = None,
    max_nodes: int = 200,
    root_key: str | None = None,
) -> dict[str, Any]:
    """Read (or search) the currently loaded nodes of a tree. Never expands or selects.

    Returns a plain dict (see ``TreeReadResult``). Raises ``ValueError`` for bad arguments or an
    ambiguous / missing tree and ``RuntimeError`` for COM failures.
    """
    if not 1 <= max_nodes <= MAX_NODES_CEILING:
        raise ValueError(f"max_nodes must be between 1 and {MAX_NODES_CEILING}; got {max_nodes}")
    if column is not None and search is None:
        raise ValueError("column only restricts a search; pass search as well")

    tree, resolved_id = resolve_tree(raw_session, tree_id)
    try:
        tree_type = TREE_TYPE_NAMES.get(int(tree.GetTreeType()), "simple")
        key_collection = tree.GetAllNodeKeys()
        total_nodes = int(key_collection.Count)
        # Bound key retrieval: a huge tree must not monopolize the shared COM thread.
        keys = [str(k) for k in _collection(key_collection, MAX_SCAN_NODES)]
    except Exception as exc:
        _reraise_if_transient(exc)
        raise RuntimeError(f"tree {resolved_id!r}: reading node keys failed: {exc}") from exc

    columns = _read_columns(tree, tree_type)
    if column is not None and column not in {c["name"] for c in columns}:
        raise ValueError(
            f"column {column!r} is not a column of tree {resolved_id!r} (type {tree_type}); "
            f"available columns: {[c['name'] for c in columns]}"
        )
    if root_key is not None and root_key not in keys:
        # Beyond the scan prefix the key cannot be listed; ask the control whether it exists at all.
        beyond_prefix = total_nodes > len(keys) and _try(tree.GetNodeTextByKey, root_key) is not None
        if not beyond_prefix:
            raise ValueError(
                f"root_key {root_key!r} not found among the loaded nodes of tree {resolved_id!r}; "
                f"some valid keys: {keys[:_KEY_HINT_COUNT]}"
            )

    scan_limit_hit = total_nodes > len(keys)
    reader = _TreeReader(tree, resolved_id)
    needle = search.casefold() if search is not None else None

    nodes: list[dict[str, Any]] = []
    scanned = 0
    skipped = 0
    truncated = False
    for key in keys:
        scanned += 1
        try:
            if root_key is not None and root_key not in reader.ancestors(key):
                continue
            text, items = _read_fields(reader, key, columns)
            # Match on the cheap fields first; path/level/flags cost extra COM calls and are only
            # computed for nodes that are returned (or that prove truncation).
            if needle is not None and not _matches(text, items, needle, column):
                continue
            if len(nodes) == max_nodes:
                truncated = True
                scanned -= 1  # the node that proved truncation was looked at, not consumed
                break
            nodes.append(_build_node(reader, key, text, items))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _reraise_if_transient(exc)
            skipped += 1
            logger.debug("tree %s: skipping node %r: %s", resolved_id, key, exc)
            continue

    return {
        "tree_id": resolved_id,
        "tree_type": tree_type,
        "columns": columns,
        "nodes": nodes,
        "total_nodes": total_nodes,
        "returned_nodes": len(nodes),
        "scanned_nodes": scanned,
        "skipped_nodes": skipped,
        "truncated": truncated,
        "scan_limit_hit": scan_limit_hit,
    }
