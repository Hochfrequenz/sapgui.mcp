"""Shared helpers for the SE38/SE24/SE37 source edit tools."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar, cast

from sapguimcp.models.se24_edit_models import SE24EditResult
from sapguimcp.models.se37_edit_models import SE37EditResult
from sapguimcp.models.se38_edit_models import SE38EditResult
from sapguimcp.tools.desktop_wait_predicates import popup_closed_and_screen_changed, window_title_changed

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from sapguimcp.backend.desktop import DesktopBackend

logger = logging.getLogger(__name__)

EditResult = TypeVar("EditResult", SE24EditResult, SE37EditResult, SE38EditResult)

# Set once the edit tool itself asks for change mode: before that, the screen and any dialog may still be the user's.
# A context variable, so the navigation helpers keep their signatures; set in another task it is not seen, and then
# the editor is not left, which is the safe side.
_change_mode_requested: ContextVar[bool] = ContextVar("change_mode_requested", default=False)

REVERT_FAILED = (
    "WARNING: Auto-revert failed. The editor is left without saving. If only the syntax check failed, nothing was "
    "saved. If the activation failed (Ctrl+F3 saves first), an inactive version with the new source may remain on "
    "the server: restore it from backup_source."
)


def change_mode_requested() -> None:
    """Record that the edit tool is about to switch its own object to change mode, so it has to leave afterwards."""
    _change_mode_requested.set(True)


async def describe_failed_replace(backend: DesktopBackend, backup_source: str) -> str:
    """Recover from a failed ``replace_editor_source`` and describe the outcome.

    The write clears the editor before inserting, so a verification failure
    leaves a half-written buffer behind (#859).  Nothing has reached the
    server at this point — the object is only written on save/activate — but
    the editor must not be left holding someone else's half of two sources,
    so the backup is put back before reporting.
    """
    restored = await backend.replace_editor_source(backup_source)
    if not restored:
        logger.warning("edit_restore_failed", extra={"backup_chars": len(backup_source)})
    detail = (
        "The original source was restored into the editor."
        if restored
        else (
            "WARNING: the editor buffer could not be restored and holds partial content. "
            "It is discarded when the editor is left without saving."
        )
    )
    return (
        "Failed to replace editor content: the editor buffer does not match new_source. "
        f"Nothing was saved or activated, so the object on the server is unchanged. {detail}"
    )


async def confirm_language_dialog(
    backend: DesktopBackend, before_title: str, before_status: str, *, timeout_ms: int
) -> str | None:
    """Confirm the "Different original and logon languages" dialog if it is open; the text of any other popup.

    The dialog only exists for some objects and users: without it there is nothing to wait for. Only that dialog
    is confirmed (see :meth:`DesktopBackend.dismiss_language_dialog`); any other popup is left alone and reported,
    since Enter could accept its default action. ``before_title`` / ``before_status`` are read right before the
    action that led to the popup.
    """
    if await backend.check_popup() is None:
        return None
    try:
        await backend.dismiss_language_dialog()
        await backend.wait_for_ready()
        # screen_changed is already true because of the popup itself: wait until it is gone as well.
        await backend.wait_for_condition(
            popup_closed_and_screen_changed(before_title, before_status), timeout_ms=timeout_ms
        )
    except Exception:  # pylint: disable=broad-exception-caught  # noqa: S110
        pass
    popup = await backend.check_popup()
    if popup is not None:
        return popup.message or popup.popup_type
    return None


async def switch_to_change_mode(backend: DesktopBackend, *, toggle_wait_ms: int, dialog_wait_ms: int) -> str | None:
    """Switch the displayed object to change mode with Ctrl+F1; the text of an unexpected popup, else None.

    Ctrl+F1 because the toolbar button has no text on the desktop, so a label-based click would not find it. SAP
    asks about the original language when switching to change mode, not when displaying: that dialog is confirmed.
    """
    session = backend.require_session()
    display_title = await backend.com.run(lambda: str(cast("Any", session.find_by_id("wnd[0]")).text).strip())
    before_status = (await backend.get_status_bar()).message.strip()
    change_mode_requested()
    await backend.press_key("Ctrl+F1")
    await backend.wait_for_ready()
    if not await backend.wait_for_condition(window_title_changed(display_title), timeout_ms=toggle_wait_ms):
        logger.debug("The window title did not change after Ctrl+F1 within %d ms", toggle_wait_ms)
    return await confirm_language_dialog(backend, display_title, before_status, timeout_ms=dialog_wait_ms)


async def leave_editor_after(backend: DesktopBackend, tcode: str, edit: Awaitable[EditResult]) -> EditResult:
    """Run ``edit``, then leave ``tcode`` without saving, so the object is no longer locked (#1166).

    The editor is left on every path once ``edit`` has asked for change mode (:func:`change_mode_requested`), also
    when it fails or raises: by then the server side is settled (activated, restored, or nothing saved), and whatever
    the editor still holds is meant to be discarded. Before that point the screen and its dialogs may be the user's,
    so nothing is touched. A failed leave does not change the outcome of the edit, which is already final on the
    server: it is logged and noted in ``check_messages``, so the caller knows the lock may still be held.
    """
    token = _change_mode_requested.set(False)
    left = True
    try:
        result = await edit
    finally:
        if _change_mode_requested.get():
            try:
                left = await backend.leave_transaction_without_saving(tcode)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception("Leaving %s after the edit failed", tcode)
                left = False
        _change_mode_requested.reset(token)
    if not left:
        result.check_messages.append(
            f"The session could not leave {tcode}, so the object may still be locked. "  # lang-ok: our own message
            "Leave the transaction without saving."
        )
    return result
