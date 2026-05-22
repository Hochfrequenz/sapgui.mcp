"""Unit tests for field_helpers — initial screen detection logic."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.tools.field_helpers import fill_and_display, fill_field_with_keyboard


def _make_backend(
    *,
    fill_returns: bool = True,
    status_message: str = "",
    status_type: str = "",
    screen_titles: list[str] | None = None,
) -> AsyncMock:
    """Create a mock backend for fill_and_display tests."""
    backend = AsyncMock()
    backend.backend_type = "webgui"

    # fill_field_with_keyboard result (via evaluate_javascript + type_text)
    backend.evaluate_javascript = AsyncMock(return_value=fill_returns)
    backend.type_text = AsyncMock()

    # Status bar
    sbar = MagicMock()
    sbar.message = status_message
    sbar.type = status_type
    backend.get_status_bar = AsyncMock(return_value=sbar)

    # Screen info — cycles through provided titles
    titles = screen_titles or ["Display Screen"]
    call_count = 0

    async def get_screen_info() -> MagicMock:
        nonlocal call_count
        info = MagicMock()
        info.title = titles[min(call_count, len(titles) - 1)]
        call_count += 1
        return info

    backend.get_screen_info = get_screen_info
    backend.wait_for_ready = AsyncMock()

    return backend


@pytest.mark.anyio
async def test_fill_and_display_navigates_away_from_initial_screen():
    """fill_and_display returns None (success) when screen title changes."""
    backend = _make_backend(screen_titles=["Function Builder: Display FM"])
    result = await fill_and_display(backend, ["Function Module"], "RFC_READ_TABLE")
    assert result is None


@pytest.mark.anyio
async def test_fill_and_display_detects_de_initial_screen():
    """fill_and_display detects DE initial screen via 'Einstieg' in title."""
    backend = _make_backend(screen_titles=["Function Builder: Einstiegsbild"] * 20)
    result = await fill_and_display(backend, ["Funktionsbaustein"], "ZZZFAKE")
    assert result is not None
    assert "not found" in result.lower()


@pytest.mark.anyio
async def test_fill_and_display_detects_en_initial_screen():
    """fill_and_display detects EN initial screen via 'Initial' in title."""
    backend = _make_backend(screen_titles=["Function Builder: Initial Screen"] * 20)
    result = await fill_and_display(backend, ["Function Module"], "ZZZFAKE")
    assert result is not None
    assert "not found" in result.lower()


# ---- Desktop branch of fill_field_with_keyboard ----


@pytest.mark.anyio
async def test_fill_field_with_keyboard_desktop_delegates_to_focus_and_type():
    """On desktop, fill_field_with_keyboard uses focus_and_type instead of JS."""
    backend = AsyncMock()
    backend.backend_type = "desktop"
    backend.focus_and_type = AsyncMock(return_value=True)

    result = await fill_field_with_keyboard(backend, ["Programm", "Program"], "ZTEST")
    assert result is True
    backend.focus_and_type.assert_called_once_with("Programm", "ZTEST")


@pytest.mark.anyio
async def test_fill_field_with_keyboard_desktop_tries_all_labels():
    """On desktop, tries each label until one succeeds."""
    backend = AsyncMock()
    backend.backend_type = "desktop"
    backend.focus_and_type = AsyncMock(side_effect=[False, True])

    result = await fill_field_with_keyboard(backend, ["Programm", "Program"], "ZTEST")
    assert result is True
    assert backend.focus_and_type.call_count == 2


@pytest.mark.anyio
async def test_fill_field_with_keyboard_desktop_returns_false_when_not_found():
    """On desktop, returns False when no label matches."""
    backend = AsyncMock()
    backend.backend_type = "desktop"
    backend.focus_and_type = AsyncMock(return_value=False)

    result = await fill_field_with_keyboard(backend, ["Programm", "Program"], "ZTEST")
    assert result is False
    assert backend.focus_and_type.call_count == 2


@pytest.mark.anyio
async def test_fill_and_display_detects_not_found_status():
    """fill_and_display returns error when status bar says 'does not exist'."""
    backend = _make_backend(
        status_message="Function module ZZZFAKE does not exist",
        screen_titles=["Function Builder: Initial Screen"],
    )
    result = await fill_and_display(backend, ["Function Module"], "ZZZFAKE")
    assert result is not None
    assert "not found" in result.lower()
