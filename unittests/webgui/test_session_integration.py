"""Integration tests for session management with real Playwright browser.

These tests require Playwright with Chromium browser installed.
They are skipped in CI where browsers are not available.
"""

import asyncio

import pytest


@pytest.fixture
async def browser_context():
    """Real Playwright browser context for testing.

    Skips the test if Playwright browsers are not installed.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            yield context
            await browser.close()
    except Exception as e:  # pylint: disable=broad-exception-caught
        if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
            pytest.skip(f"Playwright browsers not installed: {e}")
        raise


class TestSessionRegistryIntegration:
    """Integration tests with real browser (no SAP)."""

    @pytest.mark.anyio
    async def test_register_real_page(self, browser_context) -> None:
        """Test registering a real Playwright page."""
        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        page = await browser_context.new_page()

        session_id = registry.register(page)

        assert session_id == "s1"
        assert registry.get_page("s1") is page

    @pytest.mark.anyio
    async def test_page_close_auto_unregisters(self, browser_context) -> None:
        """Test that closing page triggers auto-unregister."""
        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        page = await browser_context.new_page()

        session_id = registry.register(page)
        assert registry.has_session(session_id)

        await page.close()

        # Give event time to fire
        await asyncio.sleep(0.1)

        assert not registry.has_session(session_id)

    @pytest.mark.anyio
    async def test_multiple_pages_independent(self, browser_context) -> None:
        """Test multiple pages are tracked independently."""
        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()

        page1 = await browser_context.new_page()
        page2 = await browser_context.new_page()

        sid1 = registry.register(page1)
        sid2 = registry.register(page2)

        assert sid1 == "s1"
        assert sid2 == "s2"
        assert registry.get_page("s1") is page1
        assert registry.get_page("s2") is page2

        # Navigate page1, page2 should be unaffected
        await page1.goto("about:blank")
        assert registry.get_page("s2") is page2

    @pytest.mark.anyio
    async def test_get_page_none_returns_primary(self, browser_context) -> None:
        """Test get_page(None) returns primary session."""
        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        page = await browser_context.new_page()
        registry.register(page)

        assert registry.get_page(None) is page

    @pytest.mark.anyio
    async def test_closed_page_raises_and_cleans(self, browser_context) -> None:
        """Test accessing closed page raises ValueError and cleans up."""
        from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

        registry = SessionRegistry()
        page = await browser_context.new_page()
        registry.register(page)
        await page.close()
        await asyncio.sleep(0.1)

        with pytest.raises(ValueError, match="not found|expired"):
            registry.get_page("s1")
