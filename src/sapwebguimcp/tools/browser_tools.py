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
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from sapwebguimcp.models import BrowserManager

__all__ = ["register_browser_tools"]

logger = logging.getLogger(__name__)


def register_browser_tools(mcp: FastMCP) -> None:
    """Register all browser automation tools with the MCP server."""

    @mcp.tool(description="Get accessibility tree snapshot of the current page")
    async def browser_snapshot(selector: Optional[str] = None) -> str:
        """
        Get accessibility tree snapshot of the current page.

        Useful for understanding page structure when other tools fail.

        Args:
            selector: Optional CSS selector to scope the snapshot

        Returns:
            Accessibility tree as text
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            if selector:
                element = await page.query_selector(selector)
                if element:
                    snapshot = await page.accessibility.snapshot(root=element)  # type: ignore[attr-defined]
                else:
                    return f"Element not found: {selector}"
            else:
                snapshot = await page.accessibility.snapshot()  # type: ignore[attr-defined]

            return json.dumps(snapshot, indent=2)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting snapshot")
            return f"Error getting snapshot: {e}"

    @mcp.tool(description="Take a screenshot of the current page")
    async def browser_screenshot(full_page: bool = False, selector: Optional[str] = None) -> str:
        """
        Take a screenshot of the current page.

        Args:
            full_page: Capture entire scrollable page
            selector: Optional CSS selector to capture specific element

        Returns:
            Base64 encoded PNG image
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            if selector:
                element = await page.query_selector(selector)
                if element:
                    screenshot = await element.screenshot()
                else:
                    return f"Element not found: {selector}"
            else:
                screenshot = await page.screenshot(full_page=full_page)

            return base64.b64encode(screenshot).decode("utf-8")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error taking screenshot")
            return f"Error taking screenshot: {e}"

    @mcp.tool(description="Click an element by CSS selector")
    async def browser_click(selector: str) -> str:
        """
        Click an element by CSS selector.

        Args:
            selector: CSS selector for the element to click

        Returns:
            Status message
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            await page.click(selector)
            await page.wait_for_load_state("networkidle")
            return f"Clicked element: {selector}"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error clicking element")
            return f"Error clicking {selector}: {e}"

    @mcp.tool(description="Fill an input field by CSS selector")
    async def browser_fill(selector: str, value: str) -> str:
        """
        Fill an input field by CSS selector.

        Args:
            selector: CSS selector for the input element
            value: Value to fill

        Returns:
            Status message
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            await page.fill(selector, value)
            return f"Filled {selector} with: {value}"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error filling element")
            return f"Error filling {selector}: {e}"

    @mcp.tool(description="Send keyboard input")
    async def browser_keyboard(key: Optional[str] = None, text: Optional[str] = None) -> str:
        """
        Send keyboard input.

        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'F3', 'Control+s')
            text: Text to type character by character

        Returns:
            Status message
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            if key:
                await page.keyboard.press(key)
                return f"Pressed key: {key}"
            if text:
                await page.keyboard.type(text)
                return f"Typed text: {text}"
            return "Either 'key' or 'text' parameter required"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error sending keyboard input")
            return f"Error with keyboard input: {e}"

    @mcp.tool(description="Navigate to a URL")
    async def browser_navigate(url: str) -> str:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to

        Returns:
            Status message
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
            title = await page.title()
            return f"Navigated to: {url} (Title: {title})"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error navigating")
            return f"Error navigating to {url}: {e}"

    @mcp.tool(description="Execute JavaScript in the browser")
    async def browser_evaluate(script: str) -> str:
        """
        Execute JavaScript in the browser.

        Use with caution - this has full access to the page context.

        Args:
            script: JavaScript code to execute

        Returns:
            Result of the script execution
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            result = await page.evaluate(script)
            return json.dumps(result, indent=2, default=str)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error evaluating script")
            return f"Error executing script: {e}"

    @mcp.tool(description="Wait for an element or timeout")
    async def browser_wait(
        selector: Optional[str] = None,
        timeout: int = 30000,
        state: Literal["attached", "detached", "hidden", "visible"] = "visible",
    ) -> str:
        """
        Wait for an element or timeout.

        Args:
            selector: CSS selector to wait for
            timeout: Timeout in milliseconds
            state: Element state to wait for ('visible', 'hidden', 'attached', 'detached')

        Returns:
            Status message
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            if selector:
                await page.wait_for_selector(selector, timeout=timeout, state=state)
                return f"Element {selector} is now {state}"
            await page.wait_for_timeout(timeout)
            return f"Waited {timeout}ms"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error waiting")
            return f"Error waiting: {e}"

    @mcp.tool(description="Get HTML content of an element or the full page")
    async def browser_get_html(selector: Optional[str] = None, outer: bool = True) -> str:
        """
        Get HTML content of an element or the full page.

        Args:
            selector: CSS selector (if None, returns full page HTML)
            outer: Include the element itself (outerHTML) or just children (innerHTML)

        Returns:
            HTML content
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            if selector:
                element = await page.query_selector(selector)
                if element:
                    if outer:
                        result: str = await element.evaluate("el => el.outerHTML")
                    else:
                        result = await element.evaluate("el => el.innerHTML")
                    return result
                return f"Element not found: {selector}"
            return await page.content()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting HTML")
            return f"Error getting HTML: {e}"

    @mcp.tool(description="Select an option from a dropdown/select element")
    async def browser_select_option(
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
    ) -> str:
        """
        Select an option from a dropdown/select element.

        Args:
            selector: CSS selector for the select element
            value: Option value to select
            label: Option label/text to select (alternative to value)

        Returns:
            Status message
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        page = await browser_manager.get_current_page()

        try:
            if value:
                await page.select_option(selector, value=value)
                return f"Selected option with value: {value}"
            if label:
                await page.select_option(selector, label=label)
                return f"Selected option with label: {label}"
            return "Either 'value' or 'label' parameter required"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error selecting option")
            return f"Error selecting option: {e}"
