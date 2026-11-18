"""
SPRO (Customizing IMG) search tool.

This module provides a tool to search the SAP Implementation Guide (IMG)
for customizing activities by keyword. Returns structured results with
activity names, parent nodes, and area context.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.models.spro_models import SPROActivity, SPROFileSummary, SPROSearchResult

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend


logger = logging.getLogger(__name__)

__all__ = ["register_spro_tools"]

#: The search reads the IMG tree itself, two levels deep.
_DESKTOP_SCOPE_NOTE = (
    "Only the top two levels of the IMG tree (areas and their direct entries) were searched, not the activities "
    "below them: more matches may exist than are listed."
)

# SPRO IMG tree control element ID (stable across languages)
_SPRO_TREE_ID = "wnd[0]/usr/cntlTREE_CONTROL_CONTAINER/shellcont/shell"


# =============================================================================
# SPRO Navigation Helpers
# =============================================================================


def _spro_img_tree_loaded(session: Any) -> bool:
    """Predicate: True once the IMG tree control exists and has nodes, or a popup is open."""
    if session.find_by_id("wnd[1]", raise_error=False) is not None:
        return True
    tree = session.find_by_id(_SPRO_TREE_ID, raise_error=False)
    if tree is None:
        return False
    raw: Any = getattr(tree, "com", getattr(tree, "_com", tree))
    return int(raw.GetAllNodeKeys().Count) > 0


async def _search_img_desktop(  # pylint: disable=too-many-locals
    backend: "DesktopBackend", query: str
) -> SPROSearchResult:
    """Desktop-specific SPRO IMG search using tree control node reading.

    SAP GUI scripting does not expose the SPRO search dialog.
    Instead, we expand the IMG tree nodes (2 levels deep) and filter by query text.
    """

    now = datetime.now(UTC)

    # Navigate to SPRO and open IMG tree
    tx = await backend.enter_transaction("SPRO")
    if not tx.success:
        return SPROSearchResult.failure(
            error=f"Failed to navigate to SPRO: {tx.error}",
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )
    await backend.wait_for_ready()

    # Press F5 for SAP Reference IMG
    await backend.press_key("F5")
    await backend.wait_for_ready()
    # The next step reads the IMG tree's node keys: wait until the tree is populated (or a popup blocks it).
    await backend.wait_for_condition(_spro_img_tree_loaded)

    session = backend.require_session()
    com = backend.com

    def _read_and_search() -> list[dict[str, str]]:
        """Expand top-level nodes, read children, filter by query."""
        tree = session.find_by_id(_SPRO_TREE_ID)
        raw: Any = getattr(tree, "com", getattr(tree, "_com", tree))

        keys = raw.GetAllNodeKeys()
        query_lower = query.lower()
        matches: list[dict[str, str]] = []

        # Expand all level-02 nodes to reveal level-03 children (activities)
        # Key format: 'LL  P      N' where LL is a 2-digit zero-padded level
        level2_keys: list[str] = []
        for i in range(keys.Count):
            k: str = keys(i)
            if k[:2] == "02":
                level2_keys.append(k)

        for k in level2_keys:
            try:
                raw.ExpandNode(k)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Re-read all nodes after expansion
        keys = raw.GetAllNodeKeys()
        # Build parent context map
        current_l2 = ""
        for i in range(keys.Count):
            k = keys(i)
            text: str = raw.GetItemText(k, "TEXT")
            level = k[:2]

            if level == "02":
                current_l2 = text
            if query_lower in text.lower() and level in ("02", "03"):
                matches.append(
                    {
                        "activity_name": text,
                        "parent_node": current_l2 if level == "03" else "SAP Customizing",
                        "area": current_l2,
                    }
                )

        return matches

    raw_matches = await com.run(_read_and_search, retry_server_fault=True)

    # Navigate back: F3 exits IMG tree, F3 exits SPRO
    await backend.press_key("F3")
    await backend.press_key("F3")

    activities = [SPROActivity(**m) for m in raw_matches]
    return SPROSearchResult(
        query=query,
        activities=activities,
        activity_count=len(activities),
        retrieved_at=now,
        scope_note=_DESKTOP_SCOPE_NOTE,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_spro_tools(mcp: FastMCP) -> None:
    """Register SPRO tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
        description=(
            "Search the SAP Implementation Guide (IMG) for customizing activities by keyword. "
            "USE THIS to find where specific SAP configuration is maintained (e.g., 'country', "
            "'pricing', 'tax'). Returns matching IMG activities with their parent node and area. "
            "The search covers only the top two levels of "
            "the IMG tree (the result's scope_note says so). Results can then be used to navigate to "
            "specific configuration via SM30 or other transactions.\n\n"
            "Note: the search expands the IMG tree, so it can take a while."
        ),
    )
    async def sap_spro_search(
        query: str,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SPROSearchResult | SPROFileSummary:
        """
        Search the SAP Implementation Guide (IMG) for customizing activities.

        Args:
            query: Search keyword (e.g., 'country', 'pricing', 'tax')
            output_file: If provided, write full results to this JSON file and return summary.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SPROSearchResult with matching activities (inline), or
            SPROFileSummary with file path and preview (when output_file provided)
        """
        now = datetime.now(UTC)

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_spro_search")
        except ValueError as e:
            return SPROSearchResult.failure(
                error=f"Session error: {e}",
                query=query,
                activities=[],
                activity_count=0,
                retrieved_at=now,
            )

        try:
            result = await _search_img_desktop(backend, query)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("SPRO desktop search query=%r", query)
            result = SPROSearchResult.failure(
                error=f"Error searching IMG for '{query}': {e}",
                query=query,
                activities=[],
                activity_count=0,
                retrieved_at=now,
            )

        # Write to file if requested
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SPROFileSummary(
                success=True,
                output_file=str(output_path.absolute()),
                query=result.query,
                activity_count=result.activity_count,
                sample_activities=result.activities[:5],
                retrieved_at=result.retrieved_at,
                scope_note=result.scope_note,
            )

        return result
