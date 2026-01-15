"""
Browser manager for persistent Playwright sessions.

This module provides a BrowserManager class that maintains a persistent browser
session across multiple tool calls, following the dev-browser pattern.
"""

import logging
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from sapwebguimcp.models.config import BrowserMode, SapWebGuiSettings, get_settings
from sapwebguimcp.models.session_registry import SessionRegistry

__all__ = [
    "BrowserManager",
    "get_browser_manager",
    "close_browser_manager",
]

logger = logging.getLogger(__name__)


class BrowserManager:  # pylint: disable=too-many-instance-attributes
    """
    Manages a persistent browser session for SAP Web GUI automation.

    The browser state persists across tool calls, allowing for:
    - Single login, multiple transactions
    - Named pages that survive between script executions
    - Session cookies and localStorage preservation

    Example:
        manager = await get_browser_manager()
        page = await manager.get_current_page()
        await page.goto("https://sap.example.com")
    """

    def __init__(self, settings: Optional[SapWebGuiSettings] = None) -> None:
        self._settings = settings
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: dict[str, Page] = {}
        self._default_page_name = "sap"
        self._initialized = False
        self._registry = SessionRegistry()

    @property
    def is_initialized(self) -> bool:
        """Check if the browser manager has been initialized."""
        return self._initialized

    @property
    def registry(self) -> SessionRegistry:
        """Session registry for multi-session support."""
        return self._registry

    def get_session_page(self, session_id: str | None) -> Page:
        """Get page for a session ID (strict - no page creation).

        Returns an existing page from the registry or legacy page storage.
        Raises ValueError if no session exists. For a version that creates
        pages as fallback, use get_or_create_session_page().

        Args:
            session_id: Session ID or None for primary session ('s1')

        Returns:
            Playwright Page for the session

        Raises:
            ValueError: If session not found and no legacy page available
        """
        # If explicit session specified, use registry
        if session_id is not None:
            return self._registry.get_page(session_id)

        # If session=None and s1 exists, use s1
        if self._registry.has_session("s1"):
            return self._registry.get_page("s1")

        # Backwards compatibility: if no sessions registered, use legacy page
        # This allows tools to work before sap_login() registers s1
        if self._default_page_name in self._pages:
            page = self._pages[self._default_page_name]
            if not page.is_closed():
                return page

        # No session and no legacy page - this is an error
        raise ValueError(
            "No session available. Call sap_login() first to create a session, "
            "or use sap_session_open() to create additional sessions."
        )

    async def get_or_create_session_page(self, session_id: str | None) -> Page:
        """Get page for a session, creating one if needed (for backwards compatibility).

        Unlike get_session_page() which raises ValueError if no session exists,
        this method will create a new page as fallback when session_id is None.
        Use this for browser tools that may be called before sap_login().

        Args:
            session_id: Session ID or None for primary/default session

        Returns:
            Playwright Page for the session (existing or newly created)
        """
        # If explicit session specified, use registry only
        if session_id is not None:
            return self._registry.get_page(session_id)

        # If session=None and s1 exists, use s1
        if self._registry.has_session("s1"):
            return self._registry.get_page("s1")

        # Backwards compatibility: if no sessions registered, use legacy get_current_page
        # This creates a page if needed (important for browser_navigate before sap_login)
        return await self.get_current_page()

    async def initialize(self) -> None:
        """Initialize the browser manager and start the browser."""
        if self._initialized:
            return

        settings = self._settings or get_settings()

        self._playwright = await async_playwright().start()

        if settings.browser_mode == BrowserMode.CONNECT:
            await self._connect_to_existing_browser()
        else:
            await self._launch_browser()

        self._initialized = True

    async def _launch_browser(self) -> None:
        """Launch a new browser instance."""
        settings = self._settings or get_settings()
        browser_type = settings.browser_type

        logger.info("Launching %s browser...", browser_type)

        if self._playwright is None:
            raise RuntimeError("Playwright not initialized")

        launcher = getattr(self._playwright, str(browser_type))
        self._browser = await launcher.launch(headless=settings.browser_headless)

        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,  # SAP systems often use self-signed certificates
        )

        logger.info("Browser launched successfully")

    async def _connect_to_existing_browser(self) -> None:
        """Connect to an existing browser via CDP."""
        settings = self._settings or get_settings()

        logger.info("Connecting to browser at %s...", settings.cdp_url)

        if self._playwright is None:
            raise RuntimeError("Playwright not initialized")

        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(settings.cdp_url)

            # Get existing contexts or create new one
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                logger.info("Connected to existing browser context")
            else:
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,  # SAP systems often use self-signed certificates
                )
                logger.info("Created new context in connected browser")

        except Exception as e:
            # Provide helpful platform-specific commands
            chrome_commands = (
                "\n\nStart Chrome with remote debugging:\n"
                "  Windows (PowerShell):\n"
                '    & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
                "--remote-debugging-port=9222 "
                '--user-data-dir="C:\\temp\\chrome-debug" '
                "--ignore-certificate-errors\n"
                "  macOS:\n"
                "    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
                "--remote-debugging-port=9222 "
                '--user-data-dir="/tmp/chrome-debug" '
                "--ignore-certificate-errors\n"
                "  Linux:\n"
                "    google-chrome --remote-debugging-port=9222 "
                '--user-data-dir="/tmp/chrome-debug" '
                "--ignore-certificate-errors"
            )
            raise RuntimeError(
                f"Failed to connect to browser at {settings.cdp_url}. " f"Error: {e}" f"{chrome_commands}"
            ) from e

    async def _reconnect(self) -> None:
        """Force reconnection to the browser."""
        logger.info("Reconnecting to browser...")
        self._initialized = False
        self._pages.clear()
        self._context = None
        self._browser = None
        # Don't close playwright, just reconnect
        await self.initialize()

    async def get_page(self, name: Optional[str] = None) -> Page:
        """
        Get or create a named page.

        Pages persist across tool calls, allowing for stateful interactions.
        When connecting to an existing browser, reuses existing pages.

        Args:
            name: Page name. If None, uses the default SAP page.

        Returns:
            The requested Page instance.
        """
        # Try up to 2 times (initial + 1 reconnect attempt)
        for attempt in range(2):
            try:
                return await self._get_page_internal(name)
            except Exception as e:  # pylint: disable=broad-exception-caught
                error_msg = str(e).lower()
                # Reconnect on connection issues: closed context, no tabs, or target closed
                is_connection_error = any(
                    phrase in error_msg for phrase in ["closed", "no browser tabs", "target closed", "not connected"]
                )
                if attempt == 0 and is_connection_error:
                    logger.warning("Browser connection issue (%s), attempting reconnect...", e)
                    await self._reconnect()
                else:
                    raise

        raise RuntimeError("Failed to get page after reconnect attempt")

    async def _get_page_internal(self, name: Optional[str] = None) -> Page:
        """Internal method to get a page (may throw if context is stale)."""
        if not self._initialized:
            await self.initialize()

        page_name = name or self._default_page_name

        # Check if we already have this page cached and it's still valid
        if page_name in self._pages:
            page = self._pages[page_name]
            # Verify the page is still usable by checking a property
            if not page.is_closed():
                return page
            del self._pages[page_name]

        if self._context is None:
            raise RuntimeError("Browser context not initialized")

        # When connected via CDP, try to use existing pages first
        existing_pages = self._context.pages
        if existing_pages:
            # Use the first existing page (usually the active tab)
            page = existing_pages[0]
            self._pages[page_name] = page
            logger.info("Using existing page: %s (from %d available)", page_name, len(existing_pages))
            return page

        # Only create new page if none exist (should be rare with CDP)
        settings = self._settings or get_settings()
        if settings.browser_mode == BrowserMode.CONNECT:
            # In connect mode, we should never need to create a page
            # If we get here, the CDP connection may be stale - trigger reconnect
            raise RuntimeError(
                "No browser tabs found - CDP connection may be stale. "
                "Will attempt reconnect. If this persists, ensure Chrome has at least one tab open."
            )

        page = await self._context.new_page()
        self._pages[page_name] = page
        logger.info("Created new page: %s", page_name)
        return page

    async def get_current_page(self) -> Page:
        """Get the current default SAP page."""
        return await self.get_page(self._default_page_name)

    def get_open_pages(self) -> list[str]:
        """List all open page names."""
        return [name for name, page in self._pages.items() if not page.is_closed()]

    async def close_page(self, name: str) -> None:
        """Close a specific page."""
        if name in self._pages:
            page = self._pages[name]
            if not page.is_closed():
                await page.close()
            del self._pages[name]

    async def close(self) -> None:
        """Close the browser and cleanup all resources."""
        settings = self._settings or get_settings()

        for page in list(self._pages.values()):
            if not page.is_closed():
                await page.close()
        self._pages.clear()

        if self._context and settings.browser_mode == BrowserMode.LAUNCH:
            await self._context.close()

        if self._browser:
            if settings.browser_mode == BrowserMode.LAUNCH:
                await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self._initialized = False
        logger.info("Browser manager closed")


# Global browser manager instance (singleton)
_browser_manager: Optional[BrowserManager] = None


async def get_browser_manager() -> BrowserManager:
    """
    Get the global browser manager instance.

    The browser manager is created and initialized on first call.
    """
    global _browser_manager  # pylint: disable=global-statement
    if _browser_manager is None:
        _browser_manager = BrowserManager()
        await _browser_manager.initialize()
    return _browser_manager


async def close_browser_manager() -> None:
    """Close the global browser manager and release resources."""
    global _browser_manager  # pylint: disable=global-statement
    if _browser_manager is not None:
        await _browser_manager.close()
        _browser_manager = None
