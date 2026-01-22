"""
abapGit integration tools for SAP Web GUI.

This module provides tools for interacting with abapGit repositories:
- Pull: Fetch and apply changes from remote git repository
- Stage: Prepare local changes for commit/push

The abapGit UI runs inside an iframe within SAP Web GUI, requiring
JavaScript evaluation to interact with its elements.
"""

import logging
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import Page

from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.abapgit_models import AbapGitActionResult
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.tools.sap_tool_impl import sap_read_status_bar_impl, sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_abapgit_tools"]

# =============================================================================
# Constants
# =============================================================================

DEFAULT_TCODE = "ZABAPGIT"

# Wait times (ms) - used as fallback when condition-based waiting isn't possible
UI_LOAD_WAIT = 5000  # Wait for abapGit UI to load in iframe (increased for reliability)
MENU_EXPAND_WAIT = 2000  # Wait for menu to expand (increased for reliability)
ACTION_WAIT = 5000  # Wait for action to complete initially
PULL_COMPLETE_WAIT = 30000  # Max wait for pull to complete

# Retry configuration
MAX_IFRAME_RETRIES = 5  # Increased retries for slow connections
RETRY_DELAY_MS = 1500  # Increased delay between retries

# =============================================================================
# JavaScript Loading
# =============================================================================

_JS_DIR = Path(__file__).parent.parent / "js"


def _load_abapgit_js() -> str:
    """Load the abapGit iframe utilities JavaScript."""
    js_path = _JS_DIR / "abapgit_iframe.js"
    return js_path.read_text(encoding="utf-8")


# Load JS once at module level
_ABAPGIT_JS = _load_abapgit_js()


def _js_call(func_name: str, *args: Any) -> str:
    """
    Generate JavaScript that loads utilities and calls a function.

    Args:
        func_name: Name of the function to call (from abapgit_iframe.js)
        args: Arguments to pass (will be JSON-encoded)

    Returns:
        Complete JavaScript code to execute
    """
    import json

    args_str = ", ".join(json.dumps(arg) for arg in args) if args else ""
    return f"""
    (() => {{
        {_ABAPGIT_JS}
        return {func_name}({args_str});
    }})()
    """


# =============================================================================
# Core Implementation
# =============================================================================


async def _evaluate_js(page: Page, script: str) -> dict[str, Any]:
    """
    Evaluate JavaScript and return result.

    Args:
        page: Playwright page object
        script: JavaScript code to execute

    Returns:
        Parsed result as dictionary
    """
    import json

    result = await page.evaluate(script)
    # Handle single level of JSON encoding from legacy scripts
    if isinstance(result, str):
        result = json.loads(result)
    return result


async def _fill_token_secure(page: Page, token: str) -> dict[str, Any]:
    """
    Fill the token field securely using Playwright argument passing.

    This avoids embedding the token in JavaScript strings where it could
    appear in error traces or browser console logs.

    Args:
        page: Playwright page object
        token: The PAT token to fill

    Returns:
        Result dict with filled, method, error fields
    """
    # Use Playwright's evaluate with argument to avoid embedding token in JS
    return await page.evaluate(
        f"""
        (token) => {{
            {_ABAPGIT_JS}
            return fillToken(token);
        }}
        """,
        token,
    )


async def _find_iframe_with_retry(
    page: Page, max_retries: int = MAX_IFRAME_RETRIES
) -> dict[str, Any]:
    """
    Find abapGit iframe with retries for robustness.

    Args:
        page: Playwright page object
        max_retries: Maximum number of retry attempts

    Returns:
        Result dict with found, id, error fields
    """
    for attempt in range(max_retries):
        result = await _evaluate_js(page, _js_call("findAbapGitIframe"))
        if result.get("found"):
            return result
        # Exponential backoff: 1s, 2s, 3s
        await page.wait_for_timeout(RETRY_DELAY_MS * (attempt + 1))
        logger.debug(f"Iframe not found, retry {attempt + 1}/{max_retries}")

    return result  # Return last failure


async def _abapgit_action_impl(
    repo_pattern: str,
    action: Literal["Pull", "Stage"],
    pat: str | None,
    tcode: str,
) -> AbapGitActionResult:
    """
    Core implementation for abapGit pull/stage actions.

    Args:
        repo_pattern: Pattern to match repo (name, package, or remote URL)
        action: Action to perform ("Pull" or "Stage")
        pat: GitHub Personal Access Token (optional, falls back to env var)
        tcode: Transaction code (default: ZABAPGIT)

    Returns:
        AbapGitActionResult with success status and details
    """
    action_lower: Literal["pull", "stage"] = action.lower()  # type: ignore[assignment]

    # Get PAT from parameter or settings (which reads from .env / environment)
    settings = get_settings()
    token = pat or settings.abapgit_pat or settings.github_pat
    logger.info(f"Starting abapGit {action} for repo pattern: {repo_pattern}")

    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()

    if page is None:
        return AbapGitActionResult.failure_result(
            action_lower,
            repo_pattern,
            "No browser page available. Call sap_login first.",
        )

    try:
        # Step 1: Navigate to abapGit transaction
        tx_result = await sap_transaction_impl(tcode, new_window=False)
        if not tx_result.success:
            return AbapGitActionResult.failure_result(
                action_lower,
                repo_pattern,
                f"Failed to open {tcode}: {tx_result.error}",
            )

        # Wait for abapGit UI to load in iframe
        await page.wait_for_timeout(UI_LOAD_WAIT)

        # Step 2: Find iframe with retry
        iframe_result = await _find_iframe_with_retry(page)
        if not iframe_result.get("found"):
            return AbapGitActionResult.failure_result(
                action_lower,
                repo_pattern,
                f"abapGit iframe not found: {iframe_result.get('error')}",
            )

        # Step 3: Clear any existing filter to ensure we can find all repos
        clear_result = await _evaluate_js(page, _js_call("clearFilter"))
        if clear_result.get("cleared") and not clear_result.get("wasEmpty"):
            # Filter was cleared, wait for page to refresh
            await page.wait_for_timeout(UI_LOAD_WAIT)
            logger.info(f"Cleared filter: {clear_result}")

        # Step 4: Find the repo row
        find_result = await _evaluate_js(page, _js_call("findRepoRow", repo_pattern))
        if find_result.get("error"):
            logger.warning(f"Repo not found: {find_result}")
            return AbapGitActionResult.failure_result(
                action_lower,
                repo_pattern,
                find_result["error"],
            )

        repo_name = find_result.get("repoName", repo_pattern)
        logger.info(f"Found repo: {repo_name}")

        # Step 5: Click menu arrow to expand actions
        click_menu = await _evaluate_js(page, _js_call("clickMenuArrow", repo_pattern))
        if click_menu.get("error"):
            logger.warning(f"Failed to click menu arrow: {click_menu}")
            return AbapGitActionResult.failure_result(
                action_lower,
                repo_name,
                f"Failed to expand menu: {click_menu['error']}",
            )

        logger.info(f"Clicked menu arrow, waiting for menu to expand...")
        await page.wait_for_timeout(MENU_EXPAND_WAIT)

        # Step 6: Click the action (Pull or Stage)
        click_action = await _evaluate_js(page, _js_call("clickAction", action))
        if click_action.get("error"):
            available = click_action.get("available", [])
            searched = click_action.get("searchedFor", [action])
            logger.warning(
                f"Failed to click {action}. Searched for: {searched}. "
                f"Available actions: {available}"
            )
            return AbapGitActionResult.failure_result(
                action_lower,
                repo_name,
                f"Failed to click {action}: {click_action['error']}. Available: {available}",
            )
        logger.info(f"Clicked action: {click_action.get('clickedText', action)}")

        await page.wait_for_timeout(ACTION_WAIT)

        # Step 7: Check for login dialog and fill token if needed
        login_check = await _evaluate_js(page, _js_call("checkLoginDialog"))
        logger.debug(f"Login dialog check result: {login_check}")

        if login_check.get("hasLoginDialog"):
            logger.info(
                f"Login dialog detected at: {login_check.get('location', 'unknown')}"
            )
            if not token:
                return AbapGitActionResult.failure_result(
                    action_lower,
                    repo_name,
                    "Login dialog appeared but no PAT provided. "
                    "Set ABAPGIT_PAT env var or pass pat parameter.",
                )

            # Fill the token securely (via Playwright argument, not JS string)
            logger.info("Filling authentication token...")
            fill_result = await _fill_token_secure(page, token)
            logger.info(
                f"Token fill result: filled={fill_result.get('filled')}, "
                f"method={fill_result.get('method')}, "
                f"inputType={fill_result.get('inputType')}, "
                f"inputId={fill_result.get('inputId')}"
            )

            if not fill_result.get("filled"):
                return AbapGitActionResult.failure_result(
                    action_lower,
                    repo_name,
                    f"Failed to fill token: {fill_result.get('error')}",
                )

            # Click "Weiter" (Continue) button - use keyboard Enter
            logger.info("Pressing Enter to submit login...")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(ACTION_WAIT)
        else:
            logger.debug("No login dialog detected - proceeding without authentication")

        # Step 8: Verify action result (for Pull)
        if action == "Pull":
            # Wait for pull to complete
            await page.wait_for_timeout(ACTION_WAIT)

            # Read status bar for verification
            status_bar = await sap_read_status_bar_impl()
            status_message = status_bar.message or ""
            logger.info(f"Status bar after pull: type={status_bar.type}, message={status_message}")

            # Check for success indicators in status bar
            # Success: "Serialize: 2 objects, 0.02 seconds"
            # Also: "Pull successful", "objects imported", "up to date"
            success_patterns = [
                r"serialize.*\d+\s*objects",  # "Serialize: 2 objects, 0.02 seconds"
                r"pull.*success",
                r"objects?\s+imported",
                r"up\s+to\s+date",
                r"nothing\s+to\s+pull",
            ]

            import re
            is_success = any(
                re.search(pattern, status_message, re.IGNORECASE)
                for pattern in success_patterns
            )

            if is_success:
                return AbapGitActionResult.success_result(
                    action_lower,
                    repo_name,
                    f"{action} completed: {status_message}",
                )

            # Check for error indicators
            if status_bar.type == "error":
                return AbapGitActionResult.failure_result(
                    action_lower,
                    repo_name,
                    f"Pull failed: {status_message}",
                )

            # Also check iframe for errors
            verify_result = await _evaluate_js(page, _js_call("checkActionResult"))
            if verify_result.get("hasError"):
                error_msg = verify_result.get("message") or status_message or "Pull operation failed"
                return AbapGitActionResult.failure_result(
                    action_lower,
                    repo_name,
                    error_msg,
                )

            # No clear success or error - report status bar message
            return AbapGitActionResult.success_result(
                action_lower,
                repo_name,
                f"{action} completed for {repo_name}. Status: {status_message or 'unknown'}",
            )

        # For Stage action, just return success (user will interact with staging UI)
        return AbapGitActionResult.success_result(
            action_lower,
            repo_name,
            f"{action} view opened for {repo_name}",
        )

    except Exception as e:
        logger.exception(f"abapGit {action} failed")
        return AbapGitActionResult.failure_result(
            action_lower,
            repo_pattern,
            str(e),
        )


# =============================================================================
# Tool Registration
# =============================================================================


def register_abapgit_tools(mcp: FastMCP) -> None:
    """Register abapGit tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="abapGit Pull",
            readOnlyHint=False,
            destructiveHint=True,  # Pull overwrites local ABAP objects
            idempotentHint=True,
            openWorldHint=True,
        ),
        description=(
            "Pull changes from a remote git repository using abapGit. "
            "Navigates to ZABAPGIT, finds the repository, and initiates a pull. "
            "WARNING: This overwrites local ABAP objects with remote versions."
        ),
    )
    async def sap_abapgit_pull(
        repo: str,
        pat: str | None = None,
        tcode: str = DEFAULT_TCODE,
    ) -> AbapGitActionResult:
        """
        Pull changes from a remote git repository using abapGit.

        This tool navigates to abapGit, finds the specified repository,
        and initiates a pull operation. If authentication is required,
        it uses the provided PAT (Personal Access Token).

        WARNING: Pull overwrites local ABAP objects with remote versions.
        This is a destructive operation.

        Args:
            repo: Repository name, package, or remote URL pattern to match
            pat: GitHub Personal Access Token (optional - falls back to
                 ABAPGIT_PAT or GITHUB_PAT environment variables)
            tcode: Transaction code (default: ZABAPGIT)

        Returns:
            AbapGitActionResult with success status and details

        Example:
            # Pull by repo name
            sap_abapgit_pull(repo="BO4E")

            # Pull with explicit PAT
            sap_abapgit_pull(repo="hfqbo4e", pat="ghp_xxx...")

            # Pull by package name
            sap_abapgit_pull(repo="/HFQ/BO4E")
        """
        return await _abapgit_action_impl(repo, "Pull", pat, tcode)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="abapGit Stage",
            readOnlyHint=False,
            destructiveHint=False,  # Stage only opens view, does not modify
            idempotentHint=True,
            openWorldHint=True,
        ),
        description=(
            "Navigate to the staging area for an abapGit repository. "
            "Opens the staging view where you can select changes to commit/push."
        ),
    )
    async def sap_abapgit_stage(
        repo: str,
        pat: str | None = None,
        tcode: str = DEFAULT_TCODE,
    ) -> AbapGitActionResult:
        """
        Navigate to the staging area for an abapGit repository.

        This tool navigates to abapGit, finds the specified repository,
        and opens the staging view where you can select changes to commit/push.

        Note: This initiates the staging process but does not complete the push.
        You'll need to interact with the staging UI to select files and commit.

        Args:
            repo: Repository name, package, or remote URL pattern to match
            pat: GitHub Personal Access Token (optional - falls back to
                 ABAPGIT_PAT or GITHUB_PAT environment variables)
            tcode: Transaction code (default: ZABAPGIT)

        Returns:
            AbapGitActionResult with success status and details

        Example:
            # Stage by repo name
            sap_abapgit_stage(repo="BO4E")
        """
        return await _abapgit_action_impl(repo, "Stage", pat, tcode)
