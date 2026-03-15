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
from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.backend.webgui.parsers.se93_parser import parse_se93_snapshot
from sapwebguimcp.models import (
    SE93Entry,
    SE93Error,
    SE93FileSummary,
    SE93Result,
)
from sapwebguimcp.tools._backend_utils import _is_desktop_backend
from sapwebguimcp.tools.field_helpers import fill_and_display

logger = logging.getLogger(__name__)

__all__ = ["register_se93_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 10


# =============================================================================
# SE93 Navigation Helpers
# =============================================================================


# DE/EN label variants for the transaction code input field.
_TCODE_FIELD_LABELS = [
    "Transaktionscode",
    "Transaction code",
    "Transaction Code",
]


async def _lookup_tcode_on_initial_screen(backend: SapUiBackend, tcode: str) -> SE93Entry | SE93Error:
    """Look up a transaction code assuming we're already on the SE93 initial screen.

    The caller handles navigation (``enter_transaction``) and state reset
    (``/n`` between lookups) to prevent state bleeding in batch mode.
    """
    # Ensure the SE93 screen is fully loaded before interacting.
    await backend.wait_for_ready()

    # Fill field with real keyboard events, press F7, and verify navigation.
    error_msg = await fill_and_display(backend, _TCODE_FIELD_LABELS, tcode, tcode_label="transaction")
    if error_msg:
        return SE93Error(
            tcode=tcode,
            error=error_msg,
            retrieved_at=datetime.now(UTC),
        )

    # Get and parse snapshot
    snapshot = AriaSnapshot(await backend.get_snapshot())
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

        # Desktop backend: not yet supported
        if _is_desktop_backend(backend):
            return SE93Result.failure("SE93 lookup is not yet supported on the desktop backend")

        entries: list[SE93Entry] = []
        errors: list[SE93Error] = []

        for tcode in tcode_list:
            # Navigate to Easy Access first to ensure a clean starting state,
            # then open SE93.  This prevents state bleeding between lookups.
            await backend.enter_transaction("/n")
            await backend.wait_for_ready()

            tx_result = await backend.enter_transaction("SE93")
            if not tx_result.success:
                errors.append(
                    SE93Error(
                        tcode=tcode,
                        error=f"Failed to navigate to SE93: {tx_result.error}",
                        retrieved_at=datetime.now(UTC),
                    )
                )
                continue
            await backend.wait_for_ready()

            try:
                result = await _lookup_tcode_on_initial_screen(backend, tcode)
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
