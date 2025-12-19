"""
Browser manager for persistent Playwright sessions.

This module provides a BrowserManager class that maintains a persistent browser
session across multiple tool calls, following the dev-browser pattern.
"""

import logging
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from sapwebguimcp.models.config import BrowserMode, SapWebGuiSettings, get_settings

__all__ = [
    "BrowserManager",
    "get_browser_manager",
    "close_browser_manager",
]

logger = logging.getLogger(__name__)


class BrowserManager:
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

    @property
    def is_initialized(self) -> bool:
        """Check if the browser manager has been initialized."""
        return self._initialized

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
            raise RuntimeError(
                f"Failed to connect to browser at {settings.cdp_url}. "
                f"Make sure browser is running with --remote-debugging-port=9222. "
                f"Error: {e}"
            ) from e

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
        if not self._initialized:
            await self.initialize()

        page_name = name or self._default_page_name

        # Check if we already have this page cached
        if page_name in self._pages:
            page = self._pages[page_name]
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

        # Only create new page if none exist
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
