"""
SE93 (Transaction Maintenance) lookup tool.

This module provides a tool to look up transaction metadata from SE93,
returning strongly-typed Pydantic models with transaction details.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.models import (
    SE93Entry,
    SE93Error,
    SE93FileSummary,
    SE93Result,
    get_browser_manager,
)
from sapwebguimcp.parsers.se93_parser import parse_se93_snapshot
from sapwebguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_se93_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 10


# =============================================================================
# SE93 Navigation Helpers
# =============================================================================


async def _find_tcode_field(page: Any) -> Any:
    """Find the transaction code input field in SE93 using multiple strategies."""
    # Build list of locator strategies to try in order
    strategies = [
        # Strategy 1: Try by role with exact name matches
        *[
            page.get_by_role("textbox", name=name)
            for name in ["Transaktionscode", "Transaction code", "Transaction Code"]
        ],
        # Strategy 2: Try regex pattern for transaction code field
        page.get_by_role("textbox", name=re.compile(r"Transaktion|Transaction", re.I)),
        # Strategy 3: Try by input title attribute (common in SAP Web GUI)
        page.locator("input[title*='Transaktionscode'], input[title*='Transaction code']").first,
        # Strategy 4: Try by placeholder or aria-label
        page.locator("[aria-label*='Transaktion'], [aria-label*='Transaction']").first,
        # Strategy 5: First visible input field on the page (last resort)
        page.locator("input:visible").first,
    ]

    for field in strategies:
        if await field.count() > 0:
            return field

    return None


async def _fill_tcode_field(page: Any, tcode: str) -> SE93Error | None:
    """Fill the transaction code field in SE93. Returns error or None."""
    now = datetime.now(UTC)

    tcode_field = await _find_tcode_field(page)

    if tcode_field is None or await tcode_field.count() == 0:
        return SE93Error(
            tcode=tcode,
            error="Could not find transaction code field in SE93",
            retrieved_at=now,
        )

    # Clear the field first by selecting all and deleting
    await tcode_field.click(click_count=3)
    await page.wait_for_timeout(100)
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(50)

    # Type the transaction code
    await page.keyboard.type(tcode.upper())
    await page.wait_for_timeout(100)
    return None


async def _click_display_button(page: Any) -> None:
    """Click the Display button (F7)."""
    await page.wait_for_timeout(300)
    await page.keyboard.press("F7")
    await page.wait_for_timeout(1000)  # Wait longer for SAP to process
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(500)  # Additional wait for page state to settle


async def _check_tcode_not_found(page: Any, tcode: str) -> SE93Error | None:
    """Check if transaction was not found by verifying page state. Returns error or None."""
    now = datetime.now(UTC)

    # Primary check: Are we still on the initial screen?
    # If we successfully displayed a transaction, the page title changes
    page_title = await page.title()
    is_initial_screen = "Transaktionspflege" in page_title or "Transaction Maintenance" in page_title

    if not is_initial_screen:
        # We're on a display screen, so the transaction was found
        return None

    # We're still on initial screen - check status bar for specific error message
    status_bar = page.locator("#sapStatusBarAll, [id*='STATUSBAR']").first
    status_text = await status_bar.text_content() if await status_bar.count() > 0 else ""

    not_found_msgs = {
        "existiert nicht",
        "does not exist",
        "nicht gefunden",
        "not found",
        "nicht vorhanden",
    }

    if status_text and any(msg in status_text.lower() for msg in not_found_msgs):
        error_msg = f"Transaction '{tcode}' not found"
    else:
        # Still on initial screen but no clear error
        error_msg = f"Transaction '{tcode}' not found (still on initial screen)"

    # Don't press F3 here - the next /nSE93 will handle navigation
    return SE93Error(
        tcode=tcode,
        error=error_msg,
        retrieved_at=now,
    )


async def _lookup_single_tcode(page: Any, tcode: str) -> SE93Entry | SE93Error:
    """Look up a single transaction code in SE93."""
    now = datetime.now(UTC)

    # Navigate to SE93
    await page.wait_for_timeout(300)
    tx_result = await sap_transaction_impl("SE93")
    if not tx_result.success:
        return SE93Error(
            tcode=tcode,
            error=f"Failed to navigate to SE93: {tx_result.error}",
            retrieved_at=now,
        )

    # Wait for SE93 screen to be ready
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

    # Try to find the transaction code field with multiple strategies
    tcode_field = await _find_tcode_field(page)
    if tcode_field is None or await tcode_field.count() == 0:
        page_title = await page.title()
        return SE93Error(
            tcode=tcode,
            error=f"SE93 screen did not load or field not found (page title: '{page_title}')",
            retrieved_at=now,
        )

    # Fill transaction code
    error = await _fill_tcode_field(page, tcode)
    if error:
        return error

    # Click display
    await _click_display_button(page)

    # Check for not found error
    error = await _check_tcode_not_found(page, tcode)
    if error:
        return error

    # Get and parse snapshot
    snapshot = await page.locator("body").aria_snapshot()
    logger.debug("Got snapshot", extra={"object": tcode, "length": len(snapshot)})

    return parse_se93_snapshot(snapshot, tcode)


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se93_tools(mcp: FastMCP) -> None:
    """Register SE93 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up transaction metadata from SE93 (Transaction Maintenance). "
            "USE THIS instead of sap_transaction('SE93') - faster and returns structured data. "
            "Returns transaction description, program, screen/selection info, and GUI capabilities. "
            "Supports single tcode or list of tcodes. "
            "Currently supports 'dialog' and 'report' transaction types."
        ),
    )
    async def sap_se93_lookup(
        tcodes: str | list[str],
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE93Result | SE93FileSummary:
        """
        Look up transaction metadata from SE93.

        Args:
            tcodes: Single transaction code or list of codes (e.g., 'VA01' or ['VA01', 'MM01'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >10 transactions to avoid context overflow.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE93Result with entries and errors (inline), or
            SE93FileSummary with file path and statistics (when output_file provided)
        """
        tcode_list = [tcodes] if isinstance(tcodes, str) else list(tcodes)

        if not tcode_list:
            return SE93Result.failure("No transaction codes provided")

        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_se93_lookup")
        except ValueError as e:
            return SE93Result.failure(f"Session error: {e}")

        entries: list[SE93Entry] = []
        errors: list[SE93Error] = []

        for tcode in tcode_list:
            try:
                result = await _lookup_single_tcode(page, tcode)
                if isinstance(result, SE93Entry):
                    entries.append(result)
                else:
                    errors.append(result)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Looking up in SE93", extra={"object": tcode})
                errors.append(
                    SE93Error(
                        tcode=tcode,
                        error=f"Error looking up '{tcode}': {e}",
                        retrieved_at=datetime.now(UTC),
                    )
                )

        # Build final result
        if entries:
            final_result = SE93Result(entries=entries, errors=errors)
        else:
            final_result = SE93Result.failure(
                error=f"All {len(errors)} lookups failed",
                entries=[],
                errors=errors,
            )

        # Write to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(final_result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SE93FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(tcode_list),
                successful=len(entries),
                failed=len(errors),
                sample_entries=[e.tcode for e in entries[:5]],
                sample_errors=[e.tcode for e in errors[:5]],
            )

        if len(tcode_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning transactions inline - consider using output_file parameter",
                extra={"count": len(tcode_list)},
            )

        return final_result
