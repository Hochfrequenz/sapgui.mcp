"""Shared helpers for the SE38/SE24/SE37 source edit tools."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend

logger = logging.getLogger(__name__)


async def describe_failed_replace(backend: WebGuiBackend | DesktopBackend, backup_source: str) -> str:
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
            "WARNING: the editor buffer could not be restored and now holds partial content. "
            "Leave SE38 WITHOUT saving, or paste backup_source back manually."
        )
    )
    return (
        "Failed to replace editor content: the editor buffer does not match new_source. "
        f"Nothing was saved or activated, so the object on the server is unchanged. {detail}"
    )
