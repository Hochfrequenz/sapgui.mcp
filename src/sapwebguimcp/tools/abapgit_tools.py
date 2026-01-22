"""
abapGit integration tools for SAP Web GUI.

This module provides tools for interacting with abapGit repositories:
- Pull: Fetch and apply changes from remote git repository
- Stage: Prepare local changes for commit/push

The abapGit UI runs inside an iframe within SAP Web GUI, requiring
JavaScript evaluation to interact with its elements.
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.abapgit_models import AbapGitActionResult
from sapwebguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_abapgit_tools"]

# Default transaction for abapGit
DEFAULT_TCODE = "ZABAPGIT"

# Wait times (ms)
UI_LOAD_WAIT = 3000  # Wait for abapGit UI to load in iframe
MENU_EXPAND_WAIT = 1000  # Wait for menu to expand
ACTION_WAIT = 5000  # Wait for action (pull/stage) to complete


# =============================================================================
# JavaScript Helpers for iframe interaction
# =============================================================================

JS_FIND_IFRAME = """
(() => {
    const iframeCandidates = [
        document.querySelector('iframe#C116'),
        document.querySelector('iframe[id^="C"]'),
        document.querySelector('iframe')
    ].filter(Boolean);

    for (const candidate of iframeCandidates) {
        try {
            const doc = candidate.contentDocument || candidate.contentWindow?.document;
            if (doc && doc.body?.innerText?.includes('Repository')) {
                return {found: true, id: candidate.id};
            }
        } catch (e) { /* ignore cross-origin */ }
    }
    return {found: false, error: 'No iframe with abapGit content found'};
})()
"""


def _js_find_repo_row(repo_pattern: str) -> str:
    """Generate JS to find a repo row by pattern (name, package, or remote URL)."""
    return f"""
    (() => {{
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {{
            try {{
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc && doc.body?.innerText?.includes('Repository')) {{
                    iframeDoc = doc;
                    break;
                }}
            }} catch (e) {{ /* ignore */ }}
        }}

        if (!iframeDoc) return JSON.stringify({{error: 'No iframe found'}});

        const pattern = {json.dumps(repo_pattern)}.toLowerCase();
        const allRows = Array.from(iframeDoc.querySelectorAll('tr'));
        const repoRow = allRows.find(tr => {{
            const text = (tr.innerText || '').toLowerCase();
            return text.includes(pattern);
        }});

        if (!repoRow) return JSON.stringify({{error: 'Repo not found: ' + pattern}});

        // Find menu arrow in this row
        const rowLinks = Array.from(repoRow.querySelectorAll('a'));
        const menuArrow = rowLinks.find(el =>
            el.innerText?.includes('▸') || el.innerText?.includes('►')
        );

        if (!menuArrow) return JSON.stringify({{error: 'No menu arrow in repo row'}});

        // Extract repo info
        const nameLink = rowLinks.find(a => a.innerText && !a.innerText.match(/[▸►]/));
        const repoName = nameLink?.innerText?.trim() || 'Unknown';

        return JSON.stringify({{
            found: true,
            repoName: repoName,
            hasMenuArrow: true
        }});
    }})()
    """


def _js_click_menu_arrow(repo_pattern: str) -> str:
    """Generate JS to click the menu arrow for a repo."""
    return f"""
    (() => {{
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {{
            try {{
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc && doc.body?.innerText?.includes('Repository')) {{
                    iframeDoc = doc;
                    break;
                }}
            }} catch (e) {{ /* ignore */ }}
        }}

        if (!iframeDoc) return JSON.stringify({{error: 'No iframe found'}});

        const pattern = {json.dumps(repo_pattern)}.toLowerCase();
        const allRows = Array.from(iframeDoc.querySelectorAll('tr'));
        const repoRow = allRows.find(tr => {{
            const text = (tr.innerText || '').toLowerCase();
            return text.includes(pattern);
        }});

        if (!repoRow) return JSON.stringify({{error: 'Repo not found'}});

        const rowLinks = Array.from(repoRow.querySelectorAll('a'));
        const menuArrow = rowLinks.find(el =>
            el.innerText?.includes('▸') || el.innerText?.includes('►')
        );

        if (!menuArrow) return JSON.stringify({{error: 'No menu arrow found'}});

        menuArrow.click();
        return JSON.stringify({{clicked: true}});
    }})()
    """


def _js_click_action(action: str) -> str:
    """Generate JS to click an action link (Pull, Stage, etc.) from expanded menu."""
    return f"""
    (() => {{
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        let iframeDoc = null;
        for (const candidate of iframeCandidates) {{
            try {{
                const doc = candidate.contentDocument || candidate.contentWindow?.document;
                if (doc) {{
                    iframeDoc = doc;
                    break;
                }}
            }} catch (e) {{ /* ignore */ }}
        }}

        if (!iframeDoc) return JSON.stringify({{error: 'No iframe found'}});

        const actionText = {json.dumps(action)};
        const allLinks = Array.from(iframeDoc.querySelectorAll('a'));
        const actionLink = allLinks.find(a =>
            a.innerText?.trim() === actionText && a.className?.includes('action_link')
        );

        if (!actionLink) {{
            const available = allLinks
                .filter(a => a.className?.includes('action_link'))
                .map(a => a.innerText?.trim())
                .slice(0, 10);
            return JSON.stringify({{
                error: 'Action link not found: ' + actionText,
                available: available
            }});
        }}

        actionLink.click();
        return JSON.stringify({{clicked: true, href: actionLink.href}});
    }})()
    """


JS_CHECK_LOGIN_DIALOG = """
(() => {
    const iframeCandidates = [
        document.querySelector('iframe#C116'),
        document.querySelector('iframe[id^="C"]'),
        document.querySelector('iframe')
    ].filter(Boolean);

    let iframeDoc = null;
    for (const candidate of iframeCandidates) {
        try {
            const doc = candidate.contentDocument || candidate.contentWindow?.document;
            if (doc) {
                iframeDoc = doc;
                break;
            }
        } catch (e) { /* ignore */ }
    }

    if (!iframeDoc) return JSON.stringify({error: 'No iframe found'});

    // Check for login dialog elements
    const bodyText = iframeDoc.body?.innerText || '';
    const hasLoginDialog = bodyText.includes('Password or Token') ||
                          bodyText.includes('github.com') ||
                          bodyText.includes('Login:');

    // Find password/token input field
    const inputs = Array.from(iframeDoc.querySelectorAll('input'));
    const tokenInput = inputs.find(i =>
        i.type === 'password' ||
        (i.previousElementSibling?.innerText?.toLowerCase().includes('token')) ||
        (i.previousElementSibling?.innerText?.toLowerCase().includes('password'))
    );

    // Also check for the SAP dialog in the main page accessibility tree
    // The login dialog appears outside the iframe in the SAP GUI structure
    const dialogCheck = document.querySelector('[role="dialog"]');
    const hasDialog = !!dialogCheck && dialogCheck.innerText?.includes('Login');

    return JSON.stringify({
        hasLoginDialog: hasLoginDialog || hasDialog,
        tokenInputId: tokenInput?.id || null,
        tokenInputName: tokenInput?.name || null,
        bodyPreview: bodyText.substring(0, 500)
    });
})()
"""


def _js_fill_token(token: str) -> str:
    """Generate JS to fill the token/password field."""
    return f"""
    (() => {{
        // The login dialog is in the SAP GUI layer, not iframe
        // Look for the password textbox by role
        const passwordBox = document.querySelector('input[type="password"]');
        if (passwordBox) {{
            passwordBox.value = {json.dumps(token)};
            passwordBox.dispatchEvent(new Event('input', {{ bubbles: true }}));
            return JSON.stringify({{filled: true, method: 'password_input'}});
        }}

        // Also try looking in iframe
        const iframeCandidates = [
            document.querySelector('iframe#C116'),
            document.querySelector('iframe[id^="C"]'),
            document.querySelector('iframe')
        ].filter(Boolean);

        for (const iframe of iframeCandidates) {{
            try {{
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (doc) {{
                    const iframePasswordBox = doc.querySelector('input[type="password"]');
                    if (iframePasswordBox) {{
                        iframePasswordBox.value = {json.dumps(token)};
                        iframePasswordBox.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        return JSON.stringify({{filled: true, method: 'iframe_password'}});
                    }}
                }}
            }} catch (e) {{ /* ignore */ }}
        }}

        return JSON.stringify({{filled: false, error: 'Password field not found'}});
    }})()
    """


# =============================================================================
# Core Implementation
# =============================================================================


async def _evaluate_js(page: Any, script: str) -> dict[str, Any]:
    """Evaluate JavaScript and parse result as JSON."""
    result = await page.evaluate(script)
    # Handle double-encoded JSON strings
    while isinstance(result, str):
        result = json.loads(result)
    return result


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
    now = datetime.now(UTC)
    action_lower = action.lower()

    # Get PAT from parameter or environment
    token = pat or os.environ.get("ABAPGIT_PAT") or os.environ.get("GITHUB_PAT")

    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()

    if page is None:
        return AbapGitActionResult(
            success=False,
            action=action_lower,
            repo_name=repo_pattern,
            error="No browser page available. Call sap_login first.",
            executed_at=now,
        )

    try:
        # Step 1: Navigate to abapGit transaction
        tx_result = await sap_transaction_impl(tcode, new_window=False)
        if not tx_result.success:
            return AbapGitActionResult(
                success=False,
                action=action_lower,
                repo_name=repo_pattern,
                error=f"Failed to open {tcode}: {tx_result.error}",
                executed_at=now,
            )

        # Wait for abapGit UI to load in iframe
        await page.wait_for_timeout(UI_LOAD_WAIT)

        # Step 2: Find the repo row
        find_result = await _evaluate_js(page, _js_find_repo_row(repo_pattern))
        if find_result.get("error"):
            return AbapGitActionResult(
                success=False,
                action=action_lower,
                repo_name=repo_pattern,
                error=find_result["error"],
                executed_at=now,
            )

        repo_name = find_result.get("repoName", repo_pattern)

        # Step 3: Click menu arrow to expand actions
        click_menu = await _evaluate_js(page, _js_click_menu_arrow(repo_pattern))
        if click_menu.get("error"):
            return AbapGitActionResult(
                success=False,
                action=action_lower,
                repo_name=repo_name,
                error=f"Failed to expand menu: {click_menu['error']}",
                executed_at=now,
            )

        await page.wait_for_timeout(MENU_EXPAND_WAIT)

        # Step 4: Click the action (Pull or Stage)
        click_action = await _evaluate_js(page, _js_click_action(action))
        if click_action.get("error"):
            return AbapGitActionResult(
                success=False,
                action=action_lower,
                repo_name=repo_name,
                error=f"Failed to click {action}: {click_action['error']}",
                executed_at=now,
            )

        await page.wait_for_timeout(ACTION_WAIT)

        # Step 5: Check for login dialog and fill token if needed
        login_check = await _evaluate_js(page, JS_CHECK_LOGIN_DIALOG)
        if login_check.get("hasLoginDialog"):
            if not token:
                return AbapGitActionResult(
                    success=False,
                    action=action_lower,
                    repo_name=repo_name,
                    error="Login dialog appeared but no PAT provided. "
                    "Set ABAPGIT_PAT env var or pass pat parameter.",
                    executed_at=now,
                )

            # Fill the token
            fill_result = await _evaluate_js(page, _js_fill_token(token))
            if not fill_result.get("filled"):
                return AbapGitActionResult(
                    success=False,
                    action=action_lower,
                    repo_name=repo_name,
                    error=f"Failed to fill token: {fill_result.get('error')}",
                    executed_at=now,
                )

            # Click "Weiter" (Continue) button - use keyboard Enter
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(ACTION_WAIT)

        # Success!
        return AbapGitActionResult(
            success=True,
            action=action_lower,
            repo_name=repo_name,
            message=f"{action} initiated for {repo_name}",
            executed_at=now,
        )

    except Exception as e:
        logger.exception(f"abapGit {action} failed")
        return AbapGitActionResult(
            success=False,
            action=action_lower,
            repo_name=repo_pattern,
            error=str(e),
            executed_at=now,
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
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
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
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
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
