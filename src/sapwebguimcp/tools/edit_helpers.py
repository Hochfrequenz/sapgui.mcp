"""
Shared helpers for ABAP source code editing (SE38, SE24, SE37).

These helpers handle the common check/activate workflow and status message parsing.
"""

import logging
import re

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Success/error prefixes used in SAP toolbar notes.
# DE: note "Erfolgreich Meldungsleiste <message>"
# EN: note "Success Message Bar <message>"
_SUCCESS_PREFIXES = ("Erfolgreich ", "Success ")
_ERROR_PREFIXES = ("Fehler ", "Error ")

# Regex to strip the prefix + "Meldungsleiste"/"Message Bar" from the note text
_PREFIX_STRIP = re.compile(
    r"^(Erfolgreich|Success|Fehler|Error)\s+(Meldungsleiste|Message Bar)\s+",
)

_SUCCESS_PATTERNS = re.compile(
    r"keine Syntaxfehler|No syntax errors|"
    r"Aktives Objekt wurde generiert|Objekt wurde aktiviert|Object activated|"
    r"generated successfully",
    re.IGNORECASE,
)
_ERROR_PATTERNS = re.compile(
    r"Syntaxfehler|syntax error",
    re.IGNORECASE,
)


def parse_toolbar_note(snapshot_text: str) -> tuple[bool, str]:
    """Parse the toolbar note from an ARIA snapshot to determine success/failure.

    SAP shows status messages as a 'note' element in the toolbar, localized:
      DE: note "Erfolgreich Meldungsleiste <actual message>"
      EN: note "Success Message Bar <actual message>"
      DE: note "Fehler Meldungsleiste <actual message>"
      EN: note "Error Message Bar <actual message>"

    Returns:
        (success, message) tuple.
    """
    match = re.search(r'note\s+"([^"]+)"', snapshot_text)
    if not match:
        return False, "No status message found in toolbar"

    full_note = match.group(1)
    message = _PREFIX_STRIP.sub("", full_note).strip() or full_note

    # Check prefix first — SAP notes start with a localized success/error prefix
    if full_note.startswith(_SUCCESS_PREFIXES):
        return True, message
    if full_note.startswith(_ERROR_PREFIXES):
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
    except (PlaywrightError, OSError) as exc:
        logger.warning("Could not read editor content with selector %s: %s", editor_selector, exc)
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
    except (PlaywrightError, OSError) as exc:
        logger.warning("Failed to replace editor source: %s", exc)
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

    # We snapshot the full body rather than a narrower toolbar locator for reliability:
    # SAP's toolbar structure varies across transactions and screen states, so a targeted
    # locator risks missing the note element. The ~80ms cost is negligible vs. the 2s SAP wait.
    snapshot = await page.locator("body").aria_snapshot()
    check_ok, check_msg = parse_toolbar_note(snapshot)
    messages.append(f"Check: {check_msg}")

    if not check_ok:
        return False, messages, False

    await page.keyboard.press("Control+F3")
    await page.wait_for_timeout(2000)
    await page.wait_for_load_state("networkidle")

    snapshot = await page.locator("body").aria_snapshot()

    # Handle "Inaktive Objekte" / "Inactive Objects" popup (common in SE24 class activation).
    # SAP shows a list of objects to activate and expects Enter (checkmark) to confirm.
    if "Inaktive Objekte" in snapshot or "Inactive Objects" in snapshot:
        logger.info("Detected inactive objects popup, confirming with Enter")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)
        await page.wait_for_load_state("networkidle")
        snapshot = await page.locator("body").aria_snapshot()

    activate_ok, activate_msg = parse_toolbar_note(snapshot)
    messages.append(f"Activate: {activate_msg}")

    return activate_ok, messages, activate_ok
