"""Tests for BackendManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.manager import (
    BackendManager,
)
from sapguimcp.backend.webgui.models.session_registry import SessionRegistry
from sapguimcp.session_language import current_language, use_language


@pytest.mark.anyio
async def test_webgui_get_or_create_sets_session_language() -> None:
    """WebGUI reads the language from the browser manager's registry (the one the backend writes)."""
    registry = SessionRegistry()
    for code in ("DE", "EN", None):  # s3 has no recorded language
        page = MagicMock()
        page.is_closed.return_value = False
        sid = registry.register(page)
        registry.set_language(sid, code)
    browser_manager = MagicMock()
    browser_manager.registry = registry
    browser_manager.get_or_create_session_page_checked = AsyncMock(
        side_effect=lambda session, *_: registry.get_page(session)
    )
    manager = BackendManager(backend_type="webgui")
    with (
        patch("sapguimcp.backend.manager.get_browser_manager", AsyncMock(return_value=browser_manager)),
        use_language(None),
    ):
        await manager.get_or_create(session="s2")
        assert current_language() == "EN"
        await manager.get_or_create()
        assert current_language() == "DE"
        # Cached backend path (same page) sets it too.
        await manager.get_or_create(session="s2")
        assert current_language() == "EN"
        await manager.get_or_create(session="s3")
        assert current_language() is None
