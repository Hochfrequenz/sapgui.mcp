"""
abapGit integration tools for SAP Web GUI.

This module provides:
- List: Enumerate all registered abapGit repositories and their metadata
- Pull: Fetch and apply changes from a remote git repository via Z_ABAPGIT_PULL
- SE38 Verification: Read ABAP report source code to verify pulls

The pull operation uses the Z_ABAPGIT_PULL transaction which calls the abapGit
ABAP API directly, avoiding fragile UI automation. The ABAP report source is
maintained in:
  unittests/abapgit_repos/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY/src/z_abapgit_pull.prog.abap

If the Z_ABAPGIT_PULL transaction is not found, you need to create it in SAP.
The tool will provide a link to the source code.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import Locator, Page

from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.abapgit_models import AbapGitActionResult, AbapGitListResult, AbapGitRepoInfo
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.tools.sap_tool_impl import sap_read_status_bar_impl, sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["parse_repo_list_output", "register_abapgit_tools", "validate_github_pat"]


async def validate_github_pat(pat: str) -> tuple[bool, str]:
    """
    Validate a GitHub PAT by calling GET /user.

    Returns:
        (True, github_username) if the token is valid.
        (False, error_message) if the token is invalid or unreachable.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {pat}",
                    "User-Agent": "sapwebgui-mcp",
                },
                timeout=5.0,
            )
        if resp.status_code == 200:
            login = resp.json().get("login", "unknown")
            return True, login
        try:
            msg = resp.json().get("message", f"HTTP {resp.status_code}")
        except (ValueError, KeyError):  # non-JSON error responses (e.g. 502 proxy)
            msg = f"HTTP {resp.status_code}"
        return False, msg
    except (httpx.HTTPError, OSError) as exc:
        return False, f"GitHub API unreachable: {exc}"


# =============================================================================
# Helper Data Structures
# =============================================================================


@dataclass
class PullParams:
    """Parameters for pull operation after validation."""

    repo: str
    trkorr: str | None
    username: str | None
    pat: str | None
    tcode_with_params: str


# =============================================================================
# Error Detection Helpers
# =============================================================================

ERROR_KEYWORDS = [
    "not found",
    "nicht gefunden",
    "error",
    "fehler",
    "exception",
    "failed",
    "fehlgeschlagen",
    "required",
    "erforderlich",
    "transport",
    "repository",
]

ERROR_PATTERNS = [
    ("repository not found", "Repository not found"),
    ("nicht gefunden", "Not found"),
    ("transport required", "Transport required"),
    ("transport erforderlich", "Transport required"),
    ("exception", "Exception occurred"),
    ("fehler bei", "Error in"),
    ("error:", "Error"),
]


async def _check_for_error_popup(page: Page) -> str | None:
    """Check for SAP error popup dialog and extract message text."""
    try:
        popup_selectors = [
            ".urMessageBox",
            ".urPopup",
            "[id*='PopupWindow']",
            "[id*='ModalWindow']",
            ".lsPopup",
            "[role='alertdialog']",
            ".urMsgArea",
            "#MESSAGE_POPUP",
            "[id*='MESSAGE']",
        ]

        for selector in popup_selectors:
            popup = await page.query_selector(selector)
            if popup and await popup.is_visible():
                text = (await popup.inner_text()).strip()
                text_lower = text.lower()
                if any(keyword in text_lower for keyword in ERROR_KEYWORDS):
                    lines = text.split("\n")
                    message_lines = [
                        line.strip()
                        for line in lines
                        if line.strip()
                        and line.strip().lower() not in ("ok", "cancel", "abbrechen", "ja", "nein", "yes", "no")
                    ]
                    if message_lines:
                        logger.info("Found error popup", extra={"popup_message": message_lines[0]})
                        return " ".join(message_lines)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Checking for popup", extra={"error": str(e)})
    return None


async def _check_screen_for_errors(page: Page) -> str | None:
    """Check the entire screen for error indicators as a fallback."""
    try:
        body_text = await page.inner_text("body")
        body_lower = body_text.lower()

        for pattern, message_prefix in ERROR_PATTERNS:
            if pattern in body_lower:
                idx = body_lower.find(pattern)
                start = max(0, idx - 50)
                end = min(len(body_text), idx + 150)
                context = " ".join(body_text[start:end].split())
                if context:
                    logger.info("Found error on screen", extra={"context": context[:100]})
                    return context
                return message_prefix
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Checking screen for errors", extra={"error": str(e)})
    return None


# =============================================================================
# Pull Parameter Validation
# =============================================================================


def _validate_param(value: str, param_name: str, pattern: str, description: str) -> str | None:
    """Validate a parameter value against a pattern. Returns error message if invalid, None if OK."""
    if not re.match(pattern, value):
        return f"Invalid {param_name}: contains forbidden characters. {description}"
    return None


def _validate_and_prepare_params(
    repo: str,
    trkorr: str | None,
    username: str | None,
    pat: str | None,
) -> PullParams | AbapGitActionResult:
    """Validate inputs and prepare pull parameters. Returns error result if validation fails."""
    # Validate repo name to prevent injection
    if not re.match(r"^[A-Za-z0-9_/]+$", repo):
        return AbapGitActionResult.failure_result(
            action="pull",
            repo_name=repo,
            error=(
                f"Invalid repository name: {repo}. "
                "Only alphanumeric characters, underscores, and forward slashes are allowed."
            ),
        )

    # Validate other parameters to prevent command injection via semicolons/special chars
    if trkorr:
        # SAP transport requests: alphanumeric only (e.g., "S4UK902008")
        error = _validate_param(trkorr, "trkorr", r"^[A-Za-z0-9]+$", "Only alphanumeric allowed.")
        if error:
            return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=error)

    if username:
        # GitHub usernames: alphanumeric and hyphens
        error = _validate_param(
            username, "username", r"^[A-Za-z0-9_-]+$", "Only alphanumeric, underscores, hyphens allowed."
        )
        if error:
            return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=error)

    if pat:
        # GitHub PATs: alphanumeric and underscores (ghp_xxx, github_pat_xxx)
        error = _validate_param(pat, "pat", r"^[A-Za-z0-9_]+$", "Only alphanumeric and underscores allowed.")
        if error:
            return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=error)

    # Get credentials from settings if not provided
    settings = get_settings()
    effective_pat = pat or settings.abapgit_pat or settings.github_pat
    effective_username = username
    if not effective_username and effective_pat:
        effective_username = settings.github_user or "x-access-token"

    # Build transaction command
    # Note: All params are validated above to contain only safe characters (no semicolons/spaces)
    # so they won't break the semicolon-separated OK-Code command syntax
    params = [f"P_REPO={repo}"]
    if trkorr:
        params.append(f"P_TRKORR={trkorr}")
    if effective_username:
        params.append(f"P_USER={effective_username}")
    if effective_pat:
        params.append(f"P_TOKEN={effective_pat}")

    tcode_with_params = f"/nZ_ABAPGIT_PULL {'; '.join(params)};"

    return PullParams(
        repo=repo,
        trkorr=trkorr,
        username=effective_username,
        pat=effective_pat,
        tcode_with_params=tcode_with_params,
    )


# =============================================================================
# OK-Code Field Handling
# =============================================================================


async def _get_okcode_field(page: Page, repo: str) -> Locator | AbapGitActionResult:
    """Find or enable OK-Code field. Returns error result if not available."""
    from sapwebguimcp.tools.sap_tool_impl import (  # pylint: disable=import-outside-toplevel
        _enable_okcode_field,
        _find_okcode_field,
    )

    okcode_field: Locator | None = await _find_okcode_field(page)
    if okcode_field:
        return okcode_field

    logger.info("OK-Code field not found, attempting to enable it")
    success, message = await _enable_okcode_field(page)
    if not success:
        return AbapGitActionResult.failure_result(
            action="pull",
            repo_name=repo,
            error=f"Could not find or enable OK-Code field: {message}",
        )

    okcode_field_retry: Locator | None = await _find_okcode_field(page)
    if not okcode_field_retry:
        return AbapGitActionResult.failure_result(
            action="pull",
            repo_name=repo,
            error="OK-Code field still not visible after enabling",
        )
    return okcode_field_retry


# =============================================================================
# Pull Result Analysis
# =============================================================================


async def _analyze_pull_result(page: Page, repo: str) -> AbapGitActionResult:
    """Analyze status bar and screen to determine pull result."""
    status = await sap_read_status_bar_impl()
    msg = status.message or ""
    msg_type = status.type or ""
    msg_lower = msg.lower()

    logger.info("Pull result", extra={"status_type": msg_type, "status_message": msg})

    # Check for explicit success or error on first read
    is_success = "pull successful" in msg_lower or ("successful" in msg_lower and msg_type in ("S", "I"))
    is_error = msg_type in ("E", "A") or "not found" in msg_lower or "error" in msg_lower

    if is_success:
        return AbapGitActionResult.success_result(action="pull", repo_name=repo, message=msg)
    if is_error:
        return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=msg)

    # Retry status bar read
    await page.wait_for_timeout(2000)
    status = await sap_read_status_bar_impl()
    final_msg = status.message or msg
    final_type = status.type or msg_type
    final_lower = final_msg.lower()
    logger.info("Final status check", extra={"status_type": final_type, "status_message": final_msg})

    # Check final status
    is_final_success = "pull successful" in final_lower
    is_final_error = final_type in ("E", "A")
    screen_error = None if final_msg and final_type != "none" else await _check_screen_for_errors(page)

    if is_final_success:
        return AbapGitActionResult.success_result(action="pull", repo_name=repo, message=final_msg)
    if is_final_error or screen_error:
        return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=screen_error or final_msg)

    # Treat ambiguous result based on whether we got any status message.
    # Empty status bar may mask auth errors (expired PAT → cx_root in ABAP).
    if not final_msg:
        return AbapGitActionResult.failure_result(
            action="pull",
            repo_name=repo,
            error="Pull status unknown: SAP status bar was empty after pull. "
            "This may indicate an authentication failure (expired PAT) "
            "or a status bar extraction issue. Check SAP manually.",
        )
    return AbapGitActionResult.success_result(
        action="pull", repo_name=repo, message=f"Pull completed. Status: {final_msg}"
    )


# =============================================================================
# Main Pull Implementation
# =============================================================================


async def _handle_popup_error(page: Page, repo: str) -> AbapGitActionResult | None:
    """Check for error popup and return failure if found, None otherwise."""
    popup_error = await _check_for_error_popup(page)
    if popup_error:
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)
        return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=popup_error)
    return None


async def _execute_pull_transaction(page: Page, params: PullParams, repo: str) -> AbapGitActionResult | None:
    """Execute pull transaction and return failure result if error, None if OK to continue."""
    # Get OK-Code field
    okcode_result = await _get_okcode_field(page, repo)
    if isinstance(okcode_result, AbapGitActionResult):
        return okcode_result
    okcode_field = okcode_result

    # Enter transaction with parameters
    await page.bring_to_front()
    await page.wait_for_timeout(500)
    await okcode_field.click()
    await page.wait_for_timeout(200)
    await okcode_field.fill("")
    await okcode_field.fill(params.tcode_with_params)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2000)

    # Check if transaction was found
    status = await sap_read_status_bar_impl()
    status_msg = (status.message or "").lower()
    tx_not_found = "not found" in status_msg or "existiert nicht" in status_msg or "does not exist" in status_msg
    if tx_not_found:
        return AbapGitActionResult.failure_result(
            action="pull",
            repo_name=repo,
            error=(
                "Transaction Z_ABAPGIT_PULL not found. Create this transaction in your SAP system. "
                "See docs/plans/2026-01-23-abapgit-api-pull-design.md for the ABAP source code."
            ),
        )
    return None


async def _run_pull_and_check_errors(page: Page, repo: str) -> AbapGitActionResult | None:
    """Execute F8 and wait for SAP to finish processing. Returns error if found."""
    await page.keyboard.press("F8")
    try:
        await page.wait_for_load_state("networkidle", timeout=120_000)
    except TimeoutError:
        logger.warning("networkidle timeout after F8 — pull may still be running")

    return await _handle_popup_error(page, repo)


def _clean_timestamp(value: str) -> str | None:
    """Return None for empty or initial ABAP TIMESTAMPL values (all zeros)."""
    if not value or value.replace("0", "").replace(".", "") == "":
        return None
    return value


def parse_repo_list_output(raw_output: str) -> list[AbapGitRepoInfo]:
    """Parse tilde-delimited WRITE output from Z_ABAPGIT_PULL LIST mode.

    Expected format per line: name~url~package~branch~deserialized_at~deserialized_by~offline
    Uses ~ as delimiter because SAP WebGUI strips | (pipe) characters from WRITE output.
    Lines that don't match (headers, empty, UI noise) are silently skipped.
    """
    repos: list[AbapGitRepoInfo] = []
    for line in raw_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("~")
        if len(parts) < 4:
            continue
        name = parts[0].strip()
        url = parts[1].strip()
        if not name or not url or ("://" not in url and not url.startswith("file:")):
            continue
        repos.append(
            AbapGitRepoInfo(
                name=name,
                url=url,
                package=parts[2].strip() if len(parts) > 2 else "",
                branch=parts[3].strip() if len(parts) > 3 else "",
                last_pull_at=(_clean_timestamp(parts[4].strip())) if len(parts) > 4 else None,
                last_pull_by=(parts[5].strip() or None) if len(parts) > 5 else None,
                is_offline=parts[6].strip().upper() == "X" if len(parts) > 6 else False,
            )
        )
    return repos


async def _abapgit_list_repos() -> AbapGitListResult:
    """List all registered abapGit repositories via Z_ABAPGIT_PULL P_ACTION=LIST."""
    logger.info("Listing abapGit repositories")

    browser_manager = await get_browser_manager()
    page = await browser_manager.get_page()
    if not page:
        return AbapGitListResult(
            success=False,
            error="No active browser session. Call sap_login first.",
        )

    try:
        # Get OK-Code field
        okcode_result = await _get_okcode_field(page, "LIST")
        if isinstance(okcode_result, AbapGitActionResult):
            return AbapGitListResult(success=False, error=okcode_result.error)
        okcode_field = okcode_result

        # Enter transaction with LIST action
        tcode_with_params = "/nZ_ABAPGIT_PULL P_ACTION=LIST;"
        await page.bring_to_front()
        await page.wait_for_timeout(500)
        await okcode_field.click()
        await page.wait_for_timeout(200)
        await okcode_field.fill("")
        await okcode_field.fill(tcode_with_params)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)

        # Check if transaction was found
        status = await sap_read_status_bar_impl()
        status_msg = (status.message or "").lower()
        if "not found" in status_msg or "existiert nicht" in status_msg or "does not exist" in status_msg:
            return AbapGitListResult(
                success=False,
                error=(
                    "Transaction Z_ABAPGIT_PULL not found. "
                    "Ensure the report is deployed with LIST support. "
                    "See docs/plans/2026-02-26-abapgit-list-repos-design.md"
                ),
            )

        # Execute report with F8
        await page.keyboard.press("F8")
        await page.wait_for_timeout(3000)

        # Read the WRITE output from the screen via JavaScript
        raw_output = await page.evaluate("""
            () => {
                // In SAP Web GUI, ABAP WRITE output is normally rendered inside
                // the main window content container '#sapwd_main_window_root_contents'.
                // For robustness, we fall back to 'document.body' in cases where this
                // container does not exist (e.g. different themes, older WebGUI
                // layouts, or error pages that bypass the standard shell).
                const body = document.querySelector('#sapwd_main_window_root_contents') || document.body;
                return body.innerText || body.textContent || '';
            }
        """)

        repos = parse_repo_list_output(raw_output or "")
        logger.info("Found repositories", extra={"count": len(repos)})

        return AbapGitListResult(success=True, repos=repos)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("abapGit list repos failed")
        return AbapGitListResult(success=False, error=str(e))


async def _abapgit_pull_via_api(
    repo: str,
    trkorr: str | None,
    username: str | None,
    pat: str | None,
) -> AbapGitActionResult:
    """Pull changes using the Z_ABAPGIT_PULL transaction (abapGit ABAP API)."""
    logger.info("Starting abapGit Pull via API", extra={"repo": repo})

    browser_manager = await get_browser_manager()
    page = await browser_manager.get_page()
    if not page:
        return AbapGitActionResult.failure_result(
            action="pull", repo_name=repo, error="No active browser session. Call sap_login first."
        )

    try:
        # Validate and prepare parameters
        params_result = _validate_and_prepare_params(repo, trkorr, username, pat)
        if isinstance(params_result, AbapGitActionResult):
            return params_result
        params = params_result

        logger.info(
            "Calling transaction with params",
            extra={"repo": params.repo, "trkorr": params.trkorr, "user": params.username, "has_pat": bool(params.pat)},
        )

        # Execute transaction
        tx_error = await _execute_pull_transaction(page, params, repo)
        if tx_error:
            return tx_error

        # Run pull and check for popup errors
        popup_error = await _run_pull_and_check_errors(page, repo)
        if popup_error:
            return popup_error

        return await _analyze_pull_result(page, repo)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("abapGit pull via API", extra={"repo": repo})
        return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=str(e))


# =============================================================================
# SE38 Verification
# =============================================================================


async def _fill_se38_program_field(page: Page, program_name: str) -> bool:
    """Fill the program name field in SE38 using various strategies."""
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
                logger.info("Filled program name", extra={"selector": selector})
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    # Try sap_fill_form as fallback
    try:
        from sapwebguimcp.tools.sap_tool_impl import (  # pylint: disable=import-outside-toplevel
            sap_fill_form_impl,
        )

        fill_result = await sap_fill_form_impl({"Programm": program_name, "Program": program_name}, strict=False)
        if fill_result.success:
            logger.info("Filled program name using sap_fill_form")
            return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("sap_fill_form fallback failed", extra={"error": str(e)})

    return False


def _is_actual_abap_source(text: str) -> bool:
    """Check if text contains actual ABAP source code (not just UI text)."""
    upper_text = text.upper()

    # Strict patterns that indicate actual ABAP code
    strict_patterns = [
        "WRITE '",
        'WRITE "',
        "WRITE:",
        "DATA:",
        "TYPES:",
        "ENDMETHOD",
        "ENDCLASS",
        "ENDLOOP",
        "ENDIF",
        "ENDFORM",
        "FORM ",
        "METHOD ",
        "CLASS ",
    ]

    if any(pattern in upper_text for pattern in strict_patterns):
        return True

    # Check for REPORT statement with proper format
    # Matches: Z/Y customer reports, standard SAP reports, and namespaced reports (/NAMESPACE/...)
    has_report = bool(re.search(r"REPORT\s+(/[A-Z0-9_]+/)?[A-Z][A-Z0-9_]*\s*\.", upper_text))
    has_data = "DATA " in upper_text and ("TYPE" in upper_text or "LIKE" in upper_text)
    has_write = "WRITE " in upper_text
    has_if = "IF " in upper_text and ("ENDIF" in upper_text or "ELSE" in upper_text)

    return sum([has_report, has_data, has_write, has_if]) >= 1


async def _read_source_from_iframes(page: Page) -> str | None:
    """Try to read ABAP source code from iframes."""
    try:
        iframes = await page.query_selector_all("iframe")
        for iframe in iframes:
            frame = await iframe.content_frame()
            if not frame:
                continue
            for selector in ["textarea", ".ace_editor", ".editor-content", "pre", ".urPTxt"]:
                elements = await frame.query_selector_all(selector)
                for el in elements:
                    text = await el.inner_text()
                    if _is_actual_abap_source(text):
                        return text
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
    editor_selectors = [
        "textarea",
        ".ace_editor",
        ".ace_content",
        ".urPTxt",
        "pre",
        "code",
        ".editor-content",
        "[id*='editor']",
        "[class*='editor']",
        "[class*='source']",
        "[class*='code']",
        ".lsListbox__list",
        "table.urST",
        "#sapwd_main_window_root_contents table",
    ]
    try:
        for selector in editor_selectors:
            elements = await page.query_selector_all(selector)
            for el in elements:
                text = await el.inner_text()
                if _is_actual_abap_source(text):
                    logger.debug("Found source in selector", extra={"selector": selector})
                    return text
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Try table cells
    try:
        cells = await page.query_selector_all("td")
        code_lines = []
        for cell in cells:
            text = (await cell.inner_text()).strip()
            if text and len(text) > 5:
                upper = text.upper()
                is_code_line = (
                    ("WRITE '" in upper or 'WRITE "' in upper)
                    or ("REPORT " in upper and "." in text)
                    or "ENDLOOP" in upper
                    or "ENDIF" in upper
                    or "ENDFORM" in upper
                    or "ENDMETHOD" in upper
                )
                if is_code_line:
                    code_lines.append(text)
        if code_lines:
            logger.debug("Found code lines in table cells", extra={"count": len(code_lines)})
            return "\n".join(code_lines)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return None


async def _read_source_via_javascript(page: Page) -> str | None:
    """Use JavaScript to find ABAP source code in the page."""
    js_code = """
    () => {
        function getTextNodes(element) {
            let texts = [];
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, null, false);
            let node;
            while (node = walker.nextNode()) {
                const text = node.textContent.trim();
                if (text.length > 5) texts.push(text);
            }
            return texts;
        }
        const codePatterns = ['REPORT ', 'WRITE ', 'DATA ', 'IF ', 'LOOP ', 'ENDLOOP'];
        let allTexts = getTextNodes(document.body);
        const iframes = document.querySelectorAll('iframe');
        for (const iframe of iframes) {
            try {
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (doc && doc.body) allTexts = allTexts.concat(getTextNodes(doc.body));
            } catch (e) {}
        }
        const codeTexts = allTexts.filter(text => {
            const upper = text.toUpperCase();
            return codePatterns.some(pattern => upper.includes(pattern));
        });
        return codeTexts.length > 0 ? codeTexts.sort((a, b) => b.length - a.length)[0] : null;
    }
    """
    try:
        result: str | None = await page.evaluate(js_code)
        if result:
            logger.info("Found source via JavaScript search", extra={"chars": len(result)})
            return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("JavaScript source search failed", extra={"error": str(e)})
    return None


async def _try_direct_se38_selectors(page: Page) -> str | None:
    """Try direct SE38 source selectors."""
    se38_selectors = [
        r"#textedit\#TEC_cnt42",
        "[id^='textedit'][id*='TEC_cnt']",
        "textarea[id*='textedit']",
        "[id*='TEC_cnt']",
    ]
    try:
        for selector in se38_selectors:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                if not text or len(text) < 20:
                    tag = await el.evaluate("el => el.tagName")
                    text = await el.input_value() if tag in ["TEXTAREA", "INPUT"] else ""
                if not text or len(text) < 20:
                    text = await el.evaluate("el => el.value || el.textContent || el.innerText")
                if text and len(text) > 20:
                    logger.info("Found source via SE38 selector", extra={"selector": selector, "chars": len(text)})
                    return text
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("SE38 direct selector failed", extra={"error": str(e)})
    return None


async def _navigate_to_se38(page: Page) -> str | None:
    """Navigate to SE38 and return error message if failed, None if OK."""
    await page.bring_to_front()
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    await page.keyboard.press("F3")
    await page.wait_for_timeout(3000)

    try:
        await page.wait_for_selector("#ToolbarOkCode", state="visible", timeout=5000)
    except Exception:  # pylint: disable=broad-exception-caught
        await page.keyboard.press("F3")
        await page.wait_for_timeout(3000)

    tx_result = await sap_transaction_impl("SE38", new_window=False)
    return None if tx_result.success else f"Failed to open SE38: {tx_result.error}"


async def _find_source_code(page: Page) -> str | None:
    """Try various methods to find source code on the page."""
    logger.info("Trying direct SE38 source selector")
    source_code = await _try_direct_se38_selectors(page)

    if not source_code:
        logger.info("Looking for source code in iframes")
        source_code = await _read_source_from_iframes(page)
    if not source_code:
        logger.info("No source in iframes, trying main document")
        source_code = await _read_source_from_main_document(page)
    if not source_code:
        logger.info("No source in main document, trying JavaScript search")
        source_code = await _read_source_via_javascript(page)

    return source_code if source_code and _is_actual_abap_source(source_code) else None


async def read_se38_source(program_name: str) -> dict[str, Any]:
    """Read ABAP report source code from SE38."""
    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()

    if page is None:
        return {"success": False, "error": "No browser page available"}

    try:
        nav_error = await _navigate_to_se38(page)
        if nav_error:
            return {"success": False, "error": nav_error}

        await page.wait_for_timeout(2000)
        if not await _fill_se38_program_field(page, program_name):
            return {"success": False, "error": "Could not find program input field"}

        # Press F7 (Display) and handle entry screen
        logger.info("Pressing F7 to display source code")
        await page.keyboard.press("F7")
        await page.wait_for_timeout(3000)

        page_title = await page.title()
        logger.info("Page title after F7", extra={"title": page_title})
        if "Einstieg" in page_title or "Entry" in page_title:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
            if "Einstieg" in (await page.title()) or "Entry" in (await page.title()):
                await page.keyboard.press("F8")
                await page.wait_for_timeout(3000)

        await page.wait_for_timeout(1000)
        source_code = await _find_source_code(page)

        if source_code:
            logger.info("Found valid ABAP source code", extra={"chars": len(source_code)})
            return {"success": True, "source_code": source_code, "program_name": program_name}

        logger.warning("No ABAP source code found, returning body text")
        body_text = await page.inner_text("body")
        return {
            "success": True,
            "source_code": body_text[:3000],
            "program_name": program_name,
            "debug_note": "No ABAP source patterns detected, returning raw body text",
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("SE38 read failed", extra={"error_type": type(e).__name__, "error": str(e)})
        return {"success": False, "error": str(e)}


async def verify_abap_report_content(program_name: str, expected_text: str) -> dict[str, Any]:
    """Verify that an ABAP report contains expected text."""
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
            title="abapGit List Repositories",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        description=(
            "List all registered abapGit repositories with their metadata. "
            "Returns repo names, Git URLs, packages, branches, and last pull timestamps. "
            "Use this to discover the correct repo name before calling sap_abapgit_pull."
        ),
    )
    async def sap_abapgit_list_repos() -> AbapGitListResult:
        """
        List all registered abapGit repositories.

        Returns:
            AbapGitListResult with list of AbapGitRepoInfo objects

        Example:
            sap_abapgit_list_repos()
        """
        return await _abapgit_list_repos()

    @mcp.tool(
        annotations=ToolAnnotations(
            title="abapGit Pull",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=True,
        ),
        description=(
            "Pull changes from a remote git repository using abapGit API. "
            "Uses the Z_ABAPGIT_PULL report/transaction for reliable execution. "
            "WARNING: This overwrites local ABAP objects with remote versions. "
            "If the tool reports 'status unknown', the pull may have succeeded. "
            "Call sap_read_status_bar() to check, or retry with sap_keyboard('F8') "
            "then sap_read_status_bar()."
        ),
    )
    async def sap_abapgit_pull(
        repo: str,
        trkorr: str | None = None,
        username: str | None = None,
        pat: str | None = None,
    ) -> AbapGitActionResult:
        """
        Pull changes from a remote git repository using abapGit API.

        WARNING: Pull overwrites local ABAP objects with remote versions.
        NOTE: First call may return "Pull status unknown" — call again or press F8 to complete.
        IMPORTANT: All filenames must be lowercase (e.g., zcl_my_class.clas.abap, not uppercase).

        Args:
            repo: Repository name pattern (matched against registered repos)
            trkorr: Transport request (optional, but error if SAP requires it).
                    If pull fails with "Transport required", retry with trkorr.
            username: GitHub username (optional for public repos)
            pat: GitHub Personal Access Token (optional for public repos,
                 falls back to ABAPGIT_PAT or GITHUB_PAT environment variables)

        Returns:
            AbapGitActionResult with success status and details

        Example:
            sap_abapgit_pull(repo="Z_PUBLIC_REPO")
            sap_abapgit_pull(repo="Z_PUBLIC_REPO", trkorr="S4UK902008")
        """
        return await _abapgit_pull_via_api(repo, trkorr, username, pat)

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

        Args:
            program_name: The ABAP program/report name (e.g., Z_REPORT_TEST)

        Returns:
            Dict with success, source_code, program_name, error fields

        Example:
            sap_read_se38_source(program_name="Z_MY_REPORT")
        """
        return await read_se38_source(program_name)
