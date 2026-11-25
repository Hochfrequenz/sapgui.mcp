"""Language packs: every SAP-language-dependent text in one place (#1044).

Public API:

- :func:`current` - the session's merged view (session pack, then EN); raises
  :class:`UnsupportedLanguageError` when the session language has no pack.
- :func:`universal` - the sections that match every registered language (popups, status-type
  inference, session pages, key names), usable without any session.
- :data:`INVARIANT` - texts that are the same in every logon language (an :class:`Invariant`).
- :func:`use` / :func:`set_session_language` - set the session language (tests, login).
- :func:`pack_for`, :func:`supported_languages` - the registry of full packs.
- :func:`logon_languages`, :func:`language_support` - full packs plus core packs (#1081): a core
  pack holds only the ``universal()`` sections, so a user can log on in its language and use the
  language-independent tools, while :func:`current` still raises for it.
- ``_register_for_tests`` - registers an extra pack (full or core) inside a ``with`` block (tests only).

Adding a login language: see ``ADDING_A_LANGUAGE.md`` in this package (procedure and pitfalls).

This package must not import ``sapguimcp.models.config``: the config imports
:func:`supported_languages` from here.
"""

from __future__ import annotations

import dataclasses
import functools
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal, TypeVar

from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.invariant import INVARIANT, Invariant
from sapguimcp.lang.it import IT
from sapguimcp.lang.schema import CorePack, LanguagePack, UniversalView, merge, sections
from sapguimcp.lang.text import HasAlt, RegexText, Template, Text, alt_of
from sapguimcp.session_language import current_language, normalize_language, set_session_language, use_language

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "INVARIANT",
    "CorePack",
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
    "language_support",
    "logon_languages",
    "pack_for",
    "set_session_language",
    "supported_languages",
    "universal",
    "use",
    "view_for",
]

FALLBACK_LANGUAGE = "EN"

P = TypeVar("P", LanguagePack, CorePack)

_PACKS: dict[str, LanguagePack] = {pack.code: pack for pack in (DE, EN, IT)}
"""Registered packs in registration order (the order of :func:`supported_languages`)."""

_CORE_PACKS: dict[str, CorePack] = {}
"""Registered core packs (#1081): languages that have only the ``universal()`` sections. None ships yet."""

_views: dict[str, LanguagePack] = {}
"""Merged session views by language code. Packs hold mappings and are not hashable."""


class UnsupportedLanguageError(RuntimeError):
    """The session's logon language has no full language pack (it may have a core pack)."""

    def __init__(self, language: str | None, feature: str) -> None:
        self.language = language
        self.supported = supported_languages()
        supported = ", ".join(self.supported)
        if language is None:
            message = (
                f"{feature} needs the session's logon language, but none is known; "
                f"log in first (supported: {supported})"
            )
        elif language in _CORE_PACKS:
            message = (
                f"{feature} needs a full language pack for {language}, which has only a core pack "
                f"(login and the language-independent tools work); full packs: {supported}"
            )
        else:
            message = f"{feature} needs a language pack for {language}; supported: {supported}"
        super().__init__(message)


def supported_languages() -> tuple[str, ...]:
    """SAP language keys that have a pack, in registration order (``("DE", "EN", "IT")``)."""
    return tuple(_PACKS)


def logon_languages() -> tuple[str, ...]:
    """SAP language keys a user may log on in: the full packs, then the core packs (#1081)."""
    return (*_PACKS, *_CORE_PACKS)


def language_support(code: str | None) -> Literal["full", "core", "none"]:
    """How far the server supports a logon language: a full pack, a core pack only, or nothing."""
    normalized = normalize_language(code)
    if normalized in _PACKS:
        return "full"
    if normalized in _CORE_PACKS:
        return "core"
    return "none"


def pack_for(code: str) -> LanguagePack:
    """The registered (unmerged) pack for ``code``; :class:`UnsupportedLanguageError` if none."""
    normalized = normalize_language(code)
    pack = _PACKS.get(normalized) if normalized is not None else None
    if pack is None:
        raise UnsupportedLanguageError(normalized or repr(code), "this lookup")
    return pack


def _build_view(code: str) -> LanguagePack:
    """Merge each section per its ``MERGE`` mode; scalar pack fields come from the session pack."""
    session = _PACKS[code]
    # Full packs only: core packs are not merged in here, so read the ``all`` sections through universal().
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
    """The ``all`` sections merged over every registered full and core pack, in registration order."""
    packs: list[LanguagePack | CorePack] = [*_PACKS.values(), *_CORE_PACKS.values()]
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


def _clear_caches() -> None:
    """Forget every merged view; the next :func:`view_for` / :func:`universal` call rebuilds it."""
    _views.clear()
    universal.cache_clear()


@contextmanager
def _register_for_tests(pack: P) -> Iterator[P]:
    """Register ``pack`` (full or core) for the duration of a ``with`` block. Tests only (#1044, #1081).

    Clears the merged-view caches on enter and on exit, so :func:`view_for`, :func:`current`,
    :func:`universal`, :func:`supported_languages` and :func:`logon_languages` see the pack inside
    the block and forget it afterwards. Refuses a code that is already registered (replacing DE or
    EN would change what other tests see) and a code that is not a normalized SAP language key.
    """
    if normalize_language(pack.code) != pack.code:
        raise ValueError(f"pack code must be an upper-case SAP language key, got {pack.code!r}")
    if pack.code in _PACKS or pack.code in _CORE_PACKS:
        raise ValueError(f"a pack for {pack.code} is already registered")
    if isinstance(pack, LanguagePack):
        _PACKS[pack.code] = pack
    else:
        _CORE_PACKS[pack.code] = pack
    _clear_caches()
    try:
        yield pack
    finally:
        _PACKS.pop(pack.code, None)
        _CORE_PACKS.pop(pack.code, None)
        _clear_caches()
