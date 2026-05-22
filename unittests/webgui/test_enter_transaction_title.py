"""Regression test: enter_transaction must return the NEW page title, not the previous one."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from sapguimcp.models.sap_results import TransactionResult


@pytest.mark.anyio
async def test_enter_transaction_returns_new_title_after_slow_navigation():
    """When OK-code clears before title updates, enter_transaction should poll for new title.

    Reproduces Bug 2: title still shows previous transaction's title.
    """
    from sapguimcp.backend.webgui.backend import WebGuiBackend

    page = AsyncMock()
    page.is_closed.return_value = False

    # Title sequence: first calls return old title, then new title appears
    title_sequence = iter(
        [
            "FBL1N - Vendor Line Items",  # title_before
            "FBL1N - Vendor Line Items",  # _verify check
            "FBL1N - Vendor Line Items",  # _poll first read
            "FBL1N - Vendor Line Items",  # _poll poll iteration 1
            "IW29 - PM Orders",  # _poll poll iteration 2 → changed!
        ]
    )
    page.title = AsyncMock(side_effect=lambda: next(title_sequence))

    # OK-code field mock: verify sees cleared value → navigation confirmed
    okcode_mock = AsyncMock()
    okcode_mock.get_attribute = AsyncMock(return_value="")  # cleared
    okcode_mock.click = AsyncMock()
    page.query_selector = AsyncMock(return_value=okcode_mock)

    # Standard page mocks
    page.bring_to_front = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    page.keyboard = AsyncMock()
    page.keyboard.press = AsyncMock()

    # Create backend with mocked page — set all required attributes
    # Bypass __init__ -- update attribute list below if constructor changes
    backend = WebGuiBackend.__new__(WebGuiBackend)
    backend._page = page
    backend._keepalive_task = None

    # Mock _find_okcode_field to return a locator-like mock directly
    okcode_locator = AsyncMock()
    okcode_locator.click = AsyncMock()
    backend._find_okcode_field = AsyncMock(return_value=okcode_locator)

    result = await backend.enter_transaction("IW29")

    assert result.success is True
    assert "IW29" in result.page_title or "PM Orders" in result.page_title
    # Must NOT be the old title
    assert "FBL1N" not in result.page_title


@pytest.mark.anyio
async def test_poll_title_change_returns_on_timeout():
    """When title never changes (same-tcode navigation), _poll_title_change returns after timeout."""
    from sapguimcp.backend.webgui.backend import WebGuiBackend

    page = AsyncMock()
    # Title never changes
    page.title = AsyncMock(return_value="SE24 - Class Builder: Initial Screen")
    page.wait_for_timeout = AsyncMock()

    backend = WebGuiBackend.__new__(WebGuiBackend)
    backend._page = page
    backend._keepalive_task = None

    # Use short timeout to keep test fast
    result = await backend._poll_title_change("SE24 - Class Builder: Initial Screen", timeout_ms=500, interval_ms=100)

    assert result == "SE24 - Class Builder: Initial Screen"
    # Verify polling happened (at least one wait_for_timeout call)
    assert page.wait_for_timeout.call_count >= 1
