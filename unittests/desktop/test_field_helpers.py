"""Unit tests for field_helpers: filling a field by label on the desktop backend."""

from unittest.mock import AsyncMock

import pytest

from sapguimcp.tools.field_helpers import fill_field_with_keyboard


@pytest.mark.anyio
async def test_fill_field_with_keyboard_desktop_delegates_to_focus_and_type():
    """On desktop, fill_field_with_keyboard uses focus_and_type instead of JS."""
    backend = AsyncMock()
    backend.focus_and_type = AsyncMock(return_value=True)

    result = await fill_field_with_keyboard(backend, ["Programm", "Program"], "ZTEST")
    assert result is True
    backend.focus_and_type.assert_called_once_with("Programm", "ZTEST")


@pytest.mark.anyio
async def test_fill_field_with_keyboard_desktop_tries_all_labels():
    """On desktop, tries each label until one succeeds."""
    backend = AsyncMock()
    backend.focus_and_type = AsyncMock(side_effect=[False, True])

    result = await fill_field_with_keyboard(backend, ["Programm", "Program"], "ZTEST")
    assert result is True
    assert backend.focus_and_type.call_count == 2


@pytest.mark.anyio
async def test_fill_field_with_keyboard_desktop_returns_false_when_not_found():
    """On desktop, returns False when no label matches."""
    backend = AsyncMock()
    backend.focus_and_type = AsyncMock(return_value=False)

    result = await fill_field_with_keyboard(backend, ["Programm", "Program"], "ZTEST")
    assert result is False
    assert backend.focus_and_type.call_count == 2
