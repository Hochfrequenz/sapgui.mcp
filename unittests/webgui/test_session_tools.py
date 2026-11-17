"""Unit tests for session management tools."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


class TestRegisterNewWindowSession:
    """Unit tests for WebGuiBackend._register_new_window_session."""

    @staticmethod
    def _make_backend_with_context(registry: Any, pages: list[Any]) -> Any:
        """Create a WebGuiBackend with a mock page whose context has the given pages."""
        from unittest.mock import MagicMock

        from sapguimcp.backend.webgui.backend import WebGuiBackend

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = pages
        mock_page.context = mock_context

        backend = WebGuiBackend.__new__(WebGuiBackend)
        backend._page = mock_page  # pylint: disable=protected-access
        backend._keepalive_task = None  # pylint: disable=protected-access
        return backend

    @pytest.mark.anyio
    async def test_registers_new_page_when_count_increases(self) -> None:
        """Test that new page is registered when page count increases."""
        from unittest.mock import MagicMock

        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        # Mock new page
        new_page = MagicMock()
        new_page.is_closed.return_value = False
        new_page.on = MagicMock()
        new_page.title = AsyncMock(return_value="New Transaction")

        backend = self._make_backend_with_context(registry, [MagicMock(), new_page])

        _PATCH_REGISTRY = "sapguimcp.backend.webgui.backend.WebGuiBackend._get_registry"
        with patch(_PATCH_REGISTRY, new=AsyncMock(return_value=registry)):
            session_id, count, title = await backend._register_new_window_session(pages_before=1)

        assert session_id == "s1"  # First registration
        assert count == 2
        assert title == "New Transaction"
        assert registry.has_session("s1")

    @pytest.mark.anyio
    async def test_returns_none_when_no_new_page(self) -> None:
        """Test that None is returned when page count doesn't increase."""
        from unittest.mock import MagicMock

        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        backend = self._make_backend_with_context(registry, [MagicMock()])

        _PATCH_REGISTRY = "sapguimcp.backend.webgui.backend.WebGuiBackend._get_registry"
        with patch(_PATCH_REGISTRY, new=AsyncMock(return_value=registry)):
            session_id, count, title = await backend._register_new_window_session(pages_before=1, wait_timeout_ms=100)

        assert session_id is None
        assert count == 1
        assert title is None

    @pytest.mark.anyio
    async def test_logs_warning_with_context_when_no_new_page(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that warning is logged with tcode context when no new page is detected."""
        import logging
        from unittest.mock import MagicMock

        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        backend = self._make_backend_with_context(registry, [MagicMock()])

        _PATCH_REGISTRY = "sapguimcp.backend.webgui.backend.WebGuiBackend._get_registry"
        with patch(_PATCH_REGISTRY, new=AsyncMock(return_value=registry)):
            with caplog.at_level(logging.WARNING):
                await backend._register_new_window_session(pages_before=1, tcode="VA01", wait_timeout_ms=100)

        assert "No new page detected" in caplog.text
        assert "/o prefix" in caplog.text
        # Dynamic values are now in structured extra fields
        record = caplog.records[-1]
        assert record.tcode == "VA01"
        assert record.pages_before == 1
        assert record.pages_after == 1

    @pytest.mark.anyio
    async def test_registers_last_page_when_multiple_pages_created(self) -> None:
        """Test that the last page is registered when multiple pages are created simultaneously."""
        from unittest.mock import MagicMock

        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        # Mock multiple new pages (edge case: 2 pages created at once)
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()
        page2.title = AsyncMock(return_value="Expected New Page")

        page3 = MagicMock()
        page3.is_closed.return_value = False
        page3.on = MagicMock()
        page3.title = AsyncMock(return_value="Last Page - Should Be Registered")

        backend = self._make_backend_with_context(registry, [page1, page2, page3])

        _PATCH_REGISTRY = "sapguimcp.backend.webgui.backend.WebGuiBackend._get_registry"
        with patch(_PATCH_REGISTRY, new=AsyncMock(return_value=registry)):
            session_id, count, title = await backend._register_new_window_session(pages_before=1, wait_timeout_ms=100)

        # Should register the LAST page (pages[-1])
        assert session_id == "s1"
        assert count == 3
        assert title == "Last Page - Should Be Registered"
        assert registry.has_session("s1")


class TestWebGuiCloseSession:
    """Unit tests for WebGuiBackend.close_session."""

    @pytest.mark.anyio
    async def test_closes_only_targeted_session_with_mode_local_command(self) -> None:
        """Closing one WebGUI session must not trigger SAP's exit-all command."""
        from unittest.mock import MagicMock

        from sapguimcp.backend.webgui.backend import WebGuiBackend
        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()

        ok_field = AsyncMock()

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()
        page2.query_selector = AsyncMock(return_value=ok_field)
        page2.keyboard.press = AsyncMock()
        page2.wait_for_timeout = AsyncMock()
        page2.close = AsyncMock()

        registry.register(page1)
        session_id = registry.register(page2)

        backend = WebGuiBackend.__new__(WebGuiBackend)
        backend._page = page1  # pylint: disable=protected-access
        backend._keepalive_task = None  # pylint: disable=protected-access

        patch_registry_target = "sapguimcp.backend.webgui.backend.WebGuiBackend._get_registry"
        with patch(patch_registry_target, new=AsyncMock(return_value=registry)):
            closed = await backend.close_session(session_id)

        assert closed is True
        ok_field.fill.assert_awaited_once_with("/i")
        page2.keyboard.press.assert_awaited_once_with("Enter")
        page2.close.assert_awaited_once()
        assert registry.has_session("s1")
        assert not registry.has_session(session_id)
