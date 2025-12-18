"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
"""

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP

from sapwebguimcp.models import BrowserManager, get_settings

__all__ = ["main", "mcp"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context available to all tools via lifespan."""

    browser_manager: BrowserManager


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """
    Manage application lifecycle with type-safe context.

    This context manager:
    1. Creates and yields the browser manager for tools to use
    2. Cleans up browser resources on shutdown
    """
    settings = get_settings()
    browser_manager = BrowserManager(settings)

    logger.info("SAP Web GUI MCP Server starting...")

    try:
        yield AppContext(browser_manager=browser_manager)
    finally:
        logger.info("Cleaning up browser resources...")
        await browser_manager.close()
        logger.info("Server shutdown complete")


# Create the FastMCP server instance
mcp = FastMCP(
    "sap-webgui-mcp",
    dependencies=["playwright", "pydantic-settings"],
    lifespan=app_lifespan,
)


# =============================================================================
# Keepalive Management
# =============================================================================

_keepalive_task: Optional[asyncio.Task[None]] = None
_keepalive_interval: int = 300  # 5 minutes default


async def _keepalive_loop(browser_manager: BrowserManager, interval: int) -> None:
    """
    Background task that periodically performs a harmless action to keep SAP session alive.

    Args:
        browser_manager: The browser manager instance
        interval: Seconds between keepalive actions
    """
    logger.info("Keepalive task started with interval %d seconds", interval)

    while True:
        try:
            await asyncio.sleep(interval)

            page = await browser_manager.get_current_page()

            if page.is_closed():
                logger.warning("Keepalive: Page is closed, stopping keepalive")
                break

            # Perform a harmless action - evaluate JS to keep connection alive
            await page.evaluate("() => { /* keepalive ping */ }")

            logger.debug("Keepalive ping sent")

        except asyncio.CancelledError:
            logger.info("Keepalive task cancelled")
            break
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Keepalive error (will retry): %s", e)


# =============================================================================
# SAP Tools
# =============================================================================

# Common selectors for SAP Web GUI elements
SELECTORS: dict[str, str] = {
    "okcode_field": (
        'input[id*="ToolbarOkCode"], ' 'input[name*="okcode" i], ' 'input[id*="okcd" i], ' 'input[id*="OkCodeField" i]'
    ),
    "settings_button": (
        '[id*="settingsButton"], '
        '[title*="Setting" i], '
        '[title*="Einstellung" i], '
        'button[id*="gear" i], '
        '[aria-label*="Setting" i]'
    ),
    "menu_expand": ('[id*="shellMnuExp"], ' '[title*="Menu" i], ' '[title*="Menü" i], ' '[aria-label*="Menu" i]'),
    "okcode_checkbox": ('input[type="checkbox"][id*="okCode" i], ' 'input[type="checkbox"][name*="okCode" i]'),
    "okcode_label": (
        'label:has-text("OK-Code"), '
        'label:has-text("OKCode"), '
        'label:has-text("Transaction"), '
        'span:has-text("OK-Code")'
    ),
    "save_settings": (
        'button:has-text("Save"), '
        'button:has-text("Speichern"), '
        'button:has-text("OK"), '
        'button:has-text("Apply"), '
        'input[type="submit"]'
    ),
    "close_dialog": (
        'button:has-text("Close"), '
        'button:has-text("Schließen"), '
        'button[aria-label*="Close" i], '
        '[id*="closeButton"]'
    ),
}


async def _find_okcode_field(page: Any) -> Optional[Any]:
    """Try to find the OK-Code/transaction input field."""
    return await page.query_selector(SELECTORS["okcode_field"])


async def _try_find_checkbox_by_label(page: Any) -> Optional[Any]:
    """Try to find OK-Code checkbox by its label."""
    okcode_label = await page.query_selector(SELECTORS["okcode_label"])
    if not okcode_label:
        return None

    for_id = await okcode_label.get_attribute("for")
    if for_id:
        return await page.query_selector(f"#{for_id}")

    parent = await okcode_label.evaluate_handle("el => el.parentElement")
    if parent:
        return await parent.query_selector('input[type="checkbox"]')
    return None


async def _try_find_checkbox_in_tabs(page: Any, steps_taken: list[str]) -> Optional[Any]:
    """Try to find OK-Code checkbox by searching through settings tabs."""
    settings_tabs = await page.query_selector_all('[role="tab"], .sapMTabStrip button, [class*="tab" i] button')
    for tab in settings_tabs:
        tab_text = await tab.text_content()
        if tab_text and any(
            keyword in tab_text.lower()
            for keyword in ["display", "anzeige", "layout", "toolbar", "general", "allgemein"]
        ):
            await tab.click()
            await page.wait_for_timeout(500)
            okcode_checkbox = await page.query_selector(SELECTORS["okcode_checkbox"])
            if okcode_checkbox:
                steps_taken.append(f"Found OK-Code setting in tab: {tab_text}")
                return okcode_checkbox
    return None


async def _close_settings_dialog(page: Any) -> None:
    """Close the settings dialog if open."""
    close_btn = await page.query_selector(SELECTORS["close_dialog"])
    if close_btn:
        await close_btn.click()
        await page.wait_for_timeout(500)


async def _enable_okcode_field(  # pylint: disable=too-many-return-statements
    page: Any,
) -> tuple[bool, str]:
    """
    Enable the OK-Code field through SAP Web GUI settings.

    Returns:
        Tuple of (success: bool, message: str)
    """
    steps_taken: list[str] = []

    try:
        # Step 1: Try to expand menu if there's an expand button
        menu_expand = await page.query_selector(SELECTORS["menu_expand"])
        if menu_expand:
            await menu_expand.click()
            await page.wait_for_timeout(500)
            steps_taken.append("Expanded menu")

        # Step 2: Find and click settings/gear button
        settings_btn = await page.query_selector(SELECTORS["settings_button"])
        if not settings_btn:
            settings_btn = await page.query_selector(
                '[role="menu"] [title*="Setting" i], '
                '[role="menu"] [title*="Einstellung" i], '
                '[class*="menu"] [title*="Setting" i]'
            )

        if not settings_btn:
            return False, "Could not find settings/gear button. Please enable OK-Code field manually."

        await settings_btn.click()
        await page.wait_for_timeout(1000)
        steps_taken.append("Opened settings")

        # Step 3: Look for OK-Code checkbox or setting
        okcode_checkbox = await page.query_selector(SELECTORS["okcode_checkbox"])

        if not okcode_checkbox:
            okcode_checkbox = await _try_find_checkbox_by_label(page)

        if not okcode_checkbox:
            okcode_checkbox = await _try_find_checkbox_in_tabs(page, steps_taken)

        if not okcode_checkbox:
            await _close_settings_dialog(page)
            return False, f"Could not find OK-Code checkbox in settings. Steps taken: {', '.join(steps_taken)}"

        # Step 4: Check if already enabled
        is_checked = await okcode_checkbox.is_checked()
        if is_checked:
            steps_taken.append("OK-Code field already enabled")
            await _close_settings_dialog(page)
            return True, f"OK-Code field was already enabled. Steps: {', '.join(steps_taken)}"

        # Step 5: Enable the checkbox
        await okcode_checkbox.click()
        await page.wait_for_timeout(300)
        steps_taken.append("Enabled OK-Code checkbox")

        # Step 6: Save settings
        save_btn = await page.query_selector(SELECTORS["save_settings"])
        if save_btn:
            await save_btn.click()
            await page.wait_for_timeout(1000)
            steps_taken.append("Saved settings")
        else:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)
            steps_taken.append("Pressed Enter to confirm")

        # Close any remaining dialog
        await _close_settings_dialog(page)

        return True, f"OK-Code field enabled. Steps: {', '.join(steps_taken)}"

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error enabling OK-Code field")
        return False, f"Error enabling OK-Code field: {e}. Steps taken: {', '.join(steps_taken)}"


@mcp.tool(description="Start a background task that keeps the SAP session alive")
async def sap_keepalive_start(interval_seconds: int = 300) -> str:
    """
    Start a background task that keeps the SAP session alive.

    This prevents SAP from logging you out due to inactivity.
    The task runs in the background and periodically pings the browser
    to maintain the session.

    Args:
        interval_seconds: Seconds between keepalive pings (default: 300 = 5 minutes)

    Returns:
        Status message confirming keepalive is running.
    """
    global _keepalive_task, _keepalive_interval  # pylint: disable=global-statement

    ctx = mcp.get_context()
    browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

    # Stop existing task if running
    if _keepalive_task is not None and not _keepalive_task.done():
        _keepalive_task.cancel()
        try:
            await _keepalive_task
        except asyncio.CancelledError:
            pass

    _keepalive_interval = interval_seconds
    _keepalive_task = asyncio.create_task(_keepalive_loop(browser_manager, interval_seconds))

    return (
        f"Keepalive started. Will ping every {interval_seconds} seconds "
        f"({interval_seconds // 60} minutes) to prevent session timeout."
    )


@mcp.tool(description="Stop the background keepalive task")
async def sap_keepalive_stop() -> str:
    """
    Stop the background keepalive task.

    Call this when you're done with SAP or want to allow the session to timeout naturally.

    Returns:
        Status message confirming keepalive is stopped.
    """
    global _keepalive_task  # pylint: disable=global-statement

    if _keepalive_task is None or _keepalive_task.done():
        return "Keepalive was not running."

    _keepalive_task.cancel()
    try:
        await _keepalive_task
    except asyncio.CancelledError:
        pass

    _keepalive_task = None
    return "Keepalive stopped."


@mcp.tool(description="Open SAP Web GUI login page")
async def sap_login(url: Optional[str] = None) -> str:
    """
    Open SAP Web GUI login page.

    Opens the SAP Web GUI URL in the browser. The user should then
    manually enter their login credentials.

    Args:
        url: SAP Web GUI URL. If not provided, uses SAP_URL from environment.

    Returns:
        Status message indicating the login page is ready.
    """
    ctx = mcp.get_context()
    browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
    settings = get_settings()

    page = await browser_manager.get_current_page()
    effective_url = url or settings.sap_url

    if not effective_url:
        return "No SAP URL provided. Either pass a URL parameter or set the SAP_URL environment variable."

    try:
        logger.info("Navigating to SAP Web GUI: %s", effective_url)
        await page.goto(effective_url)
        await page.wait_for_load_state("networkidle")

        # Check if we're on a login page or already logged in
        okcode_field = await _find_okcode_field(page)
        if okcode_field:
            return (
                f"Already logged in to SAP at {effective_url}. "
                "OK-Code field is available. Ready to run transactions."
            )

        # Check for login form elements
        login_elements = await page.query_selector(
            'input[type="password"], '
            'input[name*="user" i], '
            'input[id*="user" i], '
            'button:has-text("Log"), '
            'button:has-text("Anmeld")'
        )

        if login_elements:
            return f"SAP login page opened at {effective_url}. Please enter your credentials in the browser window."

        return f"Navigated to {effective_url}. Please check the browser window and complete any required login steps."

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error opening SAP login page")
        return f"Error navigating to SAP: {e}"


@mcp.tool(description="Enter and execute an SAP transaction code")
async def sap_transaction(tcode: str) -> str:
    """
    Enter and execute an SAP transaction code.

    This tool will:
    1. Check if the OK-Code field is visible
    2. If not, attempt to enable it via Settings (gear icon → enable OK-Code field)
    3. Enter the transaction code and execute it

    Args:
        tcode: Transaction code (e.g., VA01, MM03, SE80, SU01)

    Returns:
        Status message indicating success or describing any issues.
    """
    ctx = mcp.get_context()
    browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

    page = await browser_manager.get_current_page()

    try:
        # Step 1: Check if OK-Code field exists
        okcode_field = await _find_okcode_field(page)

        if not okcode_field:
            logger.info("OK-Code field not found, attempting to enable it")

            # Step 2: Try to enable the OK-Code field
            success, message = await _enable_okcode_field(page)
            logger.info("Enable OK-Code result: %s - %s", success, message)

            if not success:
                return (
                    f"Could not find or enable OK-Code field. {message} "
                    "You may need to enable it manually: "
                    "Menu → Settings → Enable 'OK-Code Field' or 'Transaction Field'"
                )

            await page.wait_for_timeout(500)

            okcode_field = await _find_okcode_field(page)
            if not okcode_field:
                return (
                    f"OK-Code field still not visible after enabling. {message} "
                    "Please try enabling it manually in SAP settings."
                )

        # Step 3: Enter the transaction code
        # SAP transaction codes need "/n" prefix to open in new mode
        # - Simple codes like "SU3" become "/nSU3"
        # - Codes starting with "/" like "/IWFND/GW_CLIENT" become "/n/IWFND/GW_CLIENT"
        # - Codes already starting with "/n" are used as-is
        if tcode.startswith("/n"):
            transaction_input = tcode
        else:
            transaction_input = f"/n{tcode}"

        # Ensure page is in front and active
        await page.bring_to_front()
        await page.wait_for_timeout(500)

        # ============================================================================
        # SAP Web GUI OK-Code Field Automation - Important Findings
        # ============================================================================
        #
        # The OK-Code field (id="ToolbarOkCode") in SAP Web GUI is NOT a standard HTML
        # input. It has custom SAP event handlers defined in the "lsevents" attribute:
        #
        #   lsevents="{
        #     "Enter": [{}, {"1": "vkey/0/ses[0]", "2": true}],
        #     "Change": [{}, {"1": "okcode/ses[0]"}],
        #     ...
        #   }"
        #
        # What DOES NOT work:
        # - Playwright's fill() method - sets value but SAP doesn't recognize it
        # - Playwright's type() method - characters don't appear in the field
        # - page.keyboard.type() - keystrokes don't reach the SAP field
        # - Direct click + keyboard input - same issue, SAP intercepts events
        #
        # What DOES work:
        # - JavaScript: Set field.value directly, then dispatch Enter keyboard events
        # - The Enter event triggers SAP's lsevents handler which processes the value
        # - The text may not visually appear in the field, but the transaction executes
        #
        # ============================================================================

        logger.info("Attempting to enter transaction code: %s", transaction_input)

        # Use JavaScript to set value, then Playwright to press Enter
        # JS events alone don't trigger SAP's navigation - we need real keyboard input
        #
        # IMPORTANT: We must click on the OK-Code field first to ensure it has focus.
        # Without this click, the Enter key may be processed by a different element.
        await okcode_field.click()
        await page.wait_for_timeout(200)
        logger.info("Clicked OK-Code field to ensure focus")

        await page.evaluate(
            f"""
            (function() {{
                var field = document.getElementById('ToolbarOkCode');
                if (field) {{
                    // Focus the field first
                    field.focus();

                    // Set the value directly
                    field.value = '{transaction_input}';

                    // Trigger input/change events so SAP knows the value changed
                    field.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                    field.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
                }}
            }})()
            """
        )

        await page.wait_for_timeout(300)
        logger.info("Set transaction code via JavaScript: %s", transaction_input)

        # Now use Playwright's keyboard to press Enter - this triggers SAP's navigation
        # The JS dispatched events don't work, but real keyboard input does
        await page.keyboard.press("Enter")
        logger.info("Pressed Enter to execute transaction")

        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(500)

        title = await page.title()

        return (
            f"Transaction {tcode} executed. Current page: {title}. "
            "Check the browser window for the transaction screen."
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error executing transaction")
        return f"Error executing transaction {tcode}: {e}"


# =============================================================================
# Browser Tools (Escape Hatches)
# =============================================================================


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


# =============================================================================
# Entry Point
# =============================================================================


def main() -> None:
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
