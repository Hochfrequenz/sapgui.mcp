"""WebGUI sessions record their logon language (#1044)."""

# pylint: disable=protected-access

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.webgui.backend import WebGuiBackend
from sapguimcp.backend.webgui.models.session_registry import SessionRegistry
from sapguimcp.session_language import current_language, use_language


def _make_backend(page_language: Any) -> tuple[WebGuiBackend, SessionRegistry]:
    backend = WebGuiBackend.__new__(WebGuiBackend)
    page = MagicMock()
    page.is_closed.return_value = False
    page.evaluate = AsyncMock(return_value=page_language)
    backend._page = page
    return backend, SessionRegistry()


@pytest.mark.anyio
async def test_post_login_setup_records_the_page_language() -> None:
    with use_language(None):
        backend, registry = _make_backend("de")
        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)),
            patch.object(type(backend), "_capture_sap_identity", new=AsyncMock()),
        ):
            await backend._post_login_setup("https://sap.example", "100", None, "EN")

        session = registry.session_id_of(backend._page)
        assert session is not None
        assert registry.language_of(session) == "DE"
        assert current_language() == "DE"


@pytest.mark.anyio
async def test_post_login_setup_falls_back_to_the_requested_language() -> None:
    with use_language(None):
        backend, registry = _make_backend("")
        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)),
            patch.object(type(backend), "_capture_sap_identity", new=AsyncMock()),
        ):
            await backend._post_login_setup("https://sap.example", "100", None, "en")

        session = registry.session_id_of(backend._page)
        assert session is not None
        assert registry.language_of(session) == "EN"
        assert current_language() == "EN"


@pytest.mark.anyio
async def test_new_window_session_inherits_the_origin_language() -> None:
    with use_language(None):
        backend, registry = _make_backend("de")
        origin = registry.register(backend._page)
        registry.set_language(origin, "DE")
        new_page = MagicMock()
        new_page.is_closed.return_value = False
        new_page.title = AsyncMock(return_value="t")
        backend._page.context.pages = [backend._page, new_page]

        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)),
            patch.object(type(backend), "_wait_for_new_page", new=AsyncMock(return_value=True)),
        ):
            new_id, _count, _title = await backend._register_new_window_session(1)

        assert new_id is not None
        assert registry.language_of(new_id) == "DE"
