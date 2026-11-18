"""Shared helpers for filling SAP transaction initial-screen fields."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend


async def fill_field_with_keyboard(
    backend: DesktopBackend,
    labels: Sequence[str],
    value: str,
) -> bool:
    """Find an input field by label, focus it, and type the value with real keyboard events.

    Args:
        backend: The SAP UI backend instance.
        labels: List of DE/EN label variants to match against the ``title`` attribute.
        value: The value to type into the field.

    Returns:
        True if the field was found and filled, False otherwise.
    """
    return await _fill_field_with_keyboard_desktop(backend, labels, value)


async def _fill_field_with_keyboard_desktop(backend: DesktopBackend, labels: Sequence[str], value: str) -> bool:
    """Desktop backend uses COM — no JavaScript available.

    Falls back to focus_and_type which uses COM field resolution.
    """
    for lbl in labels:
        if await backend.focus_and_type(lbl, value):
            return True
    return False
