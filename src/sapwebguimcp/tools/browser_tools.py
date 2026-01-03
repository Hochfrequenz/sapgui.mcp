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

import base64
import json
import logging
from datetime import timedelta
from typing import Literal, Optional

from fastmcp import FastMCP

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


def _escape_css_selector(selector: str) -> str:
    """
    Escape special CSS characters in selectors.

    SAP generates IDs like 'M0:48::btn[5]' which contain special CSS characters.
    This function escapes them so they work as valid CSS selectors.

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
        # Escape CSS special characters: : [ ] . (but not at start)
        escaped_id = ""
        for char in id_part:
            if char in r":[]":
                escaped_id += f"\\{char}"
            else:
                escaped_id += char
        return f"#{escaped_id}"

    return selector


def register_browser_tools(mcp: FastMCP) -> None:  # pylint: disable=too-many-statements
    """Register all browser automation tools with the MCP server."""

    @mcp.tool(description="Get accessibility tree snapshot of the current page")
    async def browser_snapshot(selector: Optional[str] = None) -> SnapshotResult:
        """
        Get ARIA snapshot of the current page.

        Returns a YAML representation of the accessibility tree.
        Useful for understanding page structure when other tools fail.

        Args:
            selector: Optional CSS selector to scope the snapshot

        Returns:
            SnapshotResult with ARIA snapshot in YAML format
        """
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
            "WARNING: Screenshots are large and consume significant context. "
            "Prefer sap_get_screen_text when you only need to read text/labels. "
            "Use screenshots sparingly - only when visual layout matters."
        )
    )
    async def browser_screenshot(full_page: bool = False, selector: Optional[str] = None) -> ScreenshotResult:
        """
        Take a screenshot of the current page.

        WARNING: Screenshots are large base64 images that consume significant
        conversation context. Prefer sap_get_screen_text when you only need
        to read text, labels, or field names. Use screenshots sparingly.

        Args:
            full_page: Capture entire scrollable page
            selector: Optional CSS selector to capture specific element

        Returns:
            ScreenshotResult with base64 encoded PNG image
        """
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

            return ScreenshotResult(
                image_base64=base64.b64encode(screenshot).decode("utf-8"),
                full_page=full_page,
                selector=selector,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error taking screenshot")
            return ScreenshotResult.failure(
                f"Error taking screenshot: {e}",
                full_page=full_page,
                selector=selector,
            )

    @mcp.tool(description="Click an element by CSS selector")
    async def browser_click(selector: str) -> ClickResult:
        """
        Click an element by CSS selector.

        Args:
            selector: CSS selector for the element to click

        Returns:
            ClickResult with the selector that was clicked
        """
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
            "For filling multiple fields on the same screen, use sap_fill_form instead - it's much faster."
        )
    )
    async def browser_fill(selector: str, value: str) -> FillResult:
        """
        Fill an input field by CSS selector.

        For filling multiple fields on the same SAP screen, use sap_fill_form
        instead - it fills all fields in a single call, which is much faster.

        Args:
            selector: CSS selector for the input element
            value: Value to fill

        Returns:
            FillResult with selector and value
        """
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
            "For filling multiple form fields, use sap_fill_form instead - "
            "it's much faster than repeated focus+type calls."
        )
    )
    async def browser_keyboard(key: Optional[str] = None, text: Optional[str] = None) -> BrowserKeyboardResult:
        """
        Send keyboard input.

        For filling multiple form fields on the same screen, use sap_fill_form
        instead - it's much faster than repeated focus+type calls.

        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'F3', 'Control+s')
            text: Text to type character by character

        Returns:
            BrowserKeyboardResult with key or text that was sent
        """
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

    @mcp.tool(description="Navigate to a URL")
    async def browser_navigate(url: str) -> NavigateResult:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to

        Returns:
            NavigateResult with URL and page title
        """
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

    @mcp.tool(description="Execute JavaScript in the browser")
    async def browser_evaluate(script: str) -> EvaluateResult:
        """
        Execute JavaScript in the browser.

        Use with caution - this has full access to the page context.

        Args:
            script: JavaScript code to execute

        Returns:
            EvaluateResult with JSON-serialized result
        """
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
            "IMPORTANT: Only useful with a selector - calling without a selector is almost always pointless "
            "because MCP round-trip time already provides natural delays. "
            "Use this to wait for elements to appear (state='visible') or disappear (state='hidden'), "
            "e.g., waiting for a loading indicator to vanish before reading content."
        )
    )
    async def browser_wait(
        selector: Optional[str] = None,
        timeout: int = 5000,
        state: Literal["attached", "detached", "hidden", "visible"] = "visible",
    ) -> WaitResult:
        """
        Wait for an element to reach a specific state.

        IMPORTANT: Only useful with a selector. Calling without a selector is almost always
        pointless because the MCP tool round-trip already introduces natural delays. Don't
        use this as a generic sleep - it wastes time without benefit.

        Good use cases:
        - Wait for an element to appear before reading: browser_wait(selector="#result", state="visible")
        - Wait for loading spinner to disappear: browser_wait(selector=".loading", state="hidden")

        Args:
            selector: CSS selector to wait for (required for meaningful use)
            timeout: Maximum wait time in milliseconds (returns early if condition met)
            state: Element state to wait for ('visible', 'hidden', 'attached', 'detached')

        Returns:
            WaitResult with selector, state, and timeout
        """
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

    @mcp.tool(description="Get HTML content of an element or the full page")
    async def browser_get_html(selector: Optional[str] = None, outer: bool = True) -> HtmlResult:
        """
        Get HTML content of an element or the full page.

        Args:
            selector: CSS selector (if None, returns full page HTML)
            outer: Include the element itself (outerHTML) or just children (innerHTML)

        Returns:
            HtmlResult with HTML content
        """
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
                    return HtmlResult(html=html, selector=selector, outer=outer)
                return HtmlResult.failure(f"Element not found: {selector}", selector=selector, outer=outer)
            html = await page.content()
            return HtmlResult(html=html, outer=outer)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting HTML")
            return HtmlResult.failure(f"Error getting HTML: {e}", selector=selector, outer=outer)

    @mcp.tool(description="Select an option from a dropdown/select element")
    async def browser_select_option(
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
    ) -> SelectOptionResult:
        """
        Select an option from a dropdown/select element.

        Args:
            selector: CSS selector for the select element
            value: Option value to select
            label: Option label/text to select (alternative to value)

        Returns:
            SelectOptionResult with selector and selected value/label
        """
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
