"""The SAP logon language of the session the current tool call works on (#1044).

A context variable, so concurrent tool calls on different sessions never see each other's
language. ``BackendManager.get_or_create`` sets it for every tool call, ``sap_login`` sets it for
the session it just opened, and desktop recovery clears it. ``ComThread.run`` copies the caller's
context to the COM worker, so the value is visible inside COM closures too.

Phase 1 of #1044: this module only carries the language. The language packs of phase 2 build on
it (``lang.current()``).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from sapguimcp.utils import SapLanguage, as_sap_language

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

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


def session_sap_language() -> SapLanguage:
    """The current session's language narrowed to what the tools handle today.

    Falls back to the configured default system's language when the session language is
    unknown — the behaviour before #1044. Phase 2 replaces this with the language packs.
    """
    code = current_language()
    if code is None:
        # Imported on the fallback path only: the models package imports widely, and this
        # module must stay cheap to import from the backends.
        from sapguimcp.models.config import get_sap_config  # noqa: PLC0415

        code = get_sap_config().get_default().language
        logger.debug("session language unknown, using the default system's", extra={"language": code})
    return as_sap_language(code)
