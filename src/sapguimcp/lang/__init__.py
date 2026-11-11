"""Language packs: every SAP-language-dependent text in one place (#1044).

Public API:

- :func:`current` - the session's merged view (session pack, then EN); raises
  :class:`UnsupportedLanguageError` when the session language has no pack.
- :func:`universal` - the sections that match every registered language (popups, status-type
  inference, session pages, key names), usable without any session.
- :data:`INVARIANT` - texts that are the same in every logon language (an :class:`Invariant`).
- :func:`use` / :func:`set_session_language` - set the session language (tests, login).
- :func:`pack_for`, :func:`supported_languages` - the registry.
- :func:`language_for_html_lang` - the SAP language key for a page's ``<html lang>``.
- ``_register_for_tests`` - registers an extra pack inside a ``with`` block (tests only).

This package must not import ``sapguimcp.models.config``: the config imports
:func:`supported_languages` from here.
"""

from __future__ import annotations

import dataclasses
import functools
from contextlib import contextmanager
from typing import TYPE_CHECKING

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
    "english_first",
    "language_for_html_lang",
    "pack_for",
    "set_session_language",
    "supported_languages",
    "universal",
    "use",
    "view_for",
]

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
        raise UnsupportedLanguageError(normalized or repr(code), "this lookup")
    return pack


def language_for_html_lang(tag: str) -> str | None:
    """SAP language key for an HTML language tag (``"de-DE"`` -> ``"DE"``).

    Matches the registered packs' ``html_lang``: the whole tag first (``zh-tw``), then the primary
    subtag (``de``), case-insensitively, ``_`` read as ``-``. A tag without a pack falls back to
    its upper-cased primary subtag, so an unsupported language is still reported by name; an empty
    tag gives ``None``.
    """
    normalized = tag.strip().lower().replace("_", "-")
    if not normalized:
        return None
    primary = normalized.split("-", 1)[0]
    by_html_lang = {pack.html_lang.lower(): pack.code for pack in _PACKS.values()}
    return by_html_lang.get(normalized) or by_html_lang.get(primary) or normalize_language(primary)


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


def english_first(text: Text, english: Text) -> Text:
    """``text`` (usually from :func:`universal`) with the variants of ``english`` (the same field of
    the EN pack) moved to the front.

    For call sites whose try order was English first before the packs, where the registration order
    (DE first) would change which element a first-match lookup picks.
    """
    first = tuple(variant for variant in text.variants if variant in english.variants)
    return dataclasses.replace(text, variants=(*first, *(v for v in text.variants if v not in first)))


@contextmanager
def use(code: str | None) -> Iterator[None]:
    """Temporarily set the session language: ``with lang.use("DE"): lang.current()``."""
    with use_language(code):
        yield


def _clear_caches() -> None:
    """Forget every merged view; the next :func:`view_for` / :func:`universal` call rebuilds it."""
    _views.clear()
    universal.cache_clear()


@contextmanager
def _register_for_tests(pack: LanguagePack) -> Iterator[LanguagePack]:
    """Register ``pack`` for the duration of a ``with`` block. Tests only (#1044, phase 2b).

    Clears the merged-view caches on enter and on exit, so :func:`view_for`, :func:`current`,
    :func:`universal` and :func:`supported_languages` see the pack inside the block and forget it
    afterwards. Refuses a code that is already registered (replacing DE or EN would change what
    other tests see) and a code that is not a normalized SAP language key.
    """
    if normalize_language(pack.code) != pack.code:
        raise ValueError(f"pack code must be an upper-case SAP language key, got {pack.code!r}")
    if pack.code in _PACKS:
        raise ValueError(f"a pack for {pack.code} is already registered")
    _PACKS[pack.code] = pack
    _clear_caches()
    try:
        yield pack
    finally:
        del _PACKS[pack.code]
        _clear_caches()
