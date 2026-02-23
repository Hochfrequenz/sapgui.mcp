"""
Shared page-level helpers for session-aware SAP transaction tools.

These helpers operate on an explicit Playwright Page object (from session routing)
rather than calling get_current_page() internally. This ensures multi-session
support works correctly.

Used by dedicated tools (SM37, SLG1, etc.) that thread the session Page through
their entire execution chain.
"""

import logging

from playwright.async_api import Page

from sapwebguimcp.tools.sap_tool_impl import _load_js, _load_js_with_field_utils

logger = logging.getLogger(__name__)

__all__ = [
    "fill_form_on_page",
    "navigate_transaction",
    "read_status_bar",
]


async def navigate_transaction(page: Page, tcode: str) -> str | None:
    """Navigate to a transaction on a specific page. Returns error string or None on success."""
    okcode = await page.query_selector("#ToolbarOkCode")
    if not okcode or not await okcode.is_visible():
        for selector in ["input[id*='OkCode']", "input[lsdata*='OKCODE']"]:
            okcode = await page.query_selector(selector)
            if okcode and await okcode.is_visible():
                break
        else:
            return f"OK-Code field not found for transaction {tcode}"

    await page.bring_to_front()
    await page.wait_for_timeout(500)
    await okcode.click()
    await page.wait_for_timeout(200)
    await page.evaluate(_load_js("set_okcode_field.js"), {"transactionInput": f"/n{tcode}"})
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("networkidle", timeout=15000)
    return None


async def fill_form_on_page(page: Page, fields: dict[str, str]) -> list[str]:
    """Fill form fields on a specific page. Returns list of field names not found."""
    result = await page.evaluate(
        _load_js_with_field_utils("fill_form_fields.js"),
        {"fields": fields},
    )
    not_found: list[str] = result.get("notFound", [])
    return not_found


async def read_status_bar(page: Page) -> tuple[str, str]:
    """Read the SAP status bar on a specific page. Returns (type, message)."""
    try:
        status_info = await page.evaluate(_load_js("extract_status_bar.js"))
        return status_info.get("type", "none"), status_info.get("message", "")
    except Exception:  # pylint: disable=broad-exception-caught
        return "none", ""
