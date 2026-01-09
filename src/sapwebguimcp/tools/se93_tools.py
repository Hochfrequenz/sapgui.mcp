"""
SE93 (Transaction Maintenance) lookup tool.

This module provides a tool to look up transaction metadata from SE93,
returning strongly-typed Pydantic models with transaction details.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import TimeoutError as PlaywrightTimeout

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


async def _fill_tcode_field(page: Any, tcode: str) -> SE93Error | None:
    """Fill the transaction code field in SE93. Returns error or None."""
    now = datetime.now(UTC)

    # Try German label first, then English
    tcode_field = page.get_by_role("textbox", name="Transaktionscode")
    if await tcode_field.count() == 0:
        tcode_field = page.get_by_role("textbox", name="Transaction code")

    if await tcode_field.count() == 0:
        return SE93Error(
            tcode=tcode,
            error="Could not find transaction code field in SE93",
            retrieved_at=now,
        )

    await tcode_field.click(click_count=3)
    await page.wait_for_timeout(50)
    await page.keyboard.type(tcode.upper())
    return None


async def _click_display_button(page: Any) -> None:
    """Click the Display button (F7)."""
    await page.wait_for_timeout(300)
    await page.keyboard.press("F7")
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")


async def _check_tcode_not_found(page: Any, tcode: str) -> SE93Error | None:
    """Check if status bar shows transaction not found. Returns error or None."""
    now = datetime.now(UTC)
    status_bar = page.locator("#sapStatusBarAll, [id*='STATUSBAR']").first
    status_text = await status_bar.text_content() if await status_bar.count() > 0 else ""

    not_found_msgs = {"existiert nicht", "does not exist", "nicht gefunden", "not found", "nicht vorhanden"}
    if status_text and any(msg in status_text.lower() for msg in not_found_msgs):
        await page.keyboard.press("F3")
        await page.wait_for_load_state("networkidle")
        return SE93Error(
            tcode=tcode,
            error=f"Transaction '{tcode}' not found",
            retrieved_at=now,
        )

    return None


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

    # Wait for SE93 screen
    try:
        tcode_field = page.get_by_role("textbox", name="Transaktionscode")
        if await tcode_field.count() == 0:
            tcode_field = page.get_by_role("textbox", name="Transaction code")
        await tcode_field.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        page_title = await page.title()
        return SE93Error(
            tcode=tcode,
            error=f"SE93 screen did not load (page title: '{page_title}')",
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
    logger.debug("SE93: Got snapshot for %s, length: %d chars", tcode, len(snapshot))

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
            "Returns transaction description, program, screen/selection info, and GUI capabilities. "
            "Supports single tcode or list of tcodes. "
            "Currently supports 'dialog' and 'report' transaction types."
        ),
    )
    async def sap_se93_lookup(
        tcodes: str | list[str],
        output_file: str | None = None,
    ) -> SE93Result | SE93FileSummary:
        """
        Look up transaction metadata from SE93.

        Args:
            tcodes: Single transaction code or list of codes (e.g., 'VA01' or ['VA01', 'MM01'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >10 transactions to avoid context overflow.

        Returns:
            SE93Result with entries and errors (inline), or
            SE93FileSummary with file path and statistics (when output_file provided)
        """
        tcode_list = [tcodes] if isinstance(tcodes, str) else list(tcodes)

        if not tcode_list:
            return SE93Result.failure("No transaction codes provided")

        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

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
                logger.exception("Error looking up %s in SE93", tcode)
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
                "Returning %d transactions inline - consider using output_file parameter",
                len(tcode_list),
            )

        return final_result
