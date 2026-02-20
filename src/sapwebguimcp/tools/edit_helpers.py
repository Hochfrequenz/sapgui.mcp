"""
Shared helpers for ABAP source code editing (SE38, SE24, SE37).

These helpers handle the common check/activate workflow and status message parsing.
"""

import logging
import re

from playwright.async_api import Page

logger = logging.getLogger(__name__)

_SUCCESS_PATTERNS = re.compile(
    r"Erfolgreich|Successfully|keine Syntaxfehler|No syntax errors|"
    r"Aktives Objekt wurde generiert|generated successfully",
    re.IGNORECASE,
)
_ERROR_PATTERNS = re.compile(
    r"Fehler|Error|Syntaxfehler|syntax error",
    re.IGNORECASE,
)


def parse_toolbar_note(snapshot_text: str) -> tuple[bool, str]:
    """Parse the toolbar note from an ARIA snapshot to determine success/failure.

    The SAP ABAP editor shows status messages as a 'note' element in the toolbar.
    Format: note "Erfolgreich Meldungsleiste <actual message>"
    Or:     note "Fehler Meldungsleiste <actual message>"

    Returns:
        (success, message) tuple.
    """
    match = re.search(r'note\s+"([^"]+)"', snapshot_text)
    if not match:
        return False, "No status message found in toolbar"

    full_note = match.group(1)
    message = re.sub(r"^(Erfolgreich|Fehler)\s+Meldungsleiste\s+", "", full_note).strip()
    if not message:
        message = full_note

    # Check prefix first — SAP notes always start with "Erfolgreich" or "Fehler"
    if full_note.startswith("Erfolgreich "):
        return True, message
    if full_note.startswith("Fehler "):
        return False, message

    # Fallback to pattern search for non-standard messages
    if _SUCCESS_PATTERNS.search(full_note):
        return True, message
    if _ERROR_PATTERNS.search(full_note):
        return False, message
    return False, message


async def read_editor_source(page: Page, editor_selector: str = "textarea[id*='textedit']") -> str | None:
    """Read the current source code from the SAP editor textarea."""
    try:
        textarea = page.locator(editor_selector).first
        if not await textarea.is_visible(timeout=3000):
            return None
        return await textarea.input_value()
    except Exception:
        logger.warning("Could not read editor content with selector %s", editor_selector)
        return None


async def replace_editor_source(page: Page, new_source: str, editor_selector: str = "textarea[id*='textedit']") -> bool:
    """Replace the entire editor content with new source code."""
    try:
        textarea = page.locator(editor_selector).first
        await textarea.click()
        await page.keyboard.press("Control+a")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Delete")
        await page.wait_for_timeout(200)
        await textarea.fill(new_source)
        return True
    except Exception:
        logger.exception("Failed to replace editor source")
        return False


async def check_and_activate(page: Page) -> tuple[bool, list[str], bool]:
    """Run syntax check (Ctrl+F2) and activation (Ctrl+F3) on the current editor.

    Returns:
        (success, messages, activated) tuple.
    """
    messages: list[str] = []

    await page.keyboard.press("Control+F2")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    snapshot = await page.locator("body").aria_snapshot()
    check_ok, check_msg = parse_toolbar_note(snapshot)
    messages.append(f"Check: {check_msg}")

    if not check_ok:
        return False, messages, False

    await page.keyboard.press("Control+F3")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    snapshot = await page.locator("body").aria_snapshot()
    activate_ok, activate_msg = parse_toolbar_note(snapshot)
    messages.append(f"Activate: {activate_msg}")

    return activate_ok, messages, activate_ok
