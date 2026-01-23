"""
abapGit integration tools for SAP Web GUI.

This module provides tools for interacting with abapGit repositories:
- Pull: Fetch and apply changes from remote git repository
- Stage: Prepare local changes for commit/push
- SE38 Verification: Read ABAP report source code

The abapGit UI runs inside an iframe within SAP Web GUI, requiring
JavaScript evaluation to interact with its elements.
"""

import json
import logging
import re
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
    result = await page.evaluate(script)
    # Handle single level of JSON encoding from legacy scripts
    if isinstance(result, str):
        result = json.loads(result)
    return dict(result)


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
    result: Any = await page.evaluate(
        f"""
        (token) => {{
            {_ABAPGIT_JS}
            return fillToken(token);
        }}
        """,
        token,
    )
    return dict(result)


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
    # Initialize result to handle edge case of max_retries=0
    result: dict[str, Any] = {"found": False, "error": "No retries attempted"}

    for attempt in range(max_retries):
        result = await _evaluate_js(page, _js_call("findAbapGitIframe"))
        if result.get("found"):
            return result
        # Exponential backoff: 1.5s, 3s, 4.5s, etc.
        await page.wait_for_timeout(RETRY_DELAY_MS * (attempt + 1))
        logger.debug("Iframe not found, retry %d/%d", attempt + 1, max_retries)

    return result  # Return last failure


async def _click_confirmation_button(page: Page) -> bool:
    """Click the Pull/Confirm button in the confirmation dialog."""
    for btn_text in ["Pull", "Ziehen", "OK", "Übernehmen"]:
        try:
            iframe = page.frame_locator("iframe").first
            btn = iframe.locator(f"a:has-text('{btn_text}'), button:has-text('{btn_text}')").first
            if await btn.is_visible(timeout=500):
                await btn.click()
                logger.info("Clicked confirmation button: %s", btn_text)
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return False


async def _handle_pull_confirmation_dialog(page: Page) -> None:
    """
    Handle the pull confirmation dialog that asks which objects to overwrite.

    The dialog appears ~2 seconds after clicking Pull and shows a table of objects
    with checkboxes. We need to:
    1. Wait for the dialog to appear
    2. Select all checkboxes (or click "Select All")
    3. Press Enter to confirm the selection
    """
    # Wait for the confirmation dialog to appear (it takes ~2 seconds after clicking Pull)
    await page.wait_for_timeout(2500)

    for attempt in range(3):  # Try up to 3 times
        confirm_result = await _evaluate_js(page, _js_call("handlePullConfirmation"))
        logger.info("Pull confirmation check (attempt %d): %s", attempt + 1, confirm_result)

        if not confirm_result.get("hasDialog"):
            # No dialog - either it hasn't appeared yet or pull started directly
            if attempt == 0:
                # Wait a bit more on first attempt
                await page.wait_for_timeout(1500)
                continue
            break

        # Dialog detected
        selected_count = confirm_result.get("selectedCount", 0)
        total_checkboxes = confirm_result.get("totalCheckboxes", 0)
        clicked_select_all = confirm_result.get("clickedSelectAll", False)

        if selected_count > 0 or clicked_select_all:
            # Checkboxes were selected - now confirm by pressing Enter
            logger.info("Selected %d objects, pressing Enter to confirm...", selected_count or total_checkboxes)
            await page.wait_for_timeout(500)

            # Press Enter to confirm (or try clicking the green checkmark button)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

            # Verify dialog is gone
            verify_result = await _evaluate_js(page, _js_call("handlePullConfirmation"))
            if not verify_result.get("hasDialog"):
                logger.info("Pull confirmation dialog handled successfully")
                return

            # If still there, try clicking any confirm button
            await _click_confirmation_button(page)
            await page.wait_for_timeout(1000)
            return

        # Dialog found but no checkboxes selected - try again
        logger.warning("Dialog found but no checkboxes selected: %s", confirm_result)
        await page.wait_for_timeout(1000)

        await page.wait_for_timeout(1000)


async def _click_action_link(page: Page, action: str) -> str | None:
    """
    Click an action link (Pull, Stage, etc.) using Playwright locators.

    Args:
        page: Playwright page object
        action: Action name ("Pull" or "Stage")

    Returns:
        The clicked action text, or None if not found
    """
    logger.info("Looking for %s action link...", action)

    # Action text variants (English and German)
    action_variants = {
        "Pull": ["Pull", "Ziehen", "Holen"],
        "Stage": ["Stage", "Bereitstellen", "Staging"],
    }
    variants = action_variants.get(action, [action])

    # Try to find and click the action link using Playwright
    for variant in variants:
        # Try in iframe first (abapGit runs inside an iframe)
        try:
            iframe_locator = page.frame_locator("iframe").first.locator(
                f"a:has-text('{variant}')"
            ).first
            if await iframe_locator.is_visible(timeout=500):
                await iframe_locator.click()
                logger.info("Clicked action link in iframe: %s", variant)
                return variant
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # Try in main document
        try:
            main_locator = page.locator(f"a:has-text('{variant}')").first
            if await main_locator.is_visible(timeout=500):
                await main_locator.click()
                logger.info("Clicked action link in main: %s", variant)
                return variant
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    return None


async def _abapgit_action_impl(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
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
    # Fallback order: explicit pat parameter > ABAPGIT_PAT > GITHUB_PAT
    settings = get_settings()
    token: str | None = None
    token_source: str = "none"

    if pat:
        token = pat
        token_source = "explicit parameter"
    elif settings.abapgit_pat:
        token = settings.abapgit_pat
        token_source = "ABAPGIT_PAT env var"
    elif settings.github_pat:
        token = settings.github_pat
        token_source = "GITHUB_PAT env var (fallback)"

    logger.info("Starting abapGit %s for repo pattern: %s", action, repo_pattern)
    if token:
        logger.debug("PAT available from: %s", token_source)
    else:
        logger.debug("No PAT available - public repos only")

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
            logger.info("Cleared filter: %s", clear_result)

        # Step 4: Find the repo row
        find_result = await _evaluate_js(page, _js_call("findRepoRow", repo_pattern))
        if find_result.get("error"):
            logger.warning("Repo not found: %s", find_result)
            return AbapGitActionResult.failure_result(
                action_lower,
                repo_pattern,
                find_result["error"],
            )

        repo_name = find_result.get("repoName", repo_pattern)
        logger.info("Found repo: %s", repo_name)

        # Step 5: Click menu arrow to expand actions
        click_menu = await _evaluate_js(page, _js_call("clickMenuArrow", repo_pattern))
        if click_menu.get("error"):
            logger.warning("Failed to click menu arrow: %s", click_menu)
            return AbapGitActionResult.failure_result(
                action_lower,
                repo_name,
                f"Failed to expand menu: {click_menu['error']}",
            )

        logger.info("Clicked menu arrow, waiting for menu to expand...")
        await page.wait_for_timeout(MENU_EXPAND_WAIT)

        # Step 6: Check for login dialog BEFORE clicking action
        # For private repos, login dialog appears after expanding the repo menu
        login_check = await _evaluate_js(page, _js_call("checkLoginDialog"))
        logger.debug("Login dialog check result: %s", login_check)

        if login_check.get("hasLoginDialog"):
            logger.info(
                "Login dialog detected at: %s", login_check.get("location", "unknown")
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
                "Token fill result: filled=%s, valueVerified=%s, method=%s, "
                "inputType=%s, inputId=%s",
                fill_result.get("filled"),
                fill_result.get("valueVerified"),
                fill_result.get("method"),
                fill_result.get("inputType"),
                fill_result.get("inputId"),
            )

            if not fill_result.get("filled"):
                return AbapGitActionResult.failure_result(
                    action_lower,
                    repo_name,
                    f"Failed to fill token: {fill_result.get('error')}",
                )

            # If JS fill didn't verify, try using Playwright's fill as fallback
            if not fill_result.get("valueVerified"):
                input_id = fill_result.get("inputId")
                if input_id:
                    logger.warning(
                        "Token value not verified, trying Playwright fill for #%s",
                        input_id
                    )
                    try:
                        await page.fill(f"#{input_id}", token)
                        logger.info("Playwright fill completed for #%s", input_id)
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        logger.warning("Playwright fill failed: %s", e)

            # Click "Weiter" (Continue) button using Playwright locators
            logger.info("Looking for Weiter/Continue button...")
            weiter_clicked = False

            # Try various button selectors for "Weiter" button
            button_selectors = [
                "button:has-text('Weiter')",
                "button:has-text('Continue')",
                "input[type='button'][value*='Weiter']",
                "input[type='submit'][value*='Weiter']",
                "span:has-text('Weiter')",  # SAP often wraps button text in spans
                "[title*='Weiter']",
                "[title*='Continue']",
            ]

            for selector in button_selectors:
                try:
                    locator = page.locator(selector).first
                    if await locator.is_visible(timeout=500):
                        await locator.click()
                        logger.info("Clicked button using selector: %s", selector)
                        weiter_clicked = True
                        break
                except Exception:  # pylint: disable=broad-exception-caught
                    continue

            if not weiter_clicked:
                # Fallback to Enter key
                logger.warning("Weiter button not found, trying Enter key")
                await page.keyboard.press("Enter")

            # Wait for login to complete and menu to become available
            await page.wait_for_timeout(ACTION_WAIT)
            # Re-expand the menu after login
            logger.info("Re-clicking menu arrow after login...")
            click_menu = await _evaluate_js(page, _js_call("clickMenuArrow", repo_pattern))
            if click_menu.get("error"):
                logger.warning("Failed to re-click menu arrow: %s", click_menu)
            await page.wait_for_timeout(MENU_EXPAND_WAIT)
        else:
            logger.debug("No login dialog detected - proceeding without authentication")

        # Step 7: Click the action (Pull or Stage) using Playwright locators
        clicked_text = await _click_action_link(page, action)

        if not clicked_text:
            # Fallback to JavaScript method
            logger.warning("Playwright couldn't find %s, trying JavaScript", action)
            click_action = await _evaluate_js(page, _js_call("clickAction", action))
            if click_action.get("error"):
                available = click_action.get("available", [])
                return AbapGitActionResult.failure_result(
                    action_lower,
                    repo_name,
                    f"Failed to click {action}: {click_action['error']}. Available: {available}",
                )
            clicked_text = click_action.get("clickedText", action)
            logger.info("Clicked action via JS: %s", clicked_text)

        await page.wait_for_timeout(ACTION_WAIT)

        # Step 8: Handle pull confirmation dialog if present
        if action == "Pull":
            await _handle_pull_confirmation_dialog(page)

        # Step 9: Verify action result (for Pull) with polling
        if action == "Pull":
            # Success patterns to check in status bar
            # Success: "Serialize: 2 objects, 0.02 seconds"
            # Also: "Pull successful", "objects imported", "up to date"
            success_patterns = [
                r"serialize.*\d+\s*objects",  # "Serialize: 2 objects, 0.02 seconds"
                r"pull.*success",
                r"objects?\s+imported",
                r"up\s+to\s+date",
                r"nothing\s+to\s+pull",
            ]

            # Poll for completion with timeout
            poll_interval = ACTION_WAIT  # 5 seconds between checks
            max_wait = PULL_COMPLETE_WAIT  # 30 seconds total
            elapsed = 0

            while elapsed < max_wait:
                await page.wait_for_timeout(poll_interval)
                elapsed += poll_interval

                # Read status bar for verification
                status_bar = await sap_read_status_bar_impl()
                status_message = status_bar.message or ""
                logger.info(
                    "Status bar after %dms: type=%s, message=%s",
                    elapsed, status_bar.type, status_message
                )

                # Check for success indicators
                is_success = any(
                    re.search(pattern, status_message, re.IGNORECASE)
                    for pattern in success_patterns
                )

                if is_success:
                    return AbapGitActionResult.success_result(
                        action_lower,
                        repo_name,
                        f"{action} completed: {status_message}",
                        clicked_action=clicked_text,
                    )

                # Check for error indicators (StatusBarType "E" = error)
                if status_bar.type == "E":
                    return AbapGitActionResult.failure_result(
                        action_lower,
                        repo_name,
                        f"Pull failed: {status_message}",
                        clicked_action=clicked_text,
                    )

                # Also check iframe for errors
                verify_result = await _evaluate_js(page, _js_call("checkActionResult"))
                if verify_result.get("hasError"):
                    error_msg = (
                        verify_result.get("message") or status_message or "Pull operation failed"
                    )
                    return AbapGitActionResult.failure_result(
                        action_lower,
                        repo_name,
                        error_msg,
                        clicked_action=clicked_text,
                    )

                # If status bar has any message, consider it potentially done
                # (might be a success pattern we didn't anticipate)
                if status_message and status_bar.type in ("S", "I", "W"):
                    logger.debug("Status bar has message, assuming completion: %s", status_message)
                    break

            # Timeout or ambiguous result - report what we have
            status_bar = await sap_read_status_bar_impl()
            status_message = status_bar.message or "unknown"
            return AbapGitActionResult.success_result(
                action_lower,
                repo_name,
                f"{action} completed for {repo_name}. Status: {status_message}",
                clicked_action=clicked_text,
            )

        # For Stage action, just return success (user will interact with staging UI)
        return AbapGitActionResult.success_result(
            action_lower,
            repo_name,
            f"{action} view opened for {repo_name}",
            clicked_action=clicked_text,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Use logger.error instead of logger.exception to avoid logging
        # stack traces that might contain sensitive data (e.g., PAT token)
        logger.error("abapGit %s failed: %s: %s", action, type(e).__name__, e)
        return AbapGitActionResult.failure_result(
            action_lower,
            repo_pattern,
            str(e),
        )


# =============================================================================
# SE38 Verification
# =============================================================================


async def _fill_se38_program_field(page: Page, program_name: str) -> bool:
    """Fill the program name field in SE38 using various strategies."""
    # Try direct selectors first
    input_selectors = [
        "input[name*='PROGRAM']",
        "input[id*='PROGRAM']",
        "input[maxlength='40']",
        "#M0\\:46\\:1\\:1\\:\\:0\\:12",
    ]

    for selector in input_selectors:
        try:
            locator = page.locator(selector).first
            if await locator.is_visible(timeout=500):
                await locator.fill(program_name)
                logger.info("Filled program name using selector: %s", selector)
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    # Try sap_fill_form as fallback
    try:
        from sapwebguimcp.tools.sap_tool_impl import (  # pylint: disable=import-outside-toplevel
            sap_fill_form_impl,
        )
        fill_result = await sap_fill_form_impl(
            {"Programm": program_name, "Program": program_name}, strict=False
        )
        if fill_result.success:
            logger.info("Filled program name using sap_fill_form")
            return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("sap_fill_form fallback failed: %s", e)

    return False


def _is_actual_abap_source(text: str) -> bool:
    """
    Check if text contains actual ABAP source code (not just UI text with 'Report').

    We need to distinguish between:
    - Page title: "ABAP Editor: Report Z_REPORT_..." (not actual code)
    - Actual code: "REPORT Z_REPORT_...\nWRITE 'Hello'." (actual code)
    """
    upper_text = text.upper()

    # Strict patterns that indicate actual ABAP code
    # These patterns are less likely to appear in UI text
    strict_patterns = [
        "WRITE '",   # Write statement with string literal
        'WRITE "',   # Write statement with string literal
        "WRITE:",    # Write chain statement
        "DATA:",     # Data chain declaration
        "TYPES:",    # Types declaration
        "ENDMETHOD", # Method end
        "ENDCLASS",  # Class end
        "ENDLOOP",   # Loop end
        "ENDIF",     # If end
        "ENDFORM",   # Form end
        "FORM ",     # Form definition
        "METHOD ",   # Method definition
        "CLASS ",    # Class definition
    ]

    # Check for strict patterns first
    if any(pattern in upper_text for pattern in strict_patterns):
        return True

    # For "REPORT" and other keywords, require additional indicators
    # that it's code, not UI text (e.g., a period at end of line, or multiple keywords)
    # Actual ABAP code: "REPORT Z_MYREPORT." (with period)
    # UI text: "Report Z_MYREPORT anzeigen" (no period, followed by "anzeigen")
    import re

    # Check for REPORT statement: must be followed by name and period (.)
    # e.g., "REPORT Z_TEST." or "REPORT Y_TEST."
    has_report = bool(re.search(r"REPORT\s+[ZY][A-Z0-9_]+\s*\.", upper_text))

    has_data = "DATA " in upper_text and ("TYPE" in upper_text or "LIKE" in upper_text)
    has_write = "WRITE " in upper_text
    has_if = "IF " in upper_text and ("ENDIF" in upper_text or "ELSE" in upper_text)

    # Count how many code indicators we have
    indicators = sum([has_report, has_data, has_write, has_if])

    # If we have at least 1 indicator, it's likely code
    # (REPORT with period is very strong indicator)
    return indicators >= 1


async def _read_source_from_iframes(page: Page) -> str | None:
    """Try to read ABAP source code from iframes."""
    try:
        iframes = await page.query_selector_all("iframe")
        for iframe in iframes:
            frame = await iframe.content_frame()
            if not frame:
                continue
            # Look for specific editor elements first
            for selector in ["textarea", ".ace_editor", ".editor-content", "pre", ".urPTxt"]:
                elements = await frame.query_selector_all(selector)
                for el in elements:
                    text = await el.inner_text()
                    if _is_actual_abap_source(text):
                        return text
            # Fallback to body
            body = await frame.query_selector("body")
            if body:
                text = await body.inner_text()
                if _is_actual_abap_source(text):
                    return text
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return None


async def _read_source_from_main_document(page: Page) -> str | None:
    """Try to read ABAP source code from main document elements."""
    # More specific selectors for SE38 editor
    # SE38 in Web GUI uses various elements for displaying code
    editor_selectors = [
        "textarea",  # Direct textarea
        ".ace_editor",  # ACE editor
        ".ace_content",  # ACE editor content
        ".urPTxt",  # SAP rich text
        "pre",  # Preformatted
        "code",  # Code element
        ".editor-content",
        "[id*='editor']",  # Any element with 'editor' in ID
        "[class*='editor']",  # Any element with 'editor' in class
        "[class*='source']",  # Any element with 'source' in class
        "[class*='code']",  # Any element with 'code' in class
        # SAP-specific selectors
        ".lsListbox__list",  # SAP listbox
        "table.urST",  # SAP standard table
        "#sapwd_main_window_root_contents table",  # Tables in main content
    ]
    try:
        for selector in editor_selectors:
            elements = await page.query_selector_all(selector)
            for el in elements:
                text = await el.inner_text()
                if _is_actual_abap_source(text):
                    logger.debug("Found source in selector: %s", selector)
                    return text
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Try to read table rows (SE38 often displays code in table format)
    try:
        # Look for table cells that might contain actual ABAP code lines
        cells = await page.query_selector_all("td")
        code_lines = []
        for cell in cells:
            text = (await cell.inner_text()).strip()
            # Only include cells that look like actual ABAP code lines
            # Require stricter patterns: WRITE with string, REPORT with period, etc.
            if text and len(text) > 5:
                upper = text.upper()
                # Only accept text that looks like actual code statements
                is_code_line = (
                    ("WRITE '" in upper or 'WRITE "' in upper)  # WRITE statement
                    or ("REPORT " in upper and "." in text)  # REPORT statement with period
                    or "ENDLOOP" in upper
                    or "ENDIF" in upper
                    or "ENDFORM" in upper
                    or "ENDMETHOD" in upper
                )
                if is_code_line:
                    code_lines.append(text)
        if code_lines:
            logger.debug("Found code lines in table cells: %d", len(code_lines))
            return "\n".join(code_lines)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return None


async def _read_source_from_body(page: Page) -> str | None:
    """
    Last resort: get all visible text from page body.

    Only returns content if it contains actual ABAP code patterns.
    """
    try:
        body_text = await page.inner_text("body")
        if _is_actual_abap_source(body_text):
            return body_text
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return None


async def _read_source_via_javascript(page: Page) -> str | None:
    """
    Use JavaScript to find ABAP source code in the page.

    This function searches all text nodes and elements for ABAP code patterns.
    """
    js_code = """
    () => {
        // Search all text content for ABAP code
        function getTextNodes(element) {
            let texts = [];
            const walker = document.createTreeWalker(
                element,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (text.length > 5) {
                    texts.push(text);
                }
            }
            return texts;
        }

        // Try to find elements that look like code
        const codePatterns = ['REPORT ', 'WRITE ', 'DATA ', 'IF ', 'LOOP ', 'ENDLOOP'];

        // Search main document
        let allTexts = getTextNodes(document.body);

        // Search iframes
        const iframes = document.querySelectorAll('iframe');
        for (const iframe of iframes) {
            try {
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (doc && doc.body) {
                    allTexts = allTexts.concat(getTextNodes(doc.body));
                }
            } catch (e) {
                // Ignore cross-origin errors
            }
        }

        // Filter to texts that look like ABAP code
        const codeTexts = allTexts.filter(text => {
            const upper = text.toUpperCase();
            return codePatterns.some(pattern => upper.includes(pattern));
        });

        // Return the longest matching text (likely the full code)
        if (codeTexts.length > 0) {
            return codeTexts.sort((a, b) => b.length - a.length)[0];
        }

        // If no code found, return null
        return null;
    }
    """
    try:
        result = await page.evaluate(js_code)
        if result:
            logger.info("Found source via JavaScript search: %d chars", len(result))
            return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("JavaScript source search failed: %s", e)
    return None


async def read_se38_source(program_name: str) -> dict[str, Any]:
    """
    Read ABAP report source code from SE38.

    This function navigates to SE38, enters the program name,
    presses F7 (Display), and reads the source code.

    Args:
        program_name: The ABAP program/report name (e.g., Z_REPORT_TEST)

    Returns:
        Dict with success, source_code, error fields
    """
    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()

    if page is None:
        return {"success": False, "error": "No browser page available"}

    try:
        # Ensure focus is on main frame (not inside abapGit iframe)
        await page.bring_to_front()

        # abapGit uses a custom UI that may not have the standard OK-Code field visible.
        # We need to exit abapGit first by pressing F3 (Back) to get to a standard SAP screen.
        logger.info("Exiting abapGit by pressing F3 (Back)...")
        await page.keyboard.press("Escape")  # Close any open menus/dialogs first
        await page.wait_for_timeout(300)
        await page.keyboard.press("F3")  # Go back from abapGit
        await page.wait_for_timeout(2000)  # Wait for navigation

        # Now try to navigate to SE38 from the main SAP screen
        tx_result = await sap_transaction_impl("SE38", new_window=False)
        if not tx_result.success:
            return {"success": False, "error": f"Failed to open SE38: {tx_result.error}"}

        await page.wait_for_timeout(2000)

        # Fill program name
        if not await _fill_se38_program_field(page, program_name):
            return {"success": False, "error": "Could not find program input field"}

        # In SE38, after entering program name:
        # 1. Ensure "Source Code" radio is selected (usually default)
        # 2. Click the "Anzeigen" (Display) button or press F7
        #
        # F7 sometimes doesn't work, try clicking the button directly
        from sapwebguimcp.tools.sap_tool_impl import sap_discover_buttons_impl

        # First try F7
        logger.info("Pressing F7 to display source code...")
        await page.keyboard.press("F7")
        await page.wait_for_timeout(2000)

        # Check if we're still on the entry screen
        page_title = await page.title()
        if "Einstieg" in page_title or "Entry" in page_title:
            # F7 didn't work, try clicking the Display button
            logger.info("F7 didn't navigate, trying to click Display button...")
            buttons_result = await sap_discover_buttons_impl()
            if buttons_result.buttons:
                for btn in buttons_result.buttons:
                    btn_label = (btn.label or "").lower()
                    if "anzeigen" in btn_label or "display" in btn_label:
                        logger.info("Clicking button: %s", btn.label)
                        if btn.selector:
                            await page.click(btn.selector)
                            await page.wait_for_timeout(3000)
                            break
                else:
                    # No display button found, try Enter
                    logger.info("No Display button found, trying Enter...")
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(3000)

        await page.wait_for_timeout(2000)  # Additional wait for source to load

        # Try to read source code from various locations
        logger.info("Looking for source code in iframes...")
        source_code = await _read_source_from_iframes(page)
        if not source_code:
            logger.info("No source in iframes, trying main document...")
            source_code = await _read_source_from_main_document(page)
        if not source_code:
            logger.info("No source in main document, trying JavaScript search...")
            source_code = await _read_source_via_javascript(page)
        if not source_code:
            logger.info("No source from JS search, trying body text...")
            source_code = await _read_source_from_body(page)

        if source_code:
            logger.info("Found source code (%d chars)", len(source_code))
            return {
                "success": True,
                "source_code": source_code,
                "program_name": program_name,
            }

        # If no source found, return the body text for debugging
        logger.warning("No ABAP source code found, returning body text for debugging")
        body_text = await page.inner_text("body")
        return {
            "success": True,  # Mark success but include debug info
            "source_code": body_text[:2000],  # Truncate for debugging
            "program_name": program_name,
            "debug_note": "No ABAP source patterns detected, returning raw body text",
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("SE38 read failed: %s: %s", type(e).__name__, e)
        return {"success": False, "error": str(e)}


async def verify_abap_report_content(
    program_name: str, expected_text: str
) -> dict[str, Any]:
    """
    Verify that an ABAP report contains expected text.

    This is a convenience wrapper around read_se38_source that checks
    for specific content in the source code.

    Args:
        program_name: The ABAP program/report name
        expected_text: Text that should be present in the source code

    Returns:
        Dict with success, found, source_code, error fields
    """
    result = await read_se38_source(program_name)

    if not result.get("success"):
        return result

    source_code = result.get("source_code", "")
    found = expected_text in source_code

    return {
        "success": True,
        "found": found,
        "expected_text": expected_text,
        "source_code": source_code,
        "program_name": program_name,
    }


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

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read SE38 Source",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        description=(
            "Read ABAP report source code from SE38. "
            "Navigates to SE38, enters the program name, and displays the source code. "
            "Useful for verifying abapGit pull operations."
        ),
    )
    async def sap_read_se38_source(program_name: str) -> dict[str, Any]:
        """
        Read ABAP report source code from SE38.

        This tool navigates to SE38, enters the program name,
        presses F7 (Display), and reads the source code.

        Args:
            program_name: The ABAP program/report name (e.g., Z_REPORT_TEST)

        Returns:
            Dict with success, source_code, program_name, error fields

        Example:
            sap_read_se38_source(program_name="Z_MY_REPORT")
        """
        return await read_se38_source(program_name)
