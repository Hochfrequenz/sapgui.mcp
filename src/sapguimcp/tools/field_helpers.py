"""Shared helpers for filling SAP transaction initial-screen fields."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.lang import LanguagePack
    from sapguimcp.lang.text import Text


logger = logging.getLogger(__name__)

# How long to wait for F7 navigation to complete before declaring failure.
_F7_POLL_INTERVAL_MS = 500
_F7_MAX_POLLS = 10  # 10 * 500ms = 5 seconds max wait


async def toggle_to_change_mode(backend: DesktopBackend, t: LanguagePack) -> str | None:
    """Click Display<->Change toggle button. Retries once after 1s wait.

    The toggle button may not be rendered immediately after F7 navigation,
    so a single retry with a short wait is needed for reliability.

    Args:
        backend: The SAP UI backend instance.
        t: The session's language pack (``lang.current()``), resolved by the calling tool.

    Returns:
        None on success, or an error message string on failure.
    """
    for toggle_attempt in range(2):
        if toggle_attempt > 0:
            await asyncio.sleep(1.0)
        for toggle_label in t.common.display_change_toggle:
            try:
                await backend.click_button(toggle_label)
                await backend.wait_for_ready()
                await backend.dismiss_language_dialog()
                return None
            except ValueError:
                continue
    return "Could not find 'Display <-> Change' toggle button"


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


async def fill_and_display(
    backend: DesktopBackend,
    labels: Sequence[str],
    name: str,
    t: LanguagePack,
    *,
    tcode_label: str = "object",
    initial_title: Text | None = None,
) -> str | None:
    """Fill the initial-screen field and press F7 (Display).

    Retries once if still on the initial screen after F7, because SAP's
    WebGUI sometimes doesn't register the field fill on the first attempt
    (especially after ``/n`` navigation in batch mode).

    Args:
        backend: The SAP UI backend instance.
        labels: DE/EN label variants for the input field.
        name: The object name to look up (e.g. class name, FM name).
        t: The session's language pack (``lang.current()``), resolved by the calling tool.
        tcode_label: Human-readable label for error messages (e.g. "class", "function module").
        initial_title: Title variants of the transaction's initial screen; defaults to
            ``t.common.initial_screen`` (for transactions whose title lacks that fragment, e.g. SE93).

    Returns:
        None on success, or an error message string on failure.
    """
    upper_name = name.upper()
    initial = initial_title if initial_title is not None else t.common.initial_screen

    for attempt in range(2):
        if attempt > 0:
            logger.info("Retrying fill+F7 for %s (attempt %d)", name, attempt + 1)
            # Extra wait before retry — SAP may need time to render after /n reset.
            await asyncio.sleep(0.5)

        filled = await fill_field_with_keyboard(backend, labels, upper_name)
        if not filled:
            if attempt == 0:
                logger.warning("Field not found on first attempt, will retry")
                continue
            return f"Could not find {tcode_label} field"

        # Brief wait for SAP to register the typed value before pressing F7.
        await asyncio.sleep(0.3)

        # Click display (F7)
        await backend.press_key("F7")
        await backend.wait_for_ready()

        # Check for definitive "not found" error — no retry needed.
        status = await backend.get_status_bar()
        status_text = status.message or ""
        if status_text and (t.common.not_found.contains(status_text) or t.common.does_not_exist.contains(status_text)):
            return f"{tcode_label.capitalize()} '{name}' not found"  # lang-ok: our own message

        # Poll: wait for the page to leave the initial screen.
        # Use screen title (via get_screen_info) rather than ARIA snapshot substring
        # matching, which is fragile across SAP language variants.
        # Initial screen titles contain common.initial_screen ("Einstieg", "Initial").
        navigated = False
        for poll in range(_F7_MAX_POLLS):
            screen = await backend.get_screen_info()
            if not initial.contains(screen.title or ""):
                navigated = True
                break
            logger.debug("Still on initial screen, poll %d/%d", poll + 1, _F7_MAX_POLLS)
            await asyncio.sleep(_F7_POLL_INTERVAL_MS / 1000)

        if navigated:
            return None

    # Include status bar text for debugging.
    final_status = await backend.get_status_bar()
    status_hint = f" (status: {final_status.message})" if final_status.message else ""

    return f"{tcode_label.capitalize()} '{name}' not found (still on initial screen after retries){status_hint}"
