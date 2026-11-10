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


@pytest.mark.anyio
async def test_post_login_setup_does_not_re_register_a_known_page() -> None:
    with use_language(None):
        backend, registry = _make_backend("de")
        registry.register(MagicMock())  # s1, since closed
        known = registry.register(backend._page)  # s2 survives
        registry.unregister("s1")
        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)),
            patch.object(type(backend), "_capture_sap_identity", new=AsyncMock()),
        ):
            await backend._post_login_setup("https://sap.example", "100", None, "EN")

        assert registry.session_id_of(backend._page) == known
        assert len(registry.list_sessions()) == 1
        assert registry.language_of(known) == "DE"


@pytest.mark.anyio
async def test_post_login_setup_without_request_keeps_the_existing_language() -> None:
    with use_language(None):
        backend, registry = _make_backend("")
        known = registry.register(backend._page)
        registry.set_language(known, "DE")
        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)),
            patch.object(type(backend), "_capture_sap_identity", new=AsyncMock()),
        ):
            await backend._post_login_setup("https://sap.example", "100", None, None)

        assert registry.language_of(known) == "DE"
        assert current_language() == "DE"


@pytest.mark.anyio
async def test_login_already_logged_in_passes_no_requested_language() -> None:
    backend, _registry = _make_backend("")
    backend._page.goto = AsyncMock()
    backend._page.wait_for_load_state = AsyncMock()
    with (
        patch.object(type(backend), "_find_okcode_field", new=AsyncMock(return_value=object())),
        patch.object(type(backend), "_post_login_setup", new=AsyncMock()) as setup,
    ):
        result = await backend.login("https://sap.example", "u", "p", "100", "EN")

    assert result.already_logged_in is True
    assert setup.await_args.args[3] is None


@pytest.mark.anyio
async def test_read_page_language_maps_iso_code_to_sap_key() -> None:
    backend, _registry = _make_backend("de-DE")
    assert await backend._read_page_language() == "DE"


@pytest.mark.anyio
async def test_read_page_language_returns_none_when_evaluate_raises() -> None:
    backend, _registry = _make_backend("de")
    backend._page.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
    assert await backend._read_page_language() is None
