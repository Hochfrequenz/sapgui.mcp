"""
Browser manager for persistent Playwright sessions.

This module provides a BrowserManager class that maintains a persistent browser
session across multiple tool calls, following the dev-browser pattern.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from sapwebguimcp.models.config import BrowserMode, SapWebGuiSettings, get_settings
from sapwebguimcp.models.session_registry import SessionRegistry

__all__ = [
    "BrowserManager",
    "get_browser_manager",
    "close_browser_manager",
]

logger = logging.getLogger(__name__)


_DOCKER_COMPOSE_CMD = "docker compose up -d cdp-proxy"
_DOCKER_DIAGNOSTIC_CMDS = (
    "Diagnostic commands:\n" + "  docker network ls | grep sapwebguimcp\n" + "  docker ps | grep cdp-proxy"
)


def _chrome_debug_commands() -> str:
    """Return platform-specific commands to start Chrome with remote debugging."""
    return (
        "Start Chrome with remote debugging:\n"
        "  Windows (PowerShell):\n"
        '    & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
        "--remote-debugging-port=9222 "
        '--user-data-dir="C:\\temp\\chrome-debug" '
        "--ignore-certificate-errors\n"
        "\n"
        "  NOTE: Your Chrome path may differ! Common locations on Windows:\n"
        '    - "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" (system-wide install)\n'
        '    - "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe" (per-user install)\n'
        "  To find your Chrome path: right-click the Chrome shortcut on your desktop or\n"
        '  Start menu → Properties → copy the "Target" field.\n'
        "\n"
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

    def get_session_page_checked(self, session_id: str | None, agent_id: str | None, tool_name: str) -> Page:
        """Get page for a session with binding check.

        Like get_session_page() but also checks agent binding and logs
        warnings for cross-agent access.

        Args:
            session_id: Session ID or None for primary session ('s1')
            agent_id: Agent making the request (or None)
            tool_name: Name of tool for logging context

        Returns:
            Playwright Page object

        Raises:
            ValueError: If session not found or page is closed
        """
        sid = session_id or "s1"
        self.registry.check_binding(sid, agent_id, tool_name)
        return self.registry.get_page(sid)

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
            "or use sap_transaction(tcode, new_window=True) to create additional sessions."
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

    async def get_or_create_session_page_checked(
        self, session_id: str | None, agent_id: str | None, tool_name: str
    ) -> Page:
        """Get page for a session with binding check, creating one if needed.

        Combines get_or_create_session_page() with agent binding checks.
        Use this for browser tools that may be called before sap_login() but
        should still respect agent bindings when sessions exist.

        Args:
            session_id: Session ID or None for primary/default session
            agent_id: Agent making the request (or None)
            tool_name: Name of tool for logging context

        Returns:
            Playwright Page for the session (existing or newly created)
        """
        # If explicit session specified, use registry with binding check
        if session_id is not None:
            self.registry.check_binding(session_id, agent_id, tool_name)
            return self._registry.get_page(session_id)

        # If session=None and s1 exists, use s1 with binding check
        if self._registry.has_session("s1"):
            self.registry.check_binding("s1", agent_id, tool_name)
            return self._registry.get_page("s1")

        # Backwards compatibility: if no sessions registered, use legacy get_current_page
        # No binding check needed - no sessions exist yet (pre-login scenario)
        return await self.get_current_page()

    async def initialize(self) -> None:
        """Initialize the browser manager and start the browser."""
        if self._initialized:
            return

        settings = self._settings or get_settings()

        self._playwright = await async_playwright().start()

        # Default is CONNECT: expects Chrome already running with --remote-debugging-port=9222.
        # This is required for exe distribution (no Playwright browser binaries bundled)
        # and matches the documented setup where users start Chrome before the MCP server.
        # LAUNCH mode is opt-in for development; requires `playwright install` for browser binaries.
        if settings.browser_mode == BrowserMode.CONNECT:
            await self._connect_to_existing_browser()
        else:
            await self._launch_browser()

        self._initialized = True

    async def _launch_browser(self) -> None:
        """Launch a new browser instance via Playwright.

        Requires Playwright browser binaries (installed via `playwright install`).
        Not available in PyInstaller exe builds. Use BROWSER_MODE=launch explicitly.
        """
        settings = self._settings or get_settings()
        browser_type = settings.browser_type

        logger.info("Launching browser", extra={"browser_type": browser_type})

        if self._playwright is None:
            raise RuntimeError("Playwright not initialized")

        launcher = getattr(self._playwright, str(browser_type))
        self._browser = await launcher.launch(headless=settings.browser_headless)

        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,  # SAP systems often use self-signed certificates
        )

        logger.info("Browser launched")

    async def _connect_to_existing_browser(self) -> None:
        """Connect to an existing Chrome browser via CDP (default mode).

        Expects Chrome running with --remote-debugging-port (default: 9222).
        Does not require Playwright browser binaries — only the Python package.
        """
        settings = self._settings or get_settings()

        logger.info("Connecting to browser", extra={"cdp_url": settings.cdp_url})

        if self._playwright is None:
            raise RuntimeError("Playwright not initialized")

        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(settings.cdp_url)

            # Get existing contexts or create new one
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                logger.info("Connected to existing browser context", extra={"contexts": len(contexts)})
            else:
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,  # SAP systems often use self-signed certificates
                )
                logger.info("Created new context in connected browser", extra={"cdp_url": settings.cdp_url})

        except Exception as e:
            error_msg = str(e).lower()
            parsed_url = urlparse(settings.cdp_url) if settings.cdp_url else None
            cdp_host = parsed_url.hostname if parsed_url else ""

            # Detect invalid URL format
            if "invalid url" in error_msg:
                raise RuntimeError(
                    f"Invalid CDP_URL format: '{settings.cdp_url}'\n\n"
                    f"Expected format: http://hostname:port (e.g., http://localhost:9222)\n\n"
                    f"Original error: {e}"
                ) from e

            # Detect Docker network issues (DNS resolution failure for cdp-proxy)
            if cdp_host == "cdp-proxy" and any(
                phrase in error_msg
                for phrase in [
                    "nodename nor servname",  # macOS
                    "name or service not known",  # Linux
                    "getaddrinfo",  # General
                    "enotfound",  # Windows/Node.js
                    "temporary failure in name resolution",  # Linux
                    "no such host",  # Windows
                ]
            ):
                raise RuntimeError(
                    f"Cannot resolve hostname 'cdp-proxy'. This usually means:\n\n"
                    f"1. The Docker network 'sapwebguimcp_default' does not exist, or\n"
                    f"2. The cdp-proxy service is not running\n\n"
                    f"Solution: Run this command first:\n"
                    f"  {_DOCKER_COMPOSE_CMD}\n\n"
                    f"This starts the CDP proxy and creates the required Docker network.\n\n"
                    f"{_DOCKER_DIAGNOSTIC_CMDS}\n\n"
                    f"Original error: {e}"
                ) from e

            # Detect connection refused (service not running)
            if any(
                phrase in error_msg for phrase in ["connection refused", "connect econnrefused", "actively refused"]
            ):
                if cdp_host == "cdp-proxy":
                    raise RuntimeError(
                        f"Connection refused by cdp-proxy at {settings.cdp_url}.\n\n"
                        f"The CDP proxy container is not running. Start it with:\n"
                        f"  {_DOCKER_COMPOSE_CMD}\n\n"
                        f"Then ensure Chrome is running with remote debugging enabled.\n\n"
                        f"Original error: {e}"
                    ) from e
                raise RuntimeError(
                    f"Connection refused at {settings.cdp_url}.\n\n"
                    f"Chrome is not running or not accepting CDP connections.\n"
                    f"{_chrome_debug_commands()}\n\n"
                    f"Original error: {e}"
                ) from e

            # Generic fallback with context-aware help
            if cdp_host == "cdp-proxy":
                raise RuntimeError(
                    f"Failed to connect to browser via CDP proxy at {settings.cdp_url}.\n\n"
                    f"Checklist:\n"
                    f"1. Is the Docker network created? Run: {_DOCKER_COMPOSE_CMD}\n"
                    f"2. Is Chrome running with --remote-debugging-port=9222?\n"
                    f"3. Is the CDP proxy forwarding correctly?\n\n"
                    f"{_DOCKER_DIAGNOSTIC_CMDS}\n\n"
                    f"Original error: {e}"
                ) from e

            # Fallback for non-Docker setups
            raise RuntimeError(
                f"Failed to connect to browser at {settings.cdp_url}.\n\n"
                f"{_chrome_debug_commands()}\n\n"
                f"Original error: {e}"
            ) from e

    async def _reconnect(self) -> None:
        """Force reconnection to the browser."""
        logger.info("Reconnecting to browser")
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
                    logger.warning("Browser connection issue, attempting reconnect", extra={"error": str(e)})
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
            logger.info("Using existing page", extra={"page": page_name, "available": len(existing_pages)})
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
        logger.info("Created new page", extra={"page": page_name})
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
