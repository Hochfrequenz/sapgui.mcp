"""
SE09 (Transport Organizer) lookup tool.

This module provides a read-only tool to list transport requests from SE09.
The tool navigates to SE09, applies filters, clicks Anzeigen (Display),
and parses the flat text list from the ARIA snapshot.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.se09_models import TransportListResult
from sapwebguimcp.parsers.se09_parser import parse_se09_transport_list
from sapwebguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_se09_tools"]


# =============================================================================
# SE09 Navigation Helpers
# =============================================================================


async def _fill_user_field(page: Any, username: str) -> None:
    """Fill the username filter field in SE09."""
    user_field = page.get_by_role("textbox", name=re.compile(r"Benutzer|User", re.I))
    if await user_field.count() > 0:
        await user_field.click(click_count=3)
        await page.wait_for_timeout(100)
        await page.keyboard.press("Delete")
        await page.wait_for_timeout(50)
        await page.keyboard.type(username.upper())
        await page.wait_for_timeout(100)


async def _safe_checkbox_click(page: Any, checkbox: Any, should_be_checked: bool) -> None:
    """Safely click a checkbox if it's enabled and in the wrong state."""
    if await checkbox.count() == 0:
        return
    is_disabled = await checkbox.get_attribute("aria-disabled")
    if is_disabled == "true":
        logger.warning("Checkbox is disabled, skipping click")
        return
    try:
        is_checked = await checkbox.is_checked()
        if is_checked != should_be_checked:
            await checkbox.click()
            await page.wait_for_timeout(200)
    except Exception:
        logger.warning("Failed to click checkbox, skipping")


async def _set_request_type_filter(page: Any, request_type: str) -> None:
    """Set request type checkboxes on SE09 selection screen."""
    if request_type == "all":
        return  # Both already checked by default

    wb_cb = page.get_by_role("checkbox", name=re.compile(r"Workbench", re.I))
    cust_cb = page.get_by_role("checkbox", name=re.compile(r"Customizing", re.I))

    if request_type == "workbench":
        await _safe_checkbox_click(page, cust_cb, should_be_checked=False)
    elif request_type == "customizing":
        await _safe_checkbox_click(page, wb_cb, should_be_checked=False)


async def _set_status_filter(page: Any, status: str) -> None:
    """Set status filter checkboxes on SE09 selection screen."""
    mod_cb = page.get_by_role("checkbox", name=re.compile(r"Änderbar|Modifiable", re.I))
    rel_cb = page.get_by_role("checkbox", name=re.compile(r"Freigegeben|Released", re.I))

    if status == "all":
        await _safe_checkbox_click(page, rel_cb, should_be_checked=True)
        await _safe_checkbox_click(page, mod_cb, should_be_checked=True)
    elif status == "modifiable":
        await _safe_checkbox_click(page, mod_cb, should_be_checked=True)
        await _safe_checkbox_click(page, rel_cb, should_be_checked=False)
    elif status == "released":
        await _safe_checkbox_click(page, rel_cb, should_be_checked=True)
        await _safe_checkbox_click(page, mod_cb, should_be_checked=False)


async def _click_anzeigen_button(page: Any) -> None:
    """Click the Anzeigen/Display button to execute the search."""
    # Try Anzeigen (DE) first, then Display (EN)
    btn = page.get_by_role("button", name=re.compile(r"^Anzeigen$|^Display$", re.I))
    if await btn.count() > 0:
        await btn.click()
    else:
        # Fallback: try F8
        logger.warning("Anzeigen/Display button not found, trying F8")
        await page.keyboard.press("F8")

    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(500)


async def _lookup_transports(
    page: Any,
    username: str | None,
    request_type: str,
    status: str,
    include_objects: bool,
) -> TransportListResult:
    """Look up transports in SE09."""
    now = datetime.now(UTC)

    # Navigate to SE09
    tx_result = await sap_transaction_impl("SE09")
    if not tx_result.success:
        return TransportListResult.failure(
            error=f"Failed to navigate to SE09: {tx_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

    # Apply filters on selection screen
    if username is not None:
        await _fill_user_field(page, username)

    await _set_request_type_filter(page, request_type)
    await _set_status_filter(page, status)

    # Click Anzeigen button
    await _click_anzeigen_button(page)

    # Capture snapshot
    snapshot: str = await page.locator("body").aria_snapshot()

    # Parse the transport list
    result = parse_se09_transport_list(snapshot, include_objects=include_objects)
    return result


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se09_tools(mcp: FastMCP) -> None:
    """Register SE09 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up transport requests from SE09 (Transport Organizer). "
            "USE THIS instead of sap_transaction('SE09') - faster and returns structured data. "
            "Returns transport requests with owner, description, status, type, and target system. "
            "By default shows only modifiable requests for the current user. "
            "Supports filtering by username, request type (workbench/customizing), and status "
            "(modifiable/released/all)."
        ),
    )
    async def sap_se09_lookup(
        username: str | None = None,
        request_type: Literal["workbench", "customizing", "all"] = "all",
        status: Literal["modifiable", "released", "all"] = "modifiable",
        include_objects: bool = False,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TransportListResult:
        """
        Look up transport requests from SE09.

        Args:
            username: Filter by owner (default: current SAP user)
            request_type: Filter by type - "workbench", "customizing", or "all"
            status: Filter by status - "modifiable", "released", or "all" (default: "modifiable")
            include_objects: Not yet supported in v1 (reserved for future)
            output_file: Write results to JSON file if provided
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TransportListResult with requests
        """
        now = datetime.now(UTC)

        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_se09_lookup")
        except ValueError as e:
            return TransportListResult.failure(
                error=f"Session error: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        try:
            result = await _lookup_transports(
                page=page,
                username=username,
                request_type=request_type,
                status=status,
                include_objects=include_objects,
            )
        except Exception as e:
            logger.exception("Error looking up transports in SE09")
            return TransportListResult.failure(
                error=f"Error looking up transports: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        # Write to file if requested
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        return result
