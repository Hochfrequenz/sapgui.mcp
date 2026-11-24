"""Tree tools for the SAP GUI desktop backend: read, expand, select, activate, context menu.

The context-menu tool is a follow-up to https://github.com/Hochfrequenz/sapgui.mcp/issues/717.
#717's snapshot-ID fix made ``GuiShell`` trees inside a ``GuiDockShell``
reachable, but the reporter's actual workflow (right-click → "Task
anlegen" on ``/n/ABC/EXAMPLE``) still failed because
``SelectContextMenuItemByText("Task anlegen")`` raises
``SAP Error 613 — The method got an invalid argument``.

Root cause: the exact menu label is ``"Task: Anlegen"`` (with colon +
capital A). The reporter could not verify this because they could not
reach the control. The existing ``sap_com_evaluate`` tool already
supports calling ``SelectContextMenuItemByText``/``SelectContextMenuItem``/
``SelectContextMenuItemByPosition`` via chained properties, but the LLM
has no way to *discover* the exact label/fcode before calling —
``GuiShell.CurrentContextMenu.Children`` is only populated while the
menu is open, which means enumerate + select must happen in one COM
round-trip.

This tool provides that round-trip. It opens the context menu for the
given node, reads every item's ``Text`` and ``Name`` (the function
code), and optionally fires ``SelectContextMenu*`` for one of them —
all in one lambda on the COM thread.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.desktop._tree_helpers import activate_node, expand_node, read_tree, select_node
from sapguimcp.backend.desktop.models.com_results import (
    TreeActionResult,
    TreeColumn,
    TreeContextMenuItem,
    TreeContextMenuResult,
    TreeNode,
    TreeReadResult,
)
from sapguimcp.backend.manager import get_backend

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

__all__ = ["register_tree_tools", "_invoke_tree_context_menu", "_read_tree"]

# Shared parameters of the tree action tools.
_TreeId = Annotated[str | None, Field(description="Tree element ID from sap_tree_read. Omit to auto-discover.")]
_NodeKey = Annotated[str, Field(description="Node `key` from sap_tree_read, unchanged (padded).")]


def _invoke_tree_context_menu(  # pylint: disable=too-many-arguments,too-many-locals
    session: Any,
    shell_id: str,
    node_key: str,
    *,
    select_text: str | None,
    select_fcode: str | None,
    select_position: int | None,
) -> dict[str, Any]:
    """Open a tree's context menu, enumerate items, optionally select one.

    Pure COM-layer function — must run on the ComThread. Returns a dict
    with ``items`` and ``selected`` keys; raises ``ValueError`` for
    invalid arg combinations and ``RuntimeError`` when a requested
    selection fails (the raised message includes the enumerated items
    so the LLM can retry with a correct label).

    ``session`` is either a sapsucker-wrapped ``GuiSession`` or a raw COM
    object; this helper unwraps via the common ``.com`` / ``._com``
    attribute used elsewhere in the desktop backend.
    """
    select_args = [
        name
        for name, value in (
            ("select_text", select_text),
            ("select_fcode", select_fcode),
            ("select_position", select_position),
        )
        if value is not None
    ]
    if len(select_args) > 1:
        raise ValueError(f"select_text / select_fcode / select_position are mutually exclusive; got {select_args}")

    raw_session = getattr(session, "com", getattr(session, "_com", session))
    shell = raw_session.FindById(shell_id)

    # SelectNode before NodeContextMenu mirrors what SAP GUI Scripting Recorder
    # emits for tree right-clicks — a TableTreeControl.1 probe (see
    # scripts/probe_tree_context_menu.py) confirmed both calls are needed for
    # CurrentContextMenu to populate. Trees that don't require it still tolerate
    # the extra selectionChanged event; this path prioritises "works everywhere".
    shell.SelectNode(node_key)
    shell.NodeContextMenu(node_key)

    # Enumerate BEFORE selecting — the menu state disappears the moment
    # an item is fired, and we want to return the full list either way.
    ccm = shell.CurrentContextMenu
    if ccm is None:
        raise RuntimeError(
            f"no context menu opened for node_key={node_key!r} on {shell_id!r}; "
            "either the node does not exist or the shell does not expose a context menu"
        )
    children = ccm.Children
    items: list[dict[str, Any]] = []
    for i in range(children.Count):
        mi = children.Item(i)
        items.append(
            {
                "position": i,
                "text": str(getattr(mi, "Text", "")),
                "fcode": str(getattr(mi, "Name", "")),
            }
        )

    selected: dict[str, Any] | None = None
    try:
        if select_text is not None:
            shell.SelectContextMenuItemByText(select_text)
            # Only set ``selected`` when the match is unambiguous — SAP fires by
            # text match server-side, but if duplicates exist we cannot tell
            # which one server actually picked, so we surface that as unknown.
            matches = [it for it in items if it["text"] == select_text]
            selected = matches[0] if len(matches) == 1 else None
        elif select_fcode is not None:
            shell.SelectContextMenuItem(select_fcode)
            selected = next((it for it in items if it["fcode"] == select_fcode), None)
        elif select_position is not None:
            shell.SelectContextMenuItemByPosition(select_position)
            selected = next((it for it in items if it["position"] == select_position), None)
    except Exception as exc:
        # Include the enumerated items so the LLM's next attempt picks a valid one.
        raise RuntimeError(f"selection failed ({exc}); available items: {items}") from exc

    return {"items": items, "selected": selected}


def _read_tree(
    session: Any,
    tree_id: str | None,
    *,
    search: str | None,
    column: str | None,
    max_nodes: int,
    root_key: str | None,
) -> dict[str, Any]:
    """Read or search the loaded nodes of a tree. Pure COM-layer function — must run on the ComThread.

    ``session`` is a sapsucker-wrapped session or a raw COM object. Never expands, collapses or
    selects. Raises ``ValueError`` for bad arguments / ambiguous trees, ``RuntimeError`` on COM errors.
    """
    raw_session = getattr(session, "com", getattr(session, "_com", session))
    return read_tree(raw_session, tree_id, search=search, column=column, max_nodes=max_nodes, root_key=root_key)


async def _run_tree_action(
    tool_name: str, session: str | None, agent_id: str | None, action: Callable[[Any], dict[str, Any]]
) -> TreeActionResult:
    """Shared body of the tree action tools: run ``action(raw_session)`` on the COM thread.

    ``ValueError`` / ``RuntimeError`` become failures. The current session's title and status bar are
    read afterwards, because an action can navigate; a failure to read them is tolerated.
    """
    try:
        backend = await get_backend(session=session, agent_id=agent_id, tool_name=tool_name)
        desktop_session = backend.require_session()
    except ValueError as e:
        return TreeActionResult.failure(str(e))

    def _run() -> dict[str, Any]:
        return action(getattr(desktop_session, "com", getattr(desktop_session, "_com", desktop_session)))

    try:
        raw = await backend.com.run(_run)
    except (ValueError, RuntimeError) as exc:
        return TreeActionResult.failure(str(exc))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("%s failed", tool_name)
        return TreeActionResult.failure(f"COM execution error: {exc}")

    result = TreeActionResult(**raw)
    try:
        result.current_session_title_after = await backend.get_page_title()
        status = await backend.get_status_bar()
        result.status_bar_type, result.status_bar_message = status.type, status.message
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.debug("%s: reading title / status bar after the action failed: %s", tool_name, exc)
    logger.info("tree_action", extra={"tool": tool_name, "tree_id": result.tree_id, "node_key": result.node_key})
    return result


def register_tree_tools(mcp: FastMCP) -> None:
    """Register tree tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        description=(
            "Read or search the nodes of a SAP tree control (SPRO IMG, SE80 object tree, SM34 "
            "navigation tree, ...). Read-only: never expands, collapses "
            "or selects anything.\n\n"
            "Only nodes the control has ALREADY LOADED (expanded) are visible; collapsed subtrees "
            "stay hidden until they are expanded. Workflow: read, `sap_tree_expand` a folder, read "
            "again (`root_key` = that folder), then `sap_tree_select` or `sap_tree_activate` a node "
            "by its `key`. Without `tree_id` the single tree of "
            "the active window is auto-discovered, including trees in docking containers "
            "(`wnd[0]/shellcont/...`); with several trees the error lists the candidate IDs.\n\n"
            "`search` is a case-insensitive substring match over loaded nodes (node text and, for "
            "column trees, all column texts, or only `column`); matches carry the ancestor `path`. "
            "`root_key` restricts output to the descendants of one node. Output is capped at "
            "`max_nodes` (default 200, max 1000); `truncated` and `total_nodes` tell what was missed.\n\n"
            "Node order is SAP's `GetAllNodeKeys` order, which is not documented as display order; "
            "use `level` and `path` to rebuild the hierarchy. `key` values are opaque and "
            "space-padded: pass them back unchanged."
        ),
    )
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    async def sap_tree_read(
        tree_id: Annotated[
            str | None,
            Field(description="Tree element ID (e.g. 'wnd[0]/shellcont/shell'). Omit to auto-discover."),
        ] = None,
        search: Annotated[
            str | None, Field(description="Case-insensitive substring to look for in loaded nodes.")
        ] = None,
        column: Annotated[
            str | None, Field(description="Restrict `search` to this column name (column trees only).")
        ] = None,
        max_nodes: Annotated[int, Field(ge=1, le=1000, description="Maximum nodes to return.")] = 200,
        root_key: Annotated[
            str | None, Field(description="Only return descendants of this node key (exact, padded).")
        ] = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TreeReadResult:
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_tree_read")
        except ValueError as e:
            return TreeReadResult.failure(str(e))

        desktop_session = backend.require_session()

        def _run() -> dict[str, Any]:
            return _read_tree(
                desktop_session, tree_id, search=search, column=column, max_nodes=max_nodes, root_key=root_key
            )

        try:
            # Read-only and re-fetches everything inside _run, so a server fault may be retried.
            raw = await backend.com.run(_run, retry_server_fault=True)
        except (ValueError, RuntimeError) as exc:
            return TreeReadResult.failure(str(exc))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_tree_read failed")
            return TreeReadResult.failure(f"COM execution error: {exc}")

        return TreeReadResult(
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

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        description=(
            "Expand (or with expand=false collapse) one folder node of a tree; not recursive. "
            "Returns the state read back and the number of loaded children."
        ),
    )
    async def sap_tree_expand(
        node_key: _NodeKey,
        tree_id: _TreeId = None,
        expand: bool = True,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TreeActionResult:
        return await _run_tree_action(
            "sap_tree_expand", session, agent_id, lambda raw: expand_node(raw, tree_id, node_key, expand=expand)
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        description="Select one node of a tree (changes only the selection).",
    )
    async def sap_tree_select(
        node_key: _NodeKey,
        tree_id: _TreeId = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TreeActionResult:
        return await _run_tree_action(
            "sap_tree_select", session, agent_id, lambda raw: select_node(raw, tree_id, node_key)
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
        ),
        description=(
            "Activate a tree node like a user would: double-click the node (or the item `item_name`), "
            "or with mode='click_link' click the hyperlink item `item_name` (a column name from "
            "sap_tree_read; list trees number their items '1', '2', ...). "
            "Can navigate or start an action; check the returned title and status bar."
        ),
    )
    async def sap_tree_activate(
        node_key: _NodeKey,
        tree_id: _TreeId = None,
        mode: Literal["double_click", "click_link"] = "double_click",
        item_name: Annotated[str | None, Field(description="Column name of the item to click.")] = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TreeActionResult:
        return await _run_tree_action(
            "sap_tree_activate",
            session,
            agent_id,
            lambda raw: activate_node(raw, tree_id, node_key, mode=mode, item_name=item_name),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            open_world_hint=False,
        ),
        description=(
            "Invoke the right-click context menu on a ``GuiShell``/``GuiTree`` node.\n\n"
            "Use this when you want to discover or fire an action from a tree node's "
            "context menu — e.g. a 'create' entry in an application tree — and the plain "
            "``sap_com_evaluate`` path fails because you don't know the exact label text.\n\n"
            "**Workflow:**\n"
            "1. `sap_com_snapshot` → copy the tree's ``id=`` (e.g. `wnd[0]/shellcont/shell`).\n"
            "2. Use `sap_com_evaluate` with `GetAllNodeKeys` / `GetNodeTextByKey` "
            "to find the `node_key` you want to right-click on.\n"
            "3. Call this tool with ``shell_id`` + ``node_key`` and NO select_* arg to "
            "enumerate the available items (text + fcode).\n"
            "4. Call again with ``select_text`` (exact label) or ``select_fcode`` "
            "(the `fcode` field) or ``select_position`` (0-based index) to fire it.\n\n"
            "Labels are case- and punctuation-sensitive — use the exact `text` field "
            "returned in step 3. Typical gotchas: 'Task: Anlegen' not 'Task anlegen'.\n\n"
            "**Prefer `select_fcode` over `select_text` for stability** — fcodes are "
            "language-independent (e.g. `T_1310` regardless of SAP logon language) and "
            "immune to punctuation/casing drift.\n\n"
            "Some menu actions open the follow-up screen in a PARALLEL SAP session "
            "(e.g. some 'create' entries open in a new session), not the current window. "
            "After a select call, use `sap_com_snapshot` or iterate the connection's "
            "child sessions to locate the new screen.\n\n"
            "`select_*` args are mutually exclusive; pass at most one."
        ),
    )
    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    async def sap_tree_context_menu(
        shell_id: Annotated[
            str, Field(description="Tree/GuiShell ID from sap_com_snapshot, e.g. 'wnd[0]/shellcont/shell'")
        ],
        node_key: Annotated[str, Field(description="Tree node key (from GetAllNodeKeys), e.g. 'TAGR__   16'")],
        select_text: Annotated[
            str | None,
            Field(
                default=None,
                description="Exact menu label to select (case/punctuation-sensitive).",
            ),
        ] = None,
        select_fcode: Annotated[
            str | None,
            Field(
                default=None,
                description="Internal function code / Name of the menu item (e.g. 'T_1310').",
            ),
        ] = None,
        select_position: Annotated[
            int | None,
            Field(
                default=None,
                description="0-based position of the item. Brittle — prefer select_text or select_fcode.",
            ),
        ] = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TreeContextMenuResult:
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_tree_context_menu")
        except ValueError as e:
            return TreeContextMenuResult.failure(str(e))

        desktop_session = backend.require_session()
        com = backend.com

        def _run() -> dict[str, Any]:
            return _invoke_tree_context_menu(
                desktop_session,
                shell_id,
                node_key,
                select_text=select_text,
                select_fcode=select_fcode,
                select_position=select_position,
            )

        try:
            raw = await com.run(_run)
        except ValueError as exc:
            return TreeContextMenuResult.failure(str(exc))
        except RuntimeError as exc:
            return TreeContextMenuResult.failure(str(exc))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("sap_tree_context_menu failed")
            return TreeContextMenuResult.failure(f"COM execution error: {exc}")

        items = [TreeContextMenuItem(**it) for it in raw["items"]]
        selected = TreeContextMenuItem(**raw["selected"]) if raw["selected"] is not None else None

        # Current-session title after the action — note that many menu actions
        # open a PARALLEL session, in which case this
        # stays on the original screen. The field name reflects that honestly.
        current_session_title_after: str | None = None
        try:
            current_session_title_after = await backend.get_page_title()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("get_page_title after tree context menu failed: %s", exc)

        logger.info(
            "tree_context_menu",
            extra={
                "shell_id": shell_id,
                "node_key": node_key,
                "item_count": len(items),
                "selected_text": selected.text if selected else None,
            },
        )
        return TreeContextMenuResult(
            items=items,
            selected=selected,
            current_session_title_after=current_session_title_after,
        )
