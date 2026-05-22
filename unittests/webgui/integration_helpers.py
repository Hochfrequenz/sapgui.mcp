"""Shared helpers for SAP integration tests.

Provides reusable functions for waiting on transaction screens,
capturing HTML snapshots, and other common test operations.
"""

import os
from pathlib import Path

from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import WaitResult

from .conftest import call_tool_typed, get_html_content

# HTML snapshot directory for offline selector tests
HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"


async def capture_html_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """
    Capture the current browser HTML and save it as a snapshot for unit tests.

    The filename will include the current SAP_LANGUAGE setting (e.g., "easy_access_en.html").
    This allows capturing snapshots in multiple languages for testing.

    Args:
        client: MCP ClientSession connected to the SAP Web GUI server
        base_name: Base name of the snapshot file without extension (e.g., "easy_access")
        overwrite: If True, overwrite existing snapshot. If False, skip if exists.

    Returns:
        The captured HTML content.
    """
    html_content = await get_html_content(client)

    # Include language in filename for multi-language snapshots
    language = os.environ.get("SAP_LANGUAGE", "EN").lower()
    filename = f"{base_name}_{language}.html"

    HTML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = HTML_SNAPSHOTS_DIR / filename

    if overwrite or not snapshot_path.exists():
        snapshot_path.write_text(html_content, encoding="utf-8")

    return html_content


# Transaction-specific selectors for wait conditions
# These selectors identify unique elements on each transaction's initial screen
_TRANSACTION_WAIT_SELECTORS: dict[str, str] = {
    "SE11": "[lsdata*='RSRD1-TBMA']",  # Database table radio button
    "SE16": "input[lsdata*='TABLENAME']",  # Table name input field
    "SE38": "label:has-text('Programm'), label:has-text('Program')",  # ABAP Editor program label
    "SE93": "input[lsdata*='TSTC-TCODE']",  # Transaction code input field
    "SM30": "input[title*='Table/View']",  # SM30 table maintenance - table name field
    "SM37": "input[lsdata*='JOBNAME']",  # Job name input field
    "SU3": "[lsdata*='SUID_ST_NODE']",  # User profile (SU3) fields - SUID_ST_NODE_PERSON_NAME etc.
    "BP": "span:has-text('Person'), span:has-text('Organisation')",  # BP category buttons
    "EMMACL": "input[type='text']",  # EMMACL has many input fields
}


async def _wait_for_transaction_screen(
    client: ClientSession,
    tcode: str,
    timeout: int = 5000,
) -> None:
    """
    Wait for a transaction's initial screen to load.

    Uses transaction-specific selectors to detect when the screen is ready.
    This is faster than fixed timeouts because it returns as soon as the
    expected element is found.

    Args:
        client: MCP ClientSession connected to the SAP Web GUI server
        tcode: Transaction code (e.g., "SE16", "SM37")
        timeout: Maximum wait time in milliseconds (default 5000)

    Raises:
        NotImplementedError: If the transaction code is not in _TRANSACTION_WAIT_SELECTORS
        RuntimeError: If the wait times out or fails
    """
    tcode_upper = tcode.upper()
    if tcode_upper not in _TRANSACTION_WAIT_SELECTORS:
        raise NotImplementedError(
            f"No wait selector defined for transaction '{tcode}'. "
            f"Known transactions: {', '.join(sorted(_TRANSACTION_WAIT_SELECTORS.keys()))}. "
            f"Add a selector to _TRANSACTION_WAIT_SELECTORS or use browser_wait directly."
        )

    selector = _TRANSACTION_WAIT_SELECTORS[tcode_upper]
    result = await call_tool_typed(client, "browser_wait", {"selector": selector, "timeout": timeout}, WaitResult)
    if not result.success:
        raise RuntimeError(f"Wait for {tcode} failed: {result.error}")


async def _wait_for_easy_access(client: ClientSession, timeout: int = 5000) -> None:
    """
    Wait for SAP Easy Access screen (main menu) to load.

    Used after pressing F3 (Back) or when returning from a transaction.

    Args:
        client: MCP ClientSession connected to the SAP Web GUI server
        timeout: Maximum wait time in milliseconds (default 5000)

    Raises:
        RuntimeError: If the wait times out or fails
    """
    result = await call_tool_typed(
        client, "browser_wait", {"selector": "#ToolbarOkCode", "timeout": timeout}, WaitResult
    )
    if not result.success:
        raise RuntimeError(f"Wait for Easy Access failed: {result.error}")
