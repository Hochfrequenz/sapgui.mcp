"""Language packs: every SAP-language-dependent text in one place (#1044).

Public API:

- :func:`current` - the session's merged view (session pack, then EN); raises
  :class:`UnsupportedLanguageError` when the session language has no pack.
- :func:`universal` - the sections that match every registered language (popups, status-type
  inference, session pages, key names), usable without any session.
- :data:`INVARIANT` - texts that are the same in every logon language (an :class:`Invariant`).
- :func:`use` / :func:`set_session_language` - set the session language (tests, login).
- :func:`pack_for`, :func:`supported_languages` - the registry.

The ``X_DE`` / ``X_EN`` constants and ``bilingual_pattern`` of the former ``lang.py`` module are
re-exported from :mod:`sapguimcp.lang._legacy` until the phase-3 migrations remove their last
importer.

This package must not import ``sapguimcp.models.config``: the config imports
:func:`supported_languages` from here.
"""

from __future__ import annotations

import dataclasses
import functools
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sapguimcp.lang import _legacy
from sapguimcp.lang._legacy import *  # noqa: F403  # re-export of the former lang.py constants
from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.invariant import INVARIANT, Invariant
from sapguimcp.lang.schema import LanguagePack, UniversalView, merge, sections
from sapguimcp.lang.text import HasAlt, RegexText, Template, Text, alt_of
from sapguimcp.session_language import current_language, normalize_language, set_session_language, use_language

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "INVARIANT",
    "HasAlt",
    "Invariant",
    "LanguagePack",
    "RegexText",
    "Template",
    "Text",
    "UniversalView",
    "UnsupportedLanguageError",
    "alt_of",
    "current",
    "pack_for",
    "set_session_language",
    "supported_languages",
    "universal",
    "use",
    "view_for",
]
__all__ += _legacy.__all__

FALLBACK_LANGUAGE = "EN"

_PACKS: dict[str, LanguagePack] = {pack.code: pack for pack in (DE, EN)}
"""Registered packs in registration order (the order of :func:`supported_languages`)."""

_views: dict[str, LanguagePack] = {}
"""Merged session views by language code. Packs hold mappings and are not hashable."""


class UnsupportedLanguageError(RuntimeError):
    """The session's logon language has no language pack."""

    def __init__(self, language: str | None, feature: str) -> None:
        self.language = language
        self.supported = supported_languages()
        supported = ", ".join(self.supported)
        if language is None:
            message = (
                f"{feature} needs the session's logon language, but none is known; "
                f"log in first (supported: {supported})"
            )
        else:
            message = f"{feature} needs a language pack for {language}; supported: {supported}"
        super().__init__(message)


def supported_languages() -> tuple[str, ...]:
    """SAP language keys that have a pack, in registration order (``("DE", "EN")``)."""
    return tuple(_PACKS)


def pack_for(code: str) -> LanguagePack:
    """The registered (unmerged) pack for ``code``; :class:`UnsupportedLanguageError` if none."""
    normalized = normalize_language(code)
    pack = _PACKS.get(normalized) if normalized is not None else None
    if pack is None:
        raise UnsupportedLanguageError(normalized, "this lookup")
    return pack


def _build_view(code: str) -> LanguagePack:
    """Merge each section per its ``MERGE`` mode; scalar pack fields come from the session pack."""
    session = _PACKS[code]
    every = [session, *(pack for pack in _PACKS.values() if pack is not session)]
    session_en = [session] if code == FALLBACK_LANGUAGE else [session, _PACKS[FALLBACK_LANGUAGE]]
    merged = {
        name: merge([getattr(pack, name) for pack in (every if section.MERGE == "all" else session_en)])
        for name, section in sections(session)
    }
    return dataclasses.replace(session, **merged)


def view_for(code: str) -> LanguagePack:
    """The merged view for ``code``: every section merged per its ``MERGE`` mode, cached."""
    pack = pack_for(code)
    view = _views.get(pack.code)
    if view is None:
        view = _views[pack.code] = _build_view(pack.code)
    return view


def current(feature: str = "this tool") -> LanguagePack:
    """The merged view for the current session's language.

    Raises :class:`UnsupportedLanguageError` (naming ``feature``) when no language is known or
    the language has no pack.
    """
    code = current_language()
    if code is None or code not in _PACKS:
        raise UnsupportedLanguageError(code, feature)
    return view_for(code)


@functools.cache
def universal() -> UniversalView:
    """The ``all`` sections merged over every registered pack, in registration order."""
    packs = list(_PACKS.values())
    return UniversalView(
        **{
            field.name: merge([getattr(pack, field.name) for pack in packs])
            for field in dataclasses.fields(UniversalView)
        }
    )


@contextmanager
def use(code: str | None) -> Iterator[None]:
    """Temporarily set the session language: ``with lang.use("DE"): lang.current()``."""
    with use_language(code):
        yield
