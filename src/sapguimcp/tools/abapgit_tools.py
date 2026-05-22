# pylint: disable=too-many-lines
"""
abapGit integration tools for SAP (WebGUI and desktop backends).

This module provides:
- List: Enumerate all registered abapGit repositories and their metadata
- Pull: Fetch and apply changes from a remote git repository via Z_ABAPGIT_PULL_MCP
- SE38 Verification: Read ABAP report source code to verify pulls

The pull operation uses the Z_ABAPGIT_PULL_MCP transaction which calls the abapGit
ABAP API directly, avoiding fragile UI automation. The ABAP report source is
maintained in:
  https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT/blob/main/src/z_abapgit_pull_mcp_shortcut.prog.abap

If the Z_ABAPGIT_PULL_MCP transaction is not found, you need to create it in SAP.
The tool will provide a link to the source code.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.models.abapgit_models import AbapGitActionResult, AbapGitListResult, AbapGitRepoInfo
from sapguimcp.models.config import get_settings

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


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
                    "User-Agent": "sapgui-mcp",
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


# Helper Data Structures


@dataclass
class PullParams:
    """Parameters for pull operation after validation."""

    repo: str
    trkorr: str | None
    username: str | None
    pat: str | None
    tcode_with_params: str


# Error Detection Helpers

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

# Additional transport-related patterns beyond ERROR_PATTERNS above.
# Keep in sync: ERROR_PATTERNS covers "transport required" / "transport erforderlich"
# for generic error detection; this list adds patterns for the enrichment check.
_TRANSPORT_REQUIRED_PATTERNS = (
    "transport required",
    "transport erforderlich",
    "provide p_trkorr",
    "p_trkorr=",
    "transportauftrag",
)

_TRANSPORT_REQUIRED_GUIDANCE = (
    "A transport request (TRKORR) is required for this pull. "
    "Look up an open transport request (e.g. via SE09/SE10) and "
    "retry: sap_abapgit_pull(repo=..., trkorr='<TRKORR>')"
)

_NO_TASK_PATTERNS = (
    "no modifiable task",
    "keine modifizierbare aufgabe",
    "has no task",
    "keine aufgabe",
)

_NO_TASK_GUIDANCE = (
    "The logged-in user has no modifiable task (Aufgabe) in the specified transport. "
    "Create a task under this transport in SE09, or use a different transport "
    "where you have a modifiable task."
)


def _is_transport_required_error(error_text: str) -> bool:
    """Check if an error message indicates a transport request is required."""
    lower = error_text.lower()
    return any(pattern in lower for pattern in _TRANSPORT_REQUIRED_PATTERNS)


def _is_no_task_error(error_text: str) -> bool:
    """Check if an error message indicates the user has no task in the transport."""
    lower = error_text.lower()
    return any(pattern in lower for pattern in _NO_TASK_PATTERNS)


def _enrich_transport_error(error_text: str) -> str:
    """If the error is transport-related, append actionable guidance."""
    if _is_transport_required_error(error_text):
        return f"{error_text.rstrip('. ')}. {_TRANSPORT_REQUIRED_GUIDANCE}"
    if _is_no_task_error(error_text):
        return f"{error_text.rstrip('. ')}. {_NO_TASK_GUIDANCE}"
    return error_text


async def _check_for_error_popup(backend: "WebGuiBackend | DesktopBackend") -> str | None:
    """Check for SAP error popup dialog and extract message text."""
    try:
        if backend.backend_type == "desktop":
            text = await _check_for_error_popup_desktop(backend)
        else:
            text = await _check_for_error_popup_webgui(cast("WebGuiBackend", backend))
        if not text:
            return None
        text_lower = text.lower()
        if not any(keyword in text_lower for keyword in ERROR_KEYWORDS):
            return None
        lines = text.split("\n")
        message_lines = [
            line.strip()
            for line in lines
            if line.strip() and line.strip().lower() not in ("ok", "cancel", "abbrechen", "ja", "nein", "yes", "no")
        ]
        if message_lines:
            logger.info("Found error popup", extra={"popup_message": message_lines[0]})
            return " ".join(message_lines)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("Checking for popup", extra={"error": str(e)})
    return None


async def _check_for_error_popup_webgui(backend: "WebGuiBackend") -> str | None:
    """Check for error popup via JavaScript (WebGUI only)."""
    js_code = """
    () => {
        const selectors = [
            '.urMessageBox', '.urPopup', '[id*="PopupWindow"]',
            '[id*="ModalWindow"]', '.lsPopup', '[role="alertdialog"]',
            '.urMsgArea', '#MESSAGE_POPUP', '[id*="MESSAGE"]'
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const text = (el.innerText || '').trim();
            if (!text) continue;
            return text;
        }
        return null;
    }
    """
    result: str | None = await backend.evaluate_javascript(js_code)
    return result


async def _check_for_error_popup_desktop(backend: "WebGuiBackend | DesktopBackend") -> str | None:
    """Check for error popup via check_popup (desktop backend)."""
    popup = await backend.check_popup()
    if popup is None:
        return None
    return popup.message


async def _check_screen_for_errors(backend: "WebGuiBackend | DesktopBackend") -> str | None:
    """Check the entire screen for error indicators as a fallback."""
    try:
        if backend.backend_type == "desktop":
            snapshot = await backend.get_snapshot()
            body_text = str(snapshot)
        else:
            body_text = await cast("WebGuiBackend", backend).evaluate_javascript("() => document.body.innerText || ''")
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


# Pull Parameter Validation


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

    tcode_with_params = f"/nZ_ABAPGIT_PULL_MCP {'; '.join(params)};"

    return PullParams(
        repo=repo,
        trkorr=trkorr,
        username=effective_username,
        pat=effective_pat,
        tcode_with_params=tcode_with_params,
    )


# OK-Code Field Handling — delegates to backend.enter_transaction()


async def _enter_tcode_via_okcode(
    backend: "WebGuiBackend | DesktopBackend", tcode_with_params: str, repo: str
) -> AbapGitActionResult | None:
    """Enter a parameterised transaction via the OK-Code field. Returns error or None."""
    result = await backend.enter_transaction(tcode_with_params)
    if not result.success:
        return AbapGitActionResult.failure_result(
            action="pull",
            repo_name=repo,
            error=result.error or "Failed to enter transaction via OK-Code field",
        )
    return None


# Pull Result Analysis


async def _analyze_pull_result(backend: "WebGuiBackend | DesktopBackend", repo: str) -> AbapGitActionResult:
    """Analyze status bar and screen to determine pull result."""
    status = await backend.get_status_bar()
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
        return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=_enrich_transport_error(msg))

    # Retry status bar read
    await backend.wait(2000)
    status = await backend.get_status_bar()
    final_msg = status.message or msg
    final_type = status.type or msg_type
    final_lower = final_msg.lower()
    logger.info("Final status check", extra={"status_type": final_type, "status_message": final_msg})

    # Check final status
    is_final_success = "pull successful" in final_lower
    is_final_error = final_type in ("E", "A")
    screen_error = None if final_msg and final_type != "none" else await _check_screen_for_errors(backend)

    if is_final_success:
        return AbapGitActionResult.success_result(action="pull", repo_name=repo, message=final_msg)
    if is_final_error or screen_error:
        return AbapGitActionResult.failure_result(
            action="pull", repo_name=repo, error=_enrich_transport_error(screen_error or final_msg)
        )

    # Treat ambiguous result based on whether we got any status message.
    # Empty status bar may mask auth errors (expired PAT -> cx_root in ABAP).
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


# Main Pull Implementation


async def _handle_popup_error(backend: "WebGuiBackend | DesktopBackend", repo: str) -> AbapGitActionResult | None:
    """Check for error popup and return failure if found, None otherwise."""
    popup_error = await _check_for_error_popup(backend)
    if popup_error:
        await backend.press_key("Enter")
        await backend.wait(500)
        return AbapGitActionResult.failure_result(
            action="pull", repo_name=repo, error=_enrich_transport_error(popup_error)
        )
    return None


async def _execute_pull_transaction(
    backend: "WebGuiBackend | DesktopBackend", params: PullParams, repo: str
) -> AbapGitActionResult | None:
    """Execute pull transaction and return failure result if error, None if OK to continue."""
    okcode_error = await _enter_tcode_via_okcode(backend, params.tcode_with_params, repo)
    if okcode_error:
        return okcode_error

    # Check if transaction was found
    status = await backend.get_status_bar()
    status_msg = (status.message or "").lower()
    tx_not_found = "not found" in status_msg or "existiert nicht" in status_msg or "does not exist" in status_msg
    if tx_not_found:
        return AbapGitActionResult.failure_result(
            action="pull",
            repo_name=repo,
            error=(
                "Transaction Z_ABAPGIT_PULL_MCP not found. Create this transaction in your SAP system. "
                "See https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT for the ABAP source code."
            ),
        )
    return None


async def _run_pull_and_check_errors(
    backend: "WebGuiBackend | DesktopBackend", repo: str
) -> AbapGitActionResult | None:
    """Execute F8 and wait for SAP to finish processing. Returns error if found."""
    await backend.press_key("F8")

    # Fast-fail: check for immediate error popups (bad transport, auth error)
    await backend.wait(2000)
    popup_result = await _handle_popup_error(backend, repo)
    if popup_result:
        return popup_result

    # Wait for deserialization to finish (networkidle = 500ms with no requests).
    try:
        await backend.wait_for_ready(timeout_ms=120_000)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("networkidle timeout after F8 -- pull may still be running")

    # SAP may show an "Inaktive Objekte" / "Inactive Objects" popup after pull.
    # Detect via check_popup() instead of parsing snapshot text.
    popup = await backend.check_popup()
    if popup and popup.message:
        msg_lower = popup.message.lower()
        if "inaktive objekte" in msg_lower or "inactive objects" in msg_lower:
            logger.info("Detected inactive objects popup, confirming with Enter")
            await backend.press_key("Enter")
            await backend.wait(2000)
            try:
                await backend.wait_for_ready(timeout_ms=30_000)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    return await _handle_popup_error(backend, repo)


def _clean_timestamp(value: str) -> str | None:
    """Return None for empty or initial ABAP TIMESTAMPL values (all zeros)."""
    if not value or value.replace("0", "").replace(".", "") == "":
        return None
    return value


def parse_repo_list_output(raw_output: str) -> list[AbapGitRepoInfo]:
    """Parse tilde-delimited WRITE output from Z_ABAPGIT_PULL_MCP_SHORTCUT LIST mode.

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


async def _abapgit_list_repos(backend: "WebGuiBackend | DesktopBackend") -> AbapGitListResult:
    """List all registered abapGit repositories via Z_ABAPGIT_PULL_MCP P_ACTION=LIST."""
    logger.info("Listing abapGit repositories")

    try:
        tcode_with_params = "/nZ_ABAPGIT_PULL_MCP P_ACTION=LIST;"
        okcode_error = await _enter_tcode_via_okcode(backend, tcode_with_params, "LIST")
        if okcode_error:
            return AbapGitListResult(success=False, error=okcode_error.error or "Failed to enter transaction")

        # Check if transaction was found
        status = await backend.get_status_bar()
        status_msg = (status.message or "").lower()
        if "not found" in status_msg or "existiert nicht" in status_msg or "does not exist" in status_msg:
            return AbapGitListResult(
                success=False,
                error=(
                    "Transaction Z_ABAPGIT_PULL_MCP not found. "
                    "Ensure the report is deployed with LIST support. "
                    "See https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT"
                ),
            )

        # Execute report with F8
        await backend.press_key("F8")
        await backend.wait(3000)

        # Read the WRITE output from the screen
        if backend.backend_type == "desktop":
            # On the desktop backend, WRITE output appears as labels (GuiLabel)
            screen = await backend.get_screen_text()
            all_text = (screen.labels or []) + (screen.main_content or [])
            raw_output = "\n".join(all_text)
        else:
            raw_output = await cast("WebGuiBackend", backend).evaluate_javascript("""
                () => {
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
    backend: "WebGuiBackend | DesktopBackend",
    repo: str,
    trkorr: str | None,
    username: str | None,
    pat: str | None,
) -> AbapGitActionResult:
    """Pull changes using the Z_ABAPGIT_PULL_MCP transaction (abapGit ABAP API)."""
    logger.info("Starting abapGit Pull via API", extra={"repo": repo})

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
        tx_error = await _execute_pull_transaction(backend, params, repo)
        if tx_error:
            return tx_error

        # Run pull and check for popup errors
        popup_error = await _run_pull_and_check_errors(backend, repo)
        if popup_error:
            return popup_error

        return await _analyze_pull_result(backend, repo)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("abapGit pull via API", extra={"repo": repo})
        return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=str(e))


# =============================================================================
# SE38 Verification
# =============================================================================


async def _fill_se38_program_field(backend: "WebGuiBackend", program_name: str) -> bool:
    """Fill the program name field in SE38 using various strategies."""
    input_selectors = [
        "input[name*='PROGRAM']",
        "input[id*='PROGRAM']",
        "input[maxlength='40']",
        "#M0\\:46\\:1\\:1\\:\\:0\\:12",
    ]

    for selector in input_selectors:
        try:
            filled = await backend.fill_element_by_locator(selector, program_name, delay_ms=30)
            if filled:
                logger.info("Filled program name", extra={"selector": selector})
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue

    # Try backend.fill_form as fallback
    try:
        fill_result = await backend.fill_form({"Programm": program_name, "Program": program_name})
        if not fill_result.not_found or len(fill_result.not_found) < 2:
            logger.info("Filled program name using backend.fill_form")
            return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("backend.fill_form fallback failed", extra={"error": str(e)})

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


async def _navigate_to_se38(backend: "WebGuiBackend") -> str | None:
    """Navigate to SE38 and return error message if failed, None if OK."""
    await backend.bring_to_front()
    await backend.press_key("Escape")
    await backend.wait(500)
    await backend.press_key("F3")
    await backend.wait(3000)

    # Check if OK-Code field is visible; if not, press F3 again
    ok_code_visible = await backend.evaluate_javascript("""
        () => {
            const el = document.querySelector('#ToolbarOkCode');
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden';
        }
    """)
    if not ok_code_visible:
        await backend.press_key("F3")
        await backend.wait(3000)

    tx_result = await backend.enter_transaction("SE38")
    return None if tx_result.success else f"Failed to open SE38: {tx_result.error}"


async def _find_source_code(backend: "WebGuiBackend") -> str | None:
    """Try various methods to find ABAP source code on the page via JavaScript."""
    # Single comprehensive JS that searches SE38 selectors, editor elements,
    # iframes, table cells, and text nodes — mirrors the old multi-function approach.
    js_code = """
    () => {
        const ABAP_PATTERNS = [
            "WRITE '", 'WRITE "', 'WRITE:', 'DATA:', 'TYPES:',
            'ENDMETHOD', 'ENDCLASS', 'ENDLOOP', 'ENDIF', 'ENDFORM',
            'FORM ', 'METHOD ', 'CLASS '
        ];
        const CODE_PATTERNS = ['REPORT ', 'WRITE ', 'DATA ', 'IF ', 'LOOP ', 'ENDLOOP'];
        function isAbapSource(text) {
            if (!text || text.length < 20) return false;
            const upper = text.toUpperCase();
            return ABAP_PATTERNS.some(p => upper.includes(p)) ||
                   /REPORT\\s+(\\/[A-Z0-9_]+\\/)?[A-Z][A-Z0-9_]*\\s*\\./.test(upper);
        }

        function getTextFromEl(el) {
            try {
                return (el.innerText || el.textContent || el.value || '').trim();
            } catch(e) { return ''; }
        }

        // 1. Direct SE38 selectors
        const se38Sels = [
            '#textedit\\\\#TEC_cnt42',
            "[id^='textedit'][id*='TEC_cnt']",
            "textarea[id*='textedit']",
            "[id*='TEC_cnt']"
        ];
        for (const sel of se38Sels) {
            try {
                const el = document.querySelector(sel);
                if (!el) continue;
                let text = getTextFromEl(el);
                if (!text || text.length < 20) {
                    text = el.value || el.textContent || el.innerText || '';
                }
                if (text && text.length > 20 && isAbapSource(text)) return text;
            } catch(e) {}
        }

        // 2. Editor selectors in main document
        const editorSels = [
            'textarea', '.ace_editor', '.ace_content', '.urPTxt', 'pre', 'code',
            '.editor-content', "[id*='editor']", "[class*='editor']",
            "[class*='source']", "[class*='code']", '.lsListbox__list',
            'table.urST', '#sapwd_main_window_root_contents table'
        ];
        for (const sel of editorSels) {
            try {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const text = getTextFromEl(el);
                    if (isAbapSource(text)) return text;
                }
            } catch(e) {}
        }

        // 3. Table cells for code lines
        try {
            const cells = document.querySelectorAll('td');
            const codeLines = [];
            for (const cell of cells) {
                const text = (cell.innerText || '').trim();
                if (text && text.length > 5) {
                    const upper = text.toUpperCase();
                    if (upper.includes("WRITE '") || upper.includes('WRITE "') ||
                        (upper.includes('REPORT ') && text.includes('.')) ||
                        upper.includes('ENDLOOP') || upper.includes('ENDIF') ||
                        upper.includes('ENDFORM') || upper.includes('ENDMETHOD')) {
                        codeLines.push(text);
                    }
                }
            }
            if (codeLines.length > 0) return codeLines.join('\\n');
        } catch(e) {}

        // 4. Iframes
        const iframes = document.querySelectorAll('iframe');
        for (const iframe of iframes) {
            try {
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (!doc || !doc.body) continue;
                const frameSels = ['textarea', '.ace_editor', '.editor-content', 'pre', '.urPTxt'];
                for (const sel of frameSels) {
                    const els = doc.querySelectorAll(sel);
                    for (const el of els) {
                        const text = getTextFromEl(el);
                        if (isAbapSource(text)) return text;
                    }
                }
                const bodyText = (doc.body.innerText || '').trim();
                if (isAbapSource(bodyText)) return bodyText;
            } catch(e) {}
        }

        // 5. Text node walk (fallback)
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
        let allTexts = getTextNodes(document.body);
        for (const iframe of iframes) {
            try {
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (doc && doc.body) allTexts = allTexts.concat(getTextNodes(doc.body));
            } catch(e) {}
        }
        const codeTexts = allTexts.filter(text => {
            const upper = text.toUpperCase();
            return CODE_PATTERNS.some(p => upper.includes(p));
        });
        if (codeTexts.length > 0) return codeTexts.sort((a, b) => b.length - a.length)[0];

        return null;
    }
    """
    try:
        logger.info("Searching for ABAP source code via JavaScript")
        result = await backend.evaluate_javascript(js_code)
        if result and _is_actual_abap_source(result):
            source: str = result
            logger.info("Found ABAP source code", extra={"chars": len(source)})
            return source
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.debug("JavaScript source search failed", extra={"error": str(e)})
    return None


async def read_se38_source(backend: "WebGuiBackend", program_name: str) -> dict[str, Any]:
    """Read ABAP report source code from SE38."""
    try:
        nav_error = await _navigate_to_se38(backend)
        if nav_error:
            return {"success": False, "error": nav_error}

        await backend.wait(2000)
        if not await _fill_se38_program_field(backend, program_name):
            return {"success": False, "error": "Could not find program input field"}

        # Press F7 (Display) and handle entry screen
        logger.info("Pressing F7 to display source code")
        await backend.press_key("F7")
        await backend.wait(3000)

        page_title = await backend.get_page_title()
        logger.info("Page title after F7", extra={"title": page_title})
        if "Einstieg" in page_title or "Entry" in page_title:
            await backend.press_key("Enter")
            await backend.wait(2000)
            title_after_enter = await backend.get_page_title()
            if "Einstieg" in title_after_enter or "Entry" in title_after_enter:
                await backend.press_key("F8")
                await backend.wait(3000)

        await backend.wait(1000)
        source_code = await _find_source_code(backend)

        if source_code:
            logger.info("Found valid ABAP source code", extra={"chars": len(source_code)})
            return {"success": True, "source_code": source_code, "program_name": program_name}

        logger.warning("No ABAP source code found, returning body text")
        body_text = await backend.evaluate_javascript("() => document.body.innerText || ''")
        return {
            "success": True,
            "source_code": (body_text or "")[:3000],
            "program_name": program_name,
            "debug_note": "No ABAP source patterns detected, returning raw body text",
        }

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("SE38 read failed", extra={"error_type": type(e).__name__, "error": str(e)})
        return {"success": False, "error": str(e)}


async def verify_abap_report_content(backend: "WebGuiBackend", program_name: str, expected_text: str) -> dict[str, Any]:
    """Verify that an ABAP report contains expected text."""
    result = await read_se38_source(backend, program_name)

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
    async def sap_abapgit_list_repos(
        session: str | None = None,
        agent_id: str | None = None,
    ) -> AbapGitListResult:
        """
        List all registered abapGit repositories.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            AbapGitListResult with list of AbapGitRepoInfo objects

        Example:
            sap_abapgit_list_repos()
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_abapgit_list_repos")
        except ValueError as e:
            return AbapGitListResult(success=False, error=f"Session error: {e}")
        return await _abapgit_list_repos(backend)

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
            "WARNING: This overwrites local ABAP objects with remote versions. "
            "If SAP requires a transport request, the tool returns an error with guidance. "
            "Look up an open transport (e.g. via SE09/SE10), then retry with trkorr=... "
            "If the tool reports 'status unknown', the pull may have succeeded. "
            "Call sap_read_status_bar() to check, or retry with sap_press_key('F8') "
            "then sap_read_status_bar()."
        ),
    )
    async def sap_abapgit_pull(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        repo: str,
        trkorr: str | None = None,
        username: str | None = None,
        pat: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> AbapGitActionResult:
        """
        Pull changes from a remote git repository using abapGit API.

        WARNING: Pull overwrites local ABAP objects with remote versions.
        NOTE: First call may return "Pull status unknown" -- call again or press F8 to complete.
        IMPORTANT: All filenames must be lowercase (e.g., zcl_my_class.clas.abap, not uppercase).

        Args:
            repo: Repository name pattern (matched against registered repos)
            trkorr: Transport request (optional, but error if SAP requires it).
                    If pull fails with "Transport required", retry with trkorr.
            username: GitHub username (optional for public repos)
            pat: GitHub Personal Access Token (optional for public repos).
                 Falls back to ABAPGIT_PAT env var, then GITHUB_PAT.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            AbapGitActionResult with success status and details

        Example:
            sap_abapgit_pull(repo="Z_PUBLIC_REPO")
            sap_abapgit_pull(repo="Z_PUBLIC_REPO", trkorr="S4UK902008")
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_abapgit_pull")
        except ValueError as e:
            return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=f"Session error: {e}")
        return await _abapgit_pull_via_api(backend, repo, trkorr, username, pat)

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
            "If sap-adt is available, prefer its get_source tool. "
            "Navigates to SE38, enters the program name, and displays the source code. "
            "Useful for verifying abapGit pull operations."
        ),
    )
    async def sap_read_se38_source(
        program_name: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Read ABAP report source code from SE38.

        Args:
            program_name: The ABAP program/report name (e.g., Z_REPORT_TEST)
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            Dict with success, source_code, program_name, error fields

        Example:
            sap_read_se38_source(program_name="Z_MY_REPORT")
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_read_se38_source")
        except ValueError as e:
            return {"success": False, "error": f"Session error: {e}"}
        if backend.backend_type == "desktop":
            return {
                "success": False,
                "error": "sap_read_se38_source is not supported on the desktop backend. "
                "Use sap_se38_edit to open the report in SE38 instead.",
            }
        from sapguimcp.backend.webgui.backend import WebGuiBackend  # pylint: disable=import-outside-toplevel

        assert isinstance(backend, WebGuiBackend)
        return await read_se38_source(backend, program_name)
