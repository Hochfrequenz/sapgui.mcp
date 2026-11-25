"""The SAP logon language of the session the current tool call works on (#1044).

A context variable, so concurrent tool calls on different sessions never see each other's
language. ``BackendManager.get_or_create`` sets it for every tool call, ``sap_login`` sets it for
the session it just opened, and desktop recovery clears it. ``ComThread.run`` copies the caller's
context to the COM worker, so the value is visible inside COM closures too.

Limitation: session tools that take an explicit ``session_id`` (``tools/session_tools.py``: close,
detach, bind, release, reset_to_primary) resolve the backend without a session, so the variable
holds the primary session's language there. Nothing on those paths reads it today; phase 2 must
wrap such backend methods in ``use_language(registry.language_of(session_id))`` if they ever need
texts.

This module only carries the language; the language packs (``lang.current()``) build on it. An
unknown or pack-less language is never replaced by EN: the tools that need texts raise
``lang.UnsupportedLanguageError`` instead (#1081).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_session_language: ContextVar[str | None] = ContextVar("session_language", default=None)


def normalize_language(code: str | None) -> str | None:
    """Upper-case and strip an SAP language key; empty or ``None`` becomes ``None``."""
    if code is None:
        return None
    normalized = code.strip().upper()
    return normalized or None


def current_language() -> str | None:
    """SAP language key of the current session, or ``None`` when unknown."""
    return _session_language.get()


def set_session_language(code: str | None) -> None:
    """Set the current session's language for the rest of this task (and its child tasks).

    No reset token: the value lives as long as the task's context. Tool calls run in their own
    task, so it ends with the call. Code that must restore the previous value uses
    :func:`use_language` instead.
    """
    _session_language.set(normalize_language(code))


@contextmanager
def use_language(code: str | None) -> Iterator[None]:
    """Temporarily set the session language, e.g. in tests."""
    token = _session_language.set(normalize_language(code))
    try:
        yield
    finally:
        _session_language.reset(token)
