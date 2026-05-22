"""Tree context-menu tool for the SAP GUI desktop backend.

Follow-up to https://github.com/Hochfrequenz/sapgui.mcp/issues/717.
#717's snapshot-ID fix made ``GuiShell`` trees inside a ``GuiDockShell``
reachable, but the reporter's actual workflow (right-click → "Task
anlegen" on ``/n/NA2/DCS``) still failed because
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
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from sapguimcp.backend.desktop.models.com_results import (
    TreeContextMenuItem,
    TreeContextMenuResult,
)
from sapguimcp.backend.manager import get_backend

logger = logging.getLogger(__name__)

__all__ = ["register_tree_tools", "_invoke_tree_context_menu"]


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
    # emits for tree right-clicks — the DCS TableTreeControl.1 probe (see
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


def register_tree_tools(mcp: FastMCP) -> None:
    """Register tree-tool(s) with the MCP server — desktop backend only."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            openWorldHint=False,
        ),
        description=(
            "Invoke the right-click context menu on a ``GuiShell``/``GuiTree`` node "
            "(desktop backend only).\n\n"
            "Use this when you want to discover or fire an action from a tree node's "
            "context menu — e.g. 'Task: Anlegen' on ``/n/NA2/DCS`` — and the plain "
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
            "(e.g. DCS 'Task: Anlegen' opens in a new session), not the current window. "
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

        if backend.backend_type != "desktop":
            return TreeContextMenuResult.failure("sap_tree_context_menu is only available on the desktop backend.")

        from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, DesktopBackend)  # noqa: S101
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
        # open a PARALLEL session (DCS 'Task: Anlegen' does), in which case this
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
