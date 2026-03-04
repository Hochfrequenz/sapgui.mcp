"""
SE09 (Transport Organizer) lookup tool.

This module provides a read-only tool to list transport requests from SE09.
The tool navigates to SE09, applies filters, clicks Anzeigen (Display),
and parses the flat text list from the ARIA snapshot.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.lang import (
    SE09_DISPLAY_BUTTON_DE,
    SE09_DISPLAY_BUTTON_EN,
    SE09_MODIFIABLE_DE,
    SE09_MODIFIABLE_EN,
    SE09_RELEASED_DE,
    SE09_RELEASED_EN,
    SE09_USER_FIELD_DE,
    SE09_USER_FIELD_EN,
)
from sapwebguimcp.models.se09_models import TransportListResult
from sapwebguimcp.parsers.se09_parser import parse_se09_transport_list

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

__all__ = ["register_se09_tools"]


# =============================================================================
# SE09 Navigation Helpers
# =============================================================================


async def _fill_user_field(backend: "SapUiBackend", username: str) -> None:
    """Fill the username filter field in SE09."""
    for label in [SE09_USER_FIELD_DE, SE09_USER_FIELD_EN]:
        try:
            await backend.fill_field(label, username.upper())
            return
        except ValueError:
            continue
    logger.warning("User field not found in SE09 for any label")


async def _set_checkbox_state(backend: "SapUiBackend", label: str, should_be_checked: bool) -> None:
    """Safely set a checkbox to checked or unchecked state."""
    try:
        value = "X" if should_be_checked else ""
        await backend.fill_field(label, value)
    except (ValueError, Exception):  # pylint: disable=broad-exception-caught
        logger.warning("Failed to set checkbox '%s', skipping", label)


async def _set_request_type_filter(backend: "SapUiBackend", request_type: str) -> None:
    """Set request type checkboxes on SE09 selection screen."""
    if request_type == "all":
        return  # Both already checked by default

    if request_type == "workbench":
        await _set_checkbox_state(backend, "Customizing", False)
    elif request_type == "customizing":
        await _set_checkbox_state(backend, "Workbench", False)


async def _set_status_filter(backend: "SapUiBackend", status: str) -> None:  # pylint: disable=too-many-branches
    """Set status filter checkboxes on SE09 selection screen."""
    # Try DE labels first, then EN
    mod_labels = [SE09_MODIFIABLE_DE, SE09_MODIFIABLE_EN]
    rel_labels = [SE09_RELEASED_DE, SE09_RELEASED_EN]

    if status == "all":
        for label in rel_labels:
            try:
                await _set_checkbox_state(backend, label, True)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        for label in mod_labels:
            try:
                await _set_checkbox_state(backend, label, True)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
    elif status == "modifiable":
        for label in mod_labels:
            try:
                await _set_checkbox_state(backend, label, True)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        for label in rel_labels:
            try:
                await _set_checkbox_state(backend, label, False)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
    elif status == "released":
        for label in rel_labels:
            try:
                await _set_checkbox_state(backend, label, True)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        for label in mod_labels:
            try:
                await _set_checkbox_state(backend, label, False)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue


async def _click_display_button(backend: "SapUiBackend") -> None:
    """Click the Anzeigen/Display button to execute the search."""
    for label in [SE09_DISPLAY_BUTTON_DE, SE09_DISPLAY_BUTTON_EN]:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            return
        except ValueError:
            continue

    logger.warning("Anzeigen/Display button not found, trying F8")
    await backend.press_key("F8")
    await backend.wait_for_ready()


async def _lookup_transports(
    backend: "SapUiBackend",
    username: str | None,
    request_type: str,
    status: str,
) -> TransportListResult:
    """Look up transports in SE09."""
    now = datetime.now(UTC)

    # Navigate to SE09 using session-aware helper
    tx_result = await backend.enter_transaction("SE09")
    if not tx_result.success:
        return TransportListResult.failure(
            error=f"Failed to navigate to SE09: {tx_result.error}",
            requests=[],
            request_count=0,
            retrieved_at=now,
        )

    await backend.wait_for_ready()

    # Apply filters on selection screen
    if username is not None:
        await _fill_user_field(backend, username)

    await _set_request_type_filter(backend, request_type)
    await _set_status_filter(backend, status)

    # Click Anzeigen/Display button
    await _click_display_button(backend)

    # Capture snapshot
    snapshot: AriaSnapshot = await backend.get_snapshot()

    # Parse the transport list
    return parse_se09_transport_list(snapshot)


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
    async def sap_se09_lookup(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        username: str | None = None,
        request_type: Literal["workbench", "customizing", "all"] = "all",
        status: Literal["modifiable", "released", "all"] = "modifiable",
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
            output_file: If provided, write results to this JSON file (on success only).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TransportListResult with requests
        """
        now = datetime.now(UTC)

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se09_lookup")
        except ValueError as e:
            return TransportListResult.failure(
                error=f"Session error: {e}",
                requests=[],
                request_count=0,
                retrieved_at=now,
            )

        try:
            result = await _lookup_transports(
                backend=backend,
                username=username,
                request_type=request_type,
                status=status,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
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
