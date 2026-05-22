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

from sapguimcp.backend.manager import get_webgui_backend
from sapguimcp.backend.webgui.models.browser_results import (
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
)
from sapguimcp.backend.webgui.utils import escape_css_selector

__all__ = ["register_browser_tools"]

logger = logging.getLogger(__name__)

# Threshold for returning HTML as File instead of inline (50KB)
# This prevents context bloat for large SAP pages
_HTML_SIZE_THRESHOLD_BYTES = 50 * 1024

_SCREENSHOT_WARNING = (
    "⚠️ You used browser_screenshot which consumes significant context. "
    "Use browser_snapshot (text-based accessibility tree) instead. "
    "Only use browser_screenshot when the user explicitly asks for a screenshot "
    "or when debugging visual rendering issues."
)


def register_browser_tools(mcp: FastMCP) -> None:  # pylint: disable=too-many-statements
    """Register all browser automation tools with the MCP server."""

    @mcp.tool(
        description=(
            "Get accessibility tree snapshot of the current page. "
            "Returns a YAML representation of the ARIA tree - useful for understanding "
            "page structure when other tools fail. "
            "Args: selector = optional CSS selector to scope the snapshot.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_snapshot(
        selector: Optional[str] = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SnapshotResult:
        """Get accessibility tree snapshot of the current page.

        Args:
            selector: Optional CSS selector to scope the snapshot.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_snapshot")
        except ValueError as e:
            return SnapshotResult.failure(str(e), selector=selector)

        page = backend._page  # pylint: disable=protected-access

        try:
            if selector:
                escaped_selector = escape_css_selector(selector)
                locator = page.locator(escaped_selector)
                if await locator.count() > 0:
                    snapshot = await locator.first.aria_snapshot()
                else:
                    return SnapshotResult.failure(f"Element not found: {selector}", selector=selector)
            else:
                snapshot = await page.locator("body").aria_snapshot()

            return SnapshotResult(snapshot=snapshot, selector=selector)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting snapshot")
            return SnapshotResult.failure(f"Error getting snapshot: {e}", selector=selector)

    @mcp.tool(
        description=(
            "⚠️ WRONG TOOL — use browser_snapshot instead. "
            "browser_snapshot returns a compact text-based accessibility tree "
            "that is sufficient for 95% of use cases.\n\n"
            "ONLY use browser_screenshot when:\n"
            "1. The user EXPLICITLY asks for a screenshot\n"
            "2. You need to verify visual rendering/layout issues that cannot be "
            "diagnosed from the accessibility tree\n\n"
            "This tool returns a large image that rapidly fills up conversation context "
            "and degrades performance.\n\n"
            "Args: full_page = capture entire scrollable page, "
            "selector = optional CSS selector to capture specific element.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_screenshot(
        full_page: bool = False,
        selector: Optional[str] = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> list[str | Image] | ScreenshotResult:
        """Take a screenshot of the current page.

        Args:
            full_page: Capture entire scrollable page.
            selector: Optional CSS selector to capture specific element.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_screenshot")
        except ValueError as e:
            return ScreenshotResult.failure(
                str(e),
                full_page=full_page,
                selector=selector,
            )

        page = backend._page  # pylint: disable=protected-access

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

            return [_SCREENSHOT_WARNING, Image(data=screenshot, format="png")]
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Taking screenshot")
            return ScreenshotResult.failure(
                f"Error taking screenshot: {e}",
                full_page=full_page,
                selector=selector,
            )

    @mcp.tool(
        description=(
            "Click an element by CSS selector. "
            "BEFORE clicking buttons, use sap_get_shortcuts to check if a keyboard shortcut "
            "is available - shortcuts are faster and more reliable than clicks.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_click(
        selector: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ClickResult:
        """Click an element by CSS selector.

        Args:
            selector: CSS selector of the element to click.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_click")
        except ValueError as e:
            return ClickResult.failure(str(e), selector=selector)

        page = backend._page  # pylint: disable=protected-access
        escaped_selector = escape_css_selector(selector)

        try:
            await page.click(escaped_selector)
            await page.wait_for_load_state("networkidle", timeout=15000)
            return ClickResult(selector=selector)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Clicking element")
            return ClickResult.failure(f"Error clicking {selector}: {e}", selector=selector)

    @mcp.tool(
        description=(
            "Fill a single input field by CSS selector. "
            "For filling multiple fields on the same screen, use sap_fill_form instead - "
            "it fills all fields in a single call, which is much faster.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_fill(
        selector: str,
        value: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> FillResult:
        """Fill a single input field by CSS selector.

        Args:
            selector: CSS selector of the input field.
            value: Value to fill in the field.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_fill")
        except ValueError as e:
            return FillResult.failure(str(e), selector=selector, value=value)

        page = backend._page  # pylint: disable=protected-access
        escaped_selector = escape_css_selector(selector)

        try:
            await page.fill(escaped_selector, value)
            return FillResult(selector=selector, value=value)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Filling element")
            return FillResult.failure(f"Error filling {selector}: {e}", selector=selector, value=value)

    @mcp.tool(
        description=(
            "Send keyboard input (key press or text typing). "
            "Important: For SAP shortcuts like Ctrl+S, prefer sap_press_key which auto-reads the status bar! "
            "For filling multiple form fields, use sap_fill_form - much faster. "
            "Args: key = key to press (e.g., 'Enter', 'Tab', 'F3'), "
            "text = text to type character by character.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_keyboard(
        key: Optional[str] = None,
        text: Optional[str] = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> BrowserKeyboardResult:
        """Send keyboard input (key press or text typing).

        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'F3').
            text: Text to type character by character.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_keyboard")
        except ValueError as e:
            return BrowserKeyboardResult.failure(str(e), key=key, text=text)

        page = backend._page  # pylint: disable=protected-access

        try:
            if key:
                await page.keyboard.press(key)
                return BrowserKeyboardResult(key=key)
            if text:
                await page.keyboard.type(text)
                return BrowserKeyboardResult(text=text)
            return BrowserKeyboardResult.failure("Either 'key' or 'text' parameter required")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Sending keyboard input")
            return BrowserKeyboardResult.failure(f"Error with keyboard input: {e}", key=key, text=text)

    @mcp.tool(
        description=(
            "Navigate to a URL. "
            "For SAP login, use sap_login instead - it handles credentials and session setup.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_navigate(
        url: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> NavigateResult:
        """Navigate to a URL.

        Args:
            url: URL to navigate to.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_navigate")
        except ValueError as e:
            return NavigateResult.failure(str(e), url=url)

        page = backend._page  # pylint: disable=protected-access

        try:
            await page.goto(url)
            await page.wait_for_load_state("networkidle", timeout=15000)
            title = await page.title()
            return NavigateResult(url=url, title=title)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Navigating")
            return NavigateResult.failure(f"Error navigating to {url}: {e}", url=url)

    @mcp.tool(
        description=(
            "Execute JavaScript in the browser. "
            "Use with caution - this has full access to the page context. "
            "Prefer SAP-specific tools when available. "
            "Returns: JSON-serialized result.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_evaluate(
        script: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> EvaluateResult:
        """Execute JavaScript in the browser.

        Args:
            script: JavaScript code to execute.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        script_snippet = script[:100] if len(script) > 100 else script

        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_evaluate")
        except ValueError as e:
            return EvaluateResult.failure(str(e), script_snippet=script_snippet)

        page = backend._page  # pylint: disable=protected-access

        try:
            result = await page.evaluate(script)
            return EvaluateResult(
                result=json.dumps(result, indent=2, default=str),
                script_snippet=script_snippet,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Evaluating script")
            return EvaluateResult.failure(f"Error executing script: {e}", script_snippet=script_snippet)

    @mcp.tool(
        description=(
            "Wait for an element to reach a specific state. "
            "IMPORTANT: Only useful with a selector - calling without a selector is pointless "
            "because MCP round-trip time already provides natural delays. "
            "Good uses: wait for element to appear (state='visible') or loading spinner to "
            "disappear (state='hidden'). "
            "Args: selector = CSS selector to wait for, timeout = max wait in ms, "
            "state = 'visible'/'hidden'/'attached'/'detached'.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_wait(
        selector: Optional[str] = None,
        timeout: int = 5000,
        state: Literal["attached", "detached", "hidden", "visible"] = "visible",
        session: str | None = None,
        agent_id: str | None = None,
    ) -> WaitResult:
        """Wait for an element to reach a specific state.

        Args:
            selector: CSS selector to wait for.
            timeout: Max wait time in milliseconds.
            state: Target state ('visible', 'hidden', 'attached', 'detached').
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        timeout_td = timedelta(milliseconds=timeout)

        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_wait")
        except ValueError as e:
            return WaitResult.failure(str(e), selector=selector, state=state, timeout=timeout_td)

        page = backend._page  # pylint: disable=protected-access

        try:
            if selector:
                escaped_selector = escape_css_selector(selector)
                await page.wait_for_selector(escaped_selector, timeout=timeout, state=state)
                return WaitResult(selector=selector, state=state, timeout=timeout_td)
            await page.wait_for_timeout(timeout)
            return WaitResult(timeout=timeout_td)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Waiting")
            return WaitResult.failure(f"Error waiting: {e}", selector=selector, state=state, timeout=timeout_td)

    @mcp.tool(
        description=(
            "Get HTML content of an element or the full page. "
            "For large HTML (>50KB), returns a File to avoid context bloat. "
            "Prefer sap_get_screen_text or sap_get_form_fields for structured SAP data. "
            "Args: selector = CSS selector (None for full page), "
            "outer = include element itself (outerHTML) or just children (innerHTML).\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_get_html(
        selector: Optional[str] = None,
        outer: bool = True,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> HtmlResult | list[File | str]:
        """Get HTML content of an element or the full page.

        Args:
            selector: CSS selector (None for full page).
            outer: Include element itself (outerHTML) or just children (innerHTML).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_get_html")
        except ValueError as e:
            return HtmlResult.failure(str(e), selector=selector, outer=outer)

        page = backend._page  # pylint: disable=protected-access

        try:
            if selector:
                escaped_selector = escape_css_selector(selector)
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
                logger.debug("HTML exceeds threshold, returning as file", extra={"size_kb": round(size_kb, 1)})
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
            logger.exception("Getting HTML")
            return HtmlResult.failure(f"Error getting HTML: {e}", selector=selector, outer=outer)

    @mcp.tool(
        description=(
            "Select an option from a dropdown/select element. "
            "For SAP dropdowns, prefer sap_fill_form or sap_set_field which handle "
            "SAP-specific dropdown behavior. "
            "Args: selector = CSS selector for select element, "
            "value = option value to select, label = option text (alternative to value).\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def browser_select_option(
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SelectOptionResult:
        """Select an option from a dropdown/select element.

        Args:
            selector: CSS selector for the select element.
            value: Option value to select.
            label: Option text (alternative to value).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_webgui_backend(session=session, agent_id=agent_id, tool_name="browser_select_option")
        except ValueError as e:
            return SelectOptionResult.failure(str(e), selector=selector)

        page = backend._page  # pylint: disable=protected-access
        escaped_selector = escape_css_selector(selector)

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
            logger.exception("Selecting option")
            return SelectOptionResult.failure(
                f"Error selecting option: {e}",
                selector=selector,
                selected_value=value,
                selected_label=label,
            )
