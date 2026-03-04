"""
Standalone SAP tool implementations for use in MCP tools.

This module contains the core logic for SAP operations, extracted as
standalone async functions used by MCP-registered tools (in sap_tools.py).

The functions follow a consistent pattern:
- Accept typed parameters
- Return Pydantic result models
- Handle errors gracefully with Result.failure()
"""

import logging
from typing import Any

from sapwebguimcp.backend.webgui.js_helpers import load_js as _load_js
from sapwebguimcp.backend.webgui.js_helpers import (
    load_js_with_field_utils as _load_js_with_field_utils,
)
from sapwebguimcp.models import (
    FieldFillError,
    FillFormResult,
    KeyboardResult,
    ScreenInfo,
    ScreenText,
    StatusBarInfo,
    TransactionResult,
    get_browser_manager,
)
from sapwebguimcp.utils import is_sap_shortcut

__all__ = [
    "_load_js",
    "_load_js_with_field_utils",
    "sap_transaction_impl",
    "sap_keyboard_impl",
    "sap_fill_form_impl",
    "sap_read_status_bar_impl",
    "sap_get_screen_text_impl",
    "sap_get_screen_info_impl",
]

logger = logging.getLogger(__name__)


async def _find_okcode_field(page: Any) -> Any | None:
    """Find the OK-Code field on the page."""
    # Try the standard ID first
    element = await page.query_selector("#ToolbarOkCode")
    if element and await element.is_visible():
        return element

    # Try alternative selectors
    for selector in [
        "input[id*='OkCode']",
        "input[lsdata*='OKCODE']",
        "#M0\\:46\\:11\\:1",  # Common dynamic ID pattern
    ]:
        element = await page.query_selector(selector)
        if element and await element.is_visible():
            return element

    return None


async def _enable_okcode_field(page: Any) -> tuple[bool, str]:
    """
    Attempt to enable the OK-Code field via SAP settings menu.

    Returns:
        (success, message) tuple
    """
    try:
        # Look for settings/gear icon
        settings_selectors = [
            "span[title*='Einstellungen']",
            "span[title*='Settings']",
            "[lsdata*='SETTINGS']",
            "span.urBtnEmph[title]",
        ]

        for selector in settings_selectors:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                await element.click()
                await page.wait_for_timeout(500)

                # Look for OK-Code option in menu
                okcode_options = [
                    "text=OK-Code",
                    "text=Transaktionsfeld",
                    "text=Transaction Field",
                ]
                for option_selector in okcode_options:
                    option = await page.query_selector(option_selector)
                    if option and await option.is_visible():
                        await option.click()
                        await page.wait_for_timeout(300)
                        return True, "Enabled OK-Code field via settings menu"

        return False, "Could not find settings menu or OK-Code option"

    except Exception as e:  # pylint: disable=broad-exception-caught
        return False, f"Error enabling OK-Code field: {e}"


async def sap_transaction_impl(tcode: str, new_window: bool = False) -> TransactionResult:
    """
    Enter and execute an SAP transaction code.

    Args:
        tcode: Transaction code (e.g., VA01, MM03, SE80, SU01)
        new_window: If True, open in new SAP session window (preserves current transaction)

    Returns:
        TransactionResult indicating success or describing any issues.
    """
    browser_manager = await get_browser_manager()
    page = await browser_manager.get_current_page()

    try:
        # Step 1: Check if OK-Code field exists
        okcode_field = await _find_okcode_field(page)

        if not okcode_field:
            logger.info("OK-Code field not found, enabling it")
            success, message = await _enable_okcode_field(page)
            logger.info("OK-Code field enabled", extra={"success": success, "result_message": message})

            if not success:
                return TransactionResult.failure(
                    f"Could not find or enable OK-Code field. {message}",
                    tcode=tcode,
                )

            okcode_field = await _find_okcode_field(page)
            if not okcode_field:
                return TransactionResult.failure(
                    f"OK-Code field still not visible after enabling. {message}",
                    tcode=tcode,
                )

        # Step 2: Build transaction code with prefix
        prefix = "/o" if new_window else "/n"
        if tcode.startswith("/n") or tcode.startswith("/o"):
            transaction_input = tcode
        else:
            transaction_input = f"{prefix}{tcode}"

        # Step 3: Execute transaction
        await page.bring_to_front()
        await page.wait_for_timeout(500)

        logger.info("Entering transaction", extra={"tcode": transaction_input})

        await okcode_field.click()
        await page.wait_for_timeout(200)

        await page.evaluate(
            _load_js("set_okcode_field.js"),
            {"transactionInput": transaction_input},
        )

        await page.wait_for_timeout(300)
        await page.keyboard.press("Enter")
        await page.wait_for_load_state("networkidle", timeout=15000)

        title = await page.title()

        if new_window:
            context = page.context
            pages = context.pages
            session_count = len(pages)
            return TransactionResult(
                tcode=tcode,
                page_title=title,
                new_window=True,
                session_count=session_count,
            )

        return TransactionResult(
            tcode=tcode,
            page_title=title,
            new_window=False,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Executing transaction")
        return TransactionResult.failure(f"Error executing transaction {tcode}: {e}", tcode=tcode)


async def sap_keyboard_impl(key: str) -> KeyboardResult:
    """
    Send a keyboard shortcut to SAP Web GUI.

    Args:
        key: Keyboard shortcut. Use "Ctrl+", "Shift+", "Alt+" prefixes for modifiers.

    Returns:
        KeyboardResult with the key sent, page title, and status bar (for shortcuts).
    """
    browser_manager = await get_browser_manager()

    try:
        page = await browser_manager.get_current_page()

        await page.bring_to_front()
        await page.wait_for_timeout(100)

        await page.keyboard.press(key)
        await page.wait_for_load_state("networkidle", timeout=15000)

        title = await page.title()

        # Auto-read status bar for shortcuts (F-keys or Ctrl+*)
        if is_sap_shortcut(key):
            try:
                status_info = await page.evaluate(_load_js("extract_status_bar.js"))
                return KeyboardResult(
                    key=key,
                    page_title=title,
                    status_bar_read=True,
                    status_bar_type=status_info.get("type", "none"),
                    status_bar_message=status_info.get("message", ""),
                )
            except Exception:  # pylint: disable=broad-exception-caught
                return KeyboardResult(
                    key=key,
                    page_title=title,
                    status_bar_read=False,
                )

        return KeyboardResult(key=key, page_title=title)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Sending keyboard shortcut")
        return KeyboardResult.failure(f"Error sending keyboard shortcut {key}: {e}", key=key)


async def sap_fill_form_impl(fields: dict[str, str], strict: bool = False) -> FillFormResult:
    """
    Fill multiple SAP form fields in a single call.

    Args:
        fields: Dictionary mapping field identifiers to values.
        strict: If True, fail if any field is not found.

    Returns:
        FillFormResult with lists of filled, not_found, and errored fields.
    """
    if not fields:
        return FillFormResult.failure("fields cannot be empty")

    browser_manager = await get_browser_manager()

    try:
        page = await browser_manager.get_current_page()

        result = await page.evaluate(
            _load_js_with_field_utils("fill_form_fields.js"),
            {"fields": fields},
        )

        filled = result.get("filled", [])
        not_found = result.get("notFound", [])
        # Handle ambiguous labels as errors
        errors = [FieldFillError(field=a["field"], error=a["error"]) for a in result.get("ambiguous", [])]
        errors.extend(FieldFillError(field=e["field"], error=e["error"]) for e in result.get("errors", []))

        debug_info = result.get("debug", [])
        if debug_info:
            logger.debug("Fill form debug info", extra={"debug_info": debug_info})

        if strict and not_found:
            return FillFormResult.failure(
                f"Fields not found: {', '.join(not_found)}",
                filled=filled,
                not_found=not_found,
                errors=errors,
            )

        return FillFormResult(filled=filled, not_found=not_found, errors=errors)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Filling form fields")
        return FillFormResult.failure(f"Error filling form fields: {e}")


async def sap_read_status_bar_impl() -> StatusBarInfo:
    """
    Read the current message from SAP's status bar.

    Returns:
        StatusBarInfo with type and message.
    """
    browser_manager = await get_browser_manager()

    try:
        page = await browser_manager.get_current_page()
        status_info = await page.evaluate(_load_js("extract_status_bar.js"))

        return StatusBarInfo(
            type=status_info.get("type", "none"),
            message=status_info.get("message", ""),
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Reading status bar")
        return StatusBarInfo.failure(f"Error reading status bar: {e}", type="none")


async def sap_get_screen_text_impl() -> ScreenText:
    """
    Get all readable text from the current SAP screen.

    Returns:
        ScreenText with the extracted text content.
    """
    browser_manager = await get_browser_manager()

    try:
        page = await browser_manager.get_current_page()
        result = await page.evaluate(_load_js("extract_screen_text.js"))

        return ScreenText(
            title=result.get("title", ""),
            status_bar=result.get("statusBar") or None,
            tabs=result.get("tabs", []),
            labels=result.get("labels", []),
            buttons=result.get("buttons", []),
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Extracting screen text")
        return ScreenText.failure(f"Error extracting screen text: {e}")


async def sap_get_screen_info_impl() -> ScreenInfo:
    """
    Get technical information about the current SAP screen.

    Returns:
        ScreenInfo with transaction, title, url, program, and dynpro.
    """
    browser_manager = await get_browser_manager()

    try:
        page = await browser_manager.get_current_page()
        screen_info = await page.evaluate(_load_js("extract_screen_info.js"))

        return ScreenInfo(
            transaction=screen_info.get("transaction"),
            title=screen_info.get("title", ""),
            url=screen_info.get("url", ""),
            program=screen_info.get("program"),
            dynpro=screen_info.get("dynpro"),
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Getting screen info")
        return ScreenInfo.failure(f"Error getting screen info: {e}", title="", url="")
