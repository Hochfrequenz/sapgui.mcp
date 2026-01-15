"""Session registry for tracking SAP browser sessions."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

__all__ = ["SessionRegistry"]

logger = logging.getLogger(__name__)


class SessionRegistry:
    """Tracks SAP sessions with automatic lifecycle management.

    Each session maps to a browser tab (Playwright Page). The registry:
    - Assigns sequential IDs (s1, s2, s3...)
    - Auto-unregisters when tabs close (via event listener)
    - Validates sessions are still open on access
    """

    def __init__(self) -> None:
        self._sessions: dict[str, "Page"] = {}
        self._counter: int = 0
        self._page_to_session: dict["Page", str] = {}
        self._pages_with_listeners: set["Page"] = set()  # Track pages with close listeners

    @property
    def primary_session(self) -> str:
        """Primary session ID (always 's1')."""
        return "s1"

    def register(self, page: "Page") -> str:
        """Register a page and return its session ID.

        Args:
            page: Playwright Page object (browser tab)

        Returns:
            Session ID (e.g., 's1', 's2')
        """
        self._counter += 1
        session_id = f"s{self._counter}"
        self._sessions[session_id] = page
        self._page_to_session[page] = session_id

        # Auto-unregister when page closes (only attach once per page)
        if page not in self._pages_with_listeners:
            # Capture page in lambda default arg to avoid closure issues
            page.on("close", lambda _, p=page: self._on_page_closed(p))
            self._pages_with_listeners.add(page)

        logger.info("Registered session '%s'", session_id)
        return session_id

    def unregister(self, session_id: str) -> None:
        """Remove a session from the registry.

        Args:
            session_id: Session to remove
        """
        if session_id in self._sessions:
            page = self._sessions.pop(session_id)
            self._page_to_session.pop(page, None)
            logger.info("Unregistered session '%s'", session_id)

    def get_page(self, session_id: str | None) -> "Page":
        """Get the Page for a session.

        Args:
            session_id: Session ID, or None for primary session ('s1')

        Returns:
            Playwright Page object

        Raises:
            ValueError: If session not found or page is closed
        """
        sid = session_id or "s1"

        if sid not in self._sessions:
            available = ", ".join(sorted(self._sessions.keys())) or "(none)"
            raise ValueError(
                f"Session '{sid}' not found. Active: {available}. " "Use sap_session_list() to see sessions."
            )

        page = self._sessions[sid]
        if page.is_closed():
            # Clean up stale entry
            self._sessions.pop(sid, None)
            self._page_to_session.pop(page, None)
            raise ValueError(
                f"Session '{sid}' expired (tab closed). " "Use sap_session_open() to create a new session."
            )

        return page

    def has_session(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    def list_sessions(self) -> list[str]:
        """List all registered session IDs."""
        return list(self._sessions.keys())

    def _on_page_closed(self, page: "Page") -> None:
        """Handle page close event - auto-unregister."""
        # Clean up listener tracking
        self._pages_with_listeners.discard(page)

        if page in self._page_to_session:
            session_id = self._page_to_session.pop(page)
            self._sessions.pop(session_id, None)
            logger.info("Session '%s' auto-unregistered (page closed)", session_id)

    async def setup_context_listeners(self, context: "BrowserContext") -> None:
        """Attach event listeners to browser context.

        Call once after context creation to enable auto-cleanup.
        """
        context.on("page", self._on_page_created)

    def _on_page_created(self, page: "Page") -> None:
        """Handle new page creation - attach close listener if not already attached."""
        if page not in self._pages_with_listeners:
            # Capture page in lambda default arg to avoid closure issues
            page.on("close", lambda _, p=page: self._on_page_closed(p))
            self._pages_with_listeners.add(page)
