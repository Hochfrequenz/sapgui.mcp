"""Session registry for tracking SAP browser sessions."""

import logging
from typing import TYPE_CHECKING, Callable

from sapguimcp.models.base import SessionBindConflictError

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

__all__ = ["SessionRegistry", "SessionBindConflictError"]

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
        self._bindings: dict[str, str] = {}  # session_id -> agent_id

    @property
    def primary_session(self) -> str:
        """Primary session ID: 's1' if present, else lowest available."""
        return self._default_session_id()

    def _default_session_id(self) -> str:
        """Return the best default session: 's1' if present, else lowest available."""
        if "s1" in self._sessions:
            return "s1"
        if self._sessions:
            return min(self._sessions.keys(), key=lambda k: int(k[1:]))
        return "s1"  # will raise in caller

    def register(self, page: "Page", agent_id: str | None = None) -> str:
        """Register a page and return its session ID.

        Args:
            page: Playwright Page object (browser tab)
            agent_id: Optional agent identifier for binding

        Returns:
            Session ID (e.g., 's1', 's2')
        """
        self._counter += 1
        session_id = f"s{self._counter}"
        self._sessions[session_id] = page
        self._page_to_session[page] = session_id

        if agent_id:
            self._bindings[session_id] = agent_id

        # Auto-unregister when page closes (only attach once per page)
        if page not in self._pages_with_listeners:
            # Use closure factory to capture page value and satisfy type checker
            page.on("close", self._make_close_handler(page))
            self._pages_with_listeners.add(page)

        logger.info(
            "Registered session",
            extra={"session": session_id, "agent_id": agent_id} if agent_id else {"session": session_id},
        )
        return session_id

    def unregister(self, session_id: str) -> None:
        """Remove a session from the registry.

        Args:
            session_id: Session to remove
        """
        if session_id in self._sessions:
            page = self._sessions.pop(session_id)
            self._page_to_session.pop(page, None)
            self._bindings.pop(session_id, None)  # Clear binding
            logger.info("Unregistered session", extra={"session": session_id})

    def get_page(self, session_id: str | None) -> "Page":
        """Get the Page for a session.

        Args:
            session_id: Session ID, or None for primary session ('s1')

        Returns:
            Playwright Page object

        Raises:
            ValueError: If session not found or page is closed
        """
        sid = session_id or self._default_session_id()

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
            self._bindings.pop(sid, None)  # Clear binding
            raise ValueError(
                f"Session '{sid}' expired (tab closed). "
                "Use sap_transaction(tcode, new_window=True) to create a new session."
            )

        return page

    def has_session(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    def list_sessions(self) -> list[str]:
        """List all registered session IDs."""
        return list(self._sessions.keys())

    def get_bound_agent(self, session_id: str) -> str | None:
        """Get the agent bound to a session.

        Args:
            session_id: Session to check

        Returns:
            Agent ID or None if unbound
        """
        return self._bindings.get(session_id)

    def bind(self, session_id: str, agent_id: str, *, force: bool = False) -> None:
        """Bind a session to an agent.

        Strict by default (issue #643): if the session is already bound to a
        *different* agent, raises :class:`SessionBindConflictError`.
        Re-binding the same agent is a no-op (idempotent). Binding an
        unbound session always succeeds.

        Args:
            session_id: Session to bind
            agent_id: Agent identifier
            force: If True, take over the binding from any other agent.
                Use this only when you know the previous binder is gone
                (e.g. agent crash recovery) — otherwise prefer the strict
                default and let the caller resolve the conflict.

        Raises:
            SessionBindConflictError: when ``force=False`` and the session
                is already bound to a different agent.
        """
        current = self._bindings.get(session_id)
        if current is not None and current != agent_id and not force:
            raise SessionBindConflictError(
                session_id=session_id,
                current_agent=current,
                requested_agent=agent_id,
            )
        self._bindings[session_id] = agent_id
        if current is not None and current != agent_id:
            # Force-take-over: log distinctly so operators can correlate.
            logger.info(
                "Replaced session binding (force=True)",
                extra={
                    "session": session_id,
                    "previous_agent": current,
                    "agent_id": agent_id,
                },
            )
        else:
            logger.info("Bound session to agent", extra={"session": session_id, "agent_id": agent_id})

    def release(self, session_id: str) -> None:
        """Release agent binding from a session.

        Args:
            session_id: Session to release
        """
        if session_id in self._bindings:
            old_agent = self._bindings.pop(session_id)
            logger.info("Released session from agent", extra={"session": session_id, "agent_id": old_agent})

    def check_binding(self, session_id: str, agent_id: str | None, tool_name: str) -> None:
        """Check if agent is authorized to access session.

        Logs warnings for:
        - Bound session accessed without agent_id
        - Bound session accessed by different agent

        Operations always proceed (warn but allow).

        Args:
            session_id: Session being accessed
            agent_id: Agent making the request (or None)
            tool_name: Name of tool for logging context
        """
        bound_agent = self._bindings.get(session_id)

        if bound_agent is None:
            return  # Unbound session, no check

        if agent_id is None:
            logger.warning(
                "Bound session accessed without agent_id",
                extra={"session": session_id, "bound_to": bound_agent, "tool": tool_name},
            )
        elif agent_id != bound_agent:
            logger.warning(
                "Cross-agent session access",
                extra={
                    "session": session_id,
                    "bound_to": bound_agent,
                    "accessed_by": agent_id,
                    "tool": tool_name,
                },
            )

    def _make_close_handler(self, page: "Page") -> Callable[["Page"], None]:
        """Create a close handler that captures the page value.

        This factory function ensures the page is captured at creation time
        (avoiding closure issues) while satisfying Playwright's type signature.
        """

        def handler(_closing_page: "Page") -> None:
            self._on_page_closed(page)

        return handler

    def _on_page_closed(self, page: "Page") -> None:
        """Handle page close event - auto-unregister."""
        # Clean up listener tracking
        self._pages_with_listeners.discard(page)

        if page in self._page_to_session:
            session_id = self._page_to_session.pop(page)
            self._sessions.pop(session_id, None)
            self._bindings.pop(session_id, None)  # Clear binding
            logger.info("Session auto-unregistered (page closed)", extra={"session": session_id})

    async def setup_context_listeners(self, context: "BrowserContext") -> None:
        """Attach event listeners to browser context.

        Call once after context creation to enable auto-cleanup.
        """
        context.on("page", self._on_page_created)

    def _on_page_created(self, page: "Page") -> None:
        """Handle new page creation - attach close listener if not already attached."""
        if page not in self._pages_with_listeners:
            # Use closure factory to capture page value and satisfy type checker
            page.on("close", self._make_close_handler(page))
            self._pages_with_listeners.add(page)
