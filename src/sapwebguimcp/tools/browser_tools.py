"""
Browser automation MCP tools (escape hatches).

This module contains generic browser automation tools that can be used
when SAP-specific tools are insufficient:
- browser_snapshot: Get accessibility tree
- browser_screenshot: Take screenshots
- browser_click: Click elements
- browser_fill: Fill input fields
- browser_keyboard: Send keyboard input
- browser_navigate: Navigate to URLs
- browser_evaluate: Execute JavaScript
- browser_wait: Wait for elements/time
- browser_get_html: Get HTML content
- browser_select_option: Select dropdown options
"""

import json
import logging
from datetime import timedelta
from typing import Literal, Optional

from fastmcp import FastMCP
from fastmcp.utilities.types import File, Image

from sapwebguimcp.models import (
    BrowserKeyboardResult,
    ClickResult,
    EvaluateResult,
    FillResult,
    HtmlResult,
    NavigateResult,
    ScreenshotResult,
    SelectOptionResult,
    SnapshotResult,
    WaitResult,
    get_browser_manager,
)

__all__ = ["register_browser_tools"]

logger = logging.getLogger(__name__)

# Threshold for returning HTML as File instead of inline (50KB)
# This prevents context bloat for large SAP pages
_HTML_SIZE_THRESHOLD_BYTES = 50 * 1024


def _escape_css_selector(selector: str) -> str:
    """
    Escape special CSS characters in selectors.

    SAP generates IDs like 'M0:48::btn[5]' which contain special CSS characters.
    This function escapes them so they work as valid CSS selectors.

    If the selector is already escaped (contains patterns like \\# or \\,),
    it will be returned as-is to avoid double-escaping.

    Args:
        selector: CSS selector string

    Returns:
        Escaped CSS selector
    """
    if not selector:
        return selector

    # If it's an ID selector (starts with #), escape special chars in the ID part
    if selector.startswith("#"):
        id_part = selector[1:]

        # Check if already escaped - look for backslash followed by special chars
        # This prevents double-escaping of selectors from sap_read_table cells
        if any(f"\\{c}" in id_part for c in ":[]#,"):
            return selector  # Already escaped

        # Escape CSS special characters: : [ ] # ,
        # SAP ALV grids use IDs like "grid#C120#1,2#if" which need # and , escaped
        escaped_id = ""
        for char in id_part:
            if char in r":[]#,":
                escaped_id += f"\\{char}"
            else:
                escaped_id += char
        return f"#{escaped_id}"

    return selector


def register_browser_tools(mcp: FastMCP) -> None:  # pylint: disable=too-many-statements
    """Register all browser automation tools with the MCP server."""

    @mcp.tool(
        description=(
            "Get accessibility tree snapshot of the current page. "
            "Returns a YAML representation of the ARIA tree - useful for understanding "
            "page structure when other tools fail. "
            "Args: selector = optional CSS selector to scope the snapshot."
        )
    )
    async def browser_snapshot(  # pylint: disable=missing-function-docstring
        selector: Optional[str] = None,
    ) -> SnapshotResult:
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        try:
            if selector:
                escaped_selector = _escape_css_selector(selector)
                locator = page.locator(escaped_selector)
                if await locator.count() > 0:
                    snapshot = await locator.first.aria_snapshot()
                else:
                    return SnapshotResult.failure(f"Element not found: {selector}", selector=selector)
            else:
                snapshot = await page.locator("body").aria_snapshot()

            return SnapshotResult(snapshot=snapshot, selector=selector)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting snapshot")
            return SnapshotResult.failure(f"Error getting snapshot: {e}", selector=selector)

    @mcp.tool(
        description=(
            "Take a screenshot of the current page. "
            "AVOID THIS TOOL - it returns a large image that fills up conversation context. "
            "Use browser_snapshot instead for a compact text-based accessibility tree. "
            "Only use screenshots when visual layout verification is absolutely necessary "
            "(e.g., debugging rendering issues, user explicitly requests screenshot). "
            "Args: full_page = capture entire scrollable page, "
            "selector = optional CSS selector to capture specific element."
        )
    )
    async def browser_screenshot(  # pylint: disable=missing-function-docstring
        full_page: bool = False,
        selector: Optional[str] = None,
    ) -> Image | ScreenshotResult:
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        try:
            if selector:
                element = await page.query_selector(selector)
                if element:
                    screenshot = await element.screenshot()
                else:
                    return ScreenshotResult.failure(
                        f"Element not found: {selector}",
                        full_page=full_page,
                        selector=selector,
                    )
            else:
                screenshot = await page.screenshot(full_page=full_page)

            # Return native MCP Image instead of base64 string to reduce token usage
            return Image(data=screenshot, format="png")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error taking screenshot")
            return ScreenshotResult.failure(
                f"Error taking screenshot: {e}",
                full_page=full_page,
                selector=selector,
            )

    @mcp.tool(
        description=(
            "Click an element by CSS selector. "
            "BEFORE clicking buttons, use sap_get_shortcuts to check if a keyboard shortcut "
            "is available - shortcuts are faster and more reliable than clicks."
        )
    )
    async def browser_click(selector: str) -> ClickResult:  # pylint: disable=missing-function-docstring
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        escaped_selector = _escape_css_selector(selector)

        try:
            await page.click(escaped_selector)
            await page.wait_for_load_state("networkidle", timeout=15000)
            return ClickResult(selector=selector)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error clicking element")
            return ClickResult.failure(f"Error clicking {selector}: {e}", selector=selector)

    @mcp.tool(
        description=(
            "Fill a single input field by CSS selector. "
            "For filling multiple fields on the same screen, use sap_fill_form instead - "
            "it fills all fields in a single call, which is much faster."
        )
    )
    async def browser_fill(selector: str, value: str) -> FillResult:  # pylint: disable=missing-function-docstring
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        escaped_selector = _escape_css_selector(selector)

        try:
            await page.fill(escaped_selector, value)
            return FillResult(selector=selector, value=value)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error filling element")
            return FillResult.failure(f"Error filling {selector}: {e}", selector=selector, value=value)

    @mcp.tool(
        description=(
            "Send keyboard input (key press or text typing). "
            "For SAP shortcuts, prefer sap_keyboard which auto-reads the status bar. "
            "For filling multiple form fields, use sap_fill_form - much faster. "
            "Args: key = key to press (e.g., 'Enter', 'Tab', 'F3'), "
            "text = text to type character by character."
        )
    )
    async def browser_keyboard(  # pylint: disable=missing-function-docstring
        key: Optional[str] = None,
        text: Optional[str] = None,
    ) -> BrowserKeyboardResult:
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        try:
            if key:
                await page.keyboard.press(key)
                return BrowserKeyboardResult(key=key)
            if text:
                await page.keyboard.type(text)
                return BrowserKeyboardResult(text=text)
            return BrowserKeyboardResult.failure("Either 'key' or 'text' parameter required")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error sending keyboard input")
            return BrowserKeyboardResult.failure(f"Error with keyboard input: {e}", key=key, text=text)

    @mcp.tool(
        description=(
            "Navigate to a URL. " "For SAP login, use sap_login instead - it handles credentials and session setup."
        )
    )
    async def browser_navigate(url: str) -> NavigateResult:  # pylint: disable=missing-function-docstring
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle", timeout=15000)
            title = await page.title()
            return NavigateResult(url=url, title=title)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error navigating")
            return NavigateResult.failure(f"Error navigating to {url}: {e}", url=url)

    @mcp.tool(
        description=(
            "Execute JavaScript in the browser. "
            "Use with caution - this has full access to the page context. "
            "Prefer SAP-specific tools when available. "
            "Returns: JSON-serialized result."
        )
    )
    async def browser_evaluate(script: str) -> EvaluateResult:  # pylint: disable=missing-function-docstring
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        script_snippet = script[:100] if len(script) > 100 else script

        try:
            result = await page.evaluate(script)
            return EvaluateResult(
                result=json.dumps(result, indent=2, default=str),
                script_snippet=script_snippet,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error evaluating script")
            return EvaluateResult.failure(f"Error executing script: {e}", script_snippet=script_snippet)

    @mcp.tool(
        description=(
            "Wait for an element to reach a specific state. "
            "IMPORTANT: Only useful with a selector - calling without a selector is pointless "
            "because MCP round-trip time already provides natural delays. "
            "Good uses: wait for element to appear (state='visible') or loading spinner to "
            "disappear (state='hidden'). "
            "Args: selector = CSS selector to wait for, timeout = max wait in ms, "
            "state = 'visible'/'hidden'/'attached'/'detached'."
        )
    )
    async def browser_wait(  # pylint: disable=missing-function-docstring
        selector: Optional[str] = None,
        timeout: int = 5000,
        state: Literal["attached", "detached", "hidden", "visible"] = "visible",
    ) -> WaitResult:
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        timeout_td = timedelta(milliseconds=timeout)

        try:
            if selector:
                escaped_selector = _escape_css_selector(selector)
                await page.wait_for_selector(escaped_selector, timeout=timeout, state=state)
                return WaitResult(selector=selector, state=state, timeout=timeout_td)
            await page.wait_for_timeout(timeout)
            return WaitResult(timeout=timeout_td)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error waiting")
            return WaitResult.failure(f"Error waiting: {e}", selector=selector, state=state, timeout=timeout_td)

    @mcp.tool(
        description=(
            "Get HTML content of an element or the full page. "
            "For large HTML (>50KB), returns a File to avoid context bloat. "
            "Prefer sap_get_screen_text or sap_get_form_fields for structured SAP data. "
            "Args: selector = CSS selector (None for full page), "
            "outer = include element itself (outerHTML) or just children (innerHTML)."
        )
    )
    async def browser_get_html(  # pylint: disable=missing-function-docstring
        selector: Optional[str] = None,
        outer: bool = True,
    ) -> HtmlResult | list[File | str]:
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        try:
            if selector:
                escaped_selector = _escape_css_selector(selector)
                element = await page.query_selector(escaped_selector)
                if element:
                    if outer:
                        html: str = await element.evaluate("el => el.outerHTML")
                    else:
                        html = await element.evaluate("el => el.innerHTML")
                else:
                    return HtmlResult.failure(f"Element not found: {selector}", selector=selector, outer=outer)
            else:
                html = await page.content()

            # Check if HTML is large enough to return as File
            html_bytes = html.encode("utf-8")
            if len(html_bytes) > _HTML_SIZE_THRESHOLD_BYTES:
                size_kb = len(html_bytes) / 1024
                logger.debug("HTML size %.1fKB exceeds threshold, returning as File", size_kb)
                metadata = (
                    f"HTML content returned as file (size: {size_kb:.1f}KB). "
                    f"Selector: {selector or 'full page'}, outer: {outer}"
                )
                return [
                    File(data=html_bytes, name="page_content.html"),
                    metadata,
                ]

            return HtmlResult(html=html, selector=selector, outer=outer)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting HTML")
            return HtmlResult.failure(f"Error getting HTML: {e}", selector=selector, outer=outer)

    @mcp.tool(
        description=(
            "Select an option from a dropdown/select element. "
            "For SAP dropdowns, prefer sap_fill_form or sap_set_field which handle "
            "SAP-specific dropdown behavior. "
            "Args: selector = CSS selector for select element, "
            "value = option value to select, label = option text (alternative to value)."
        )
    )
    async def browser_select_option(  # pylint: disable=missing-function-docstring
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
    ) -> SelectOptionResult:
        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        escaped_selector = _escape_css_selector(selector)

        try:
            if value:
                await page.select_option(escaped_selector, value=value)
                return SelectOptionResult(selector=selector, selected_value=value)
            if label:
                await page.select_option(escaped_selector, label=label)
                return SelectOptionResult(selector=selector, selected_label=label)
            return SelectOptionResult.failure(
                "Either 'value' or 'label' parameter required",
                selector=selector,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error selecting option")
            return SelectOptionResult.failure(
                f"Error selecting option: {e}",
                selector=selector,
                selected_value=value,
                selected_label=label,
            )
