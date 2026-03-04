"""
SE93 (Transaction Maintenance) lookup tool.

This module provides a tool to look up transaction metadata from SE93,
returning strongly-typed Pydantic models with transaction details.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.protocol import SapUiBackend
from sapwebguimcp.models import (
    SE93Entry,
    SE93Error,
    SE93FileSummary,
    SE93Result,
)
from sapwebguimcp.parsers.se93_parser import parse_se93_snapshot

logger = logging.getLogger(__name__)

__all__ = ["register_se93_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 10


# =============================================================================
# SE93 Navigation Helpers
# =============================================================================


async def _fill_tcode_field(backend: SapUiBackend, tcode: str) -> SE93Error | None:
    """Fill the transaction code field in SE93. Returns error or None."""
    now = datetime.now(UTC)

    # Try multiple label variants (DE and EN)
    labels = [
        "Transaktionscode",
        "Transaction code",
        "Transaction Code",
    ]

    for label in labels:
        try:
            await backend.fill_field(label, tcode.upper())
            return None
        except ValueError:  # pylint: disable=broad-exception-caught
            continue

    return SE93Error(
        tcode=tcode,
        error="Could not find transaction code field in SE93",
        retrieved_at=now,
    )


async def _check_tcode_not_found(backend: SapUiBackend, tcode: str) -> SE93Error | None:
    """Check if transaction was not found by examining the snapshot. Returns error or None."""
    now = datetime.now(UTC)

    snapshot = await backend.get_snapshot()
    snapshot_lower = str(snapshot).lower()

    # Check if we're still on the initial screen
    is_initial_screen = "transaktionspflege" in snapshot_lower or "transaction maintenance" in snapshot_lower

    if not is_initial_screen:
        # We're on a display screen, so the transaction was found
        return None

    # Check for "not found" error messages
    not_found_msgs = {
        "existiert nicht",
        "does not exist",
        "nicht gefunden",
        "not found",
        "nicht vorhanden",
    }

    if any(msg in snapshot_lower for msg in not_found_msgs):
        error_msg = f"Transaction '{tcode}' not found"
    else:
        error_msg = f"Transaction '{tcode}' not found (still on initial screen)"

    return SE93Error(
        tcode=tcode,
        error=error_msg,
        retrieved_at=now,
    )


async def _lookup_single_tcode(backend: SapUiBackend, tcode: str) -> SE93Entry | SE93Error:
    """Look up a single transaction code in SE93."""
    now = datetime.now(UTC)

    # Navigate to SE93
    tx_result = await backend.enter_transaction("SE93")
    if not tx_result.success:
        return SE93Error(
            tcode=tcode,
            error=f"Failed to navigate to SE93: {tx_result.error}",
            retrieved_at=now,
        )

    # Wait for SE93 screen to be ready
    await backend.wait_for_ready()

    # Fill transaction code
    error = await _fill_tcode_field(backend, tcode)
    if error:
        return error

    # Click display (F7)
    await backend.press_key("F7")
    await backend.wait_for_ready()

    # Check for not found error
    error = await _check_tcode_not_found(backend, tcode)
    if error:
        return error

    # Get and parse snapshot
    snapshot = await backend.get_snapshot()
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

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se93_lookup")
        except ValueError as e:
            return SE93Result.failure(f"Session error: {e}")

        entries: list[SE93Entry] = []
        errors: list[SE93Error] = []

        for tcode in tcode_list:
            try:
                result = await _lookup_single_tcode(backend, tcode)
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
