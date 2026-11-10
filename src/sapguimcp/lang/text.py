"""The three value types of a language pack: ``Text``, ``RegexText`` and ``Template`` (#1044).

They are siblings, not subclasses, so mypy rejects clicking a regex or filling a template.
All three are frozen and slotted. Slotted dataclasses have no ``__dict__``, so derived regex
sources and compiled patterns come from module-level ``functools.cache`` builders keyed by the
value's fields.

Python only. The JavaScript builder (``for_js()``) arrives with the JS object-argument
convention in phase 2c.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

T = TypeVar("T")

_PLACEHOLDER = re.compile(r"\{([A-Za-z_]\w*)\}")
_DEFAULT_GROUP = r".+?"
_TRAILING_GROUP = r".+"
"""A placeholder that ends a variant captures the whole rest of the line, not a lazy fragment."""


class HasAlt(Protocol):
    """Anything that renders as a regex alternation group to embed into a larger regex.

    Static typing only (not ``runtime_checkable``): ``Template`` deliberately has no ``alt``, and
    mypy is what keeps it out of ``alt_of``.
    """

    @property
    def alt(self) -> str:
        """The regex source, a self-contained group with its own case flag."""


def _require_strings(kind: str, values: object) -> tuple[str, ...]:
    """Validate a variants/patterns tuple: a non-empty tuple of non-empty strings."""
    if not isinstance(values, tuple):
        # Text("Anzeigen") would otherwise iterate the characters of the string.
        raise TypeError(f"{kind} must be a tuple of strings, got {type(values).__name__}")
    if not values:
        raise ValueError(f"{kind} must not be empty")
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{kind} must hold non-empty strings, got {value!r}")
    return values


def _fold_key(value: str, fold: bool) -> str:
    return value.lower() if fold else value


def _unique(values: tuple[str, ...], fold: bool) -> tuple[str, ...]:
    """Drop duplicates (case-insensitively when folding), keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = _fold_key(value, fold)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return tuple(unique)


def _scoped(body: str, fold: bool) -> str:
    """Wrap ``body`` in a group that carries its own case flag."""
    return f"(?i:{body})" if fold else f"(?:{body})"


@cache
def literal_alt(variants: tuple[str, ...], fold: bool, word: bool) -> str:
    """Escaped alternation of literal variants, de-duplicated and longest first.

    Longest first, because a short variant would otherwise shadow a longer one
    (``Programm|Programmname`` captures ``name ZFOO``). ``sorted`` is stable, so variants of equal
    length keep their declared order. Word boundaries are ``(?<!\\w)…(?!\\w)`` rather than ``\\b``,
    so variants that start or end with punctuation (``Ext. Identif.``) still match.
    """
    ordered = sorted(_unique(variants, fold), key=len, reverse=True)
    body = "|".join(re.escape(variant) for variant in ordered)
    if word:
        body = rf"(?<!\w)(?:{body})(?!\w)"
    return _scoped(body, fold)


@cache
def regex_alt(patterns: tuple[str, ...], fold: bool) -> str:
    """Alternation of raw regex patterns, each isolated in its own group, in declared order."""
    body = "|".join(f"(?:{pattern})" for pattern in _unique(patterns, fold=False))
    return _scoped(body, fold)


@cache
def compiled(source: str) -> re.Pattern[str]:
    """Compile and cache a regex source."""
    return re.compile(source)


def _literal_source(literal: str, fold: bool) -> str:
    """Scoped regex for one literal part of a template; whitespace runs match any whitespace."""
    if not literal:
        return ""
    body = r"\s+".join(re.escape(piece) for piece in re.split(r"\s+", literal))
    return _scoped(body, fold)


@cache
def template_patterns(
    variants: tuple[str, ...], fold: bool, groups: tuple[tuple[str, str], ...]
) -> tuple[re.Pattern[str], ...]:
    """One compiled pattern per template variant (Python rejects duplicate group names).

    ``groups`` maps placeholder names to the regex source of their capture group; placeholders
    without an entry capture ``.+?`` (``.+`` at the very end of a variant). Each literal part is
    scoped on its own with the case flag, so the capture groups stay outside the fold.
    """
    sources = dict(groups)
    patterns: list[re.Pattern[str]] = []
    for variant in variants:
        parts: list[str] = []
        position = 0
        for match in _PLACEHOLDER.finditer(variant):
            parts.append(_literal_source(variant[position : match.start()], fold))
            name = match.group(1)
            default = _TRAILING_GROUP if match.end() == len(variant) else _DEFAULT_GROUP
            parts.append(f"(?P<{name}>{sources.get(name, default)})")
            position = match.end()
        parts.append(_literal_source(variant[position:], fold))
        patterns.append(re.compile("".join(parts)))
    return tuple(patterns)


def placeholder_names(variant: str) -> tuple[str, ...]:
    """Placeholder names of one template variant, in order of appearance."""
    return tuple(match.group(1) for match in _PLACEHOLDER.finditer(variant))


@dataclass(frozen=True, slots=True)
class Text:
    """Literal text with one or more variants; the common case.

    Variants cover every spelling SAP shows for one text: SAP release differences (ECC vs
    S/4HANA) and truncations. A merged view appends the variants of the fallback languages.
    """

    variants: tuple[str, ...]
    fold: bool = True
    """Case-insensitive matching (``lower()`` on both sides, the same folding as ``IGNORECASE``)."""
    word: bool = False
    """Require word boundaries around the variant (``Line``, ``Alt``, ``ja``)."""

    def __post_init__(self) -> None:
        _require_strings("Text variants", self.variants)

    def __iter__(self) -> Iterator[str]:
        """Candidates for clicking, filling or tab selection, in declared order."""
        return iter(self.variants)

    def contains(self, s: str) -> bool:
        """``True`` if any variant occurs in ``s``."""
        if self.word:
            return self.pattern.search(s) is not None
        haystack = _fold_key(s, self.fold)
        return any(_fold_key(variant, self.fold) in haystack for variant in self.variants)

    def equals(self, s: str) -> bool:
        """``True`` if ``s`` equals one of the variants (no stripping)."""
        needle = _fold_key(s, self.fold)
        return any(_fold_key(variant, self.fold) == needle for variant in self.variants)

    def first_key(self, row: Mapping[str, T]) -> T | None:
        """Value of the first variant that is a key of ``row`` (column header lookup)."""
        for variant in self.variants:
            if variant in row:
                return row[variant]
        if self.fold:
            folded: dict[str, str] = {}
            for key in row:
                folded.setdefault(key.lower(), key)
            for variant in self.variants:
                original = folded.get(variant.lower())
                if original is not None:
                    return row[original]
        return None

    @property
    def alt(self) -> str:
        """Escaped alternation for embedding, e.g. ``(?i:Number\\ of\\ Hits|Anzahl\\ Treffer)``."""
        return literal_alt(self.variants, self.fold, self.word)

    @property
    def pattern(self) -> re.Pattern[str]:
        """Compiled :attr:`alt`."""
        return compiled(self.alt)


@dataclass(frozen=True, slots=True)
class RegexText:
    """Irregular text that needs a regex; raw pattern strings. No iteration, no clicking.

    No named groups: several patterns are alternated into one regex, where a repeated group name
    is an error. Text with captures belongs in :class:`Template`.
    """

    patterns: tuple[str, ...]
    fold: bool = True

    def __post_init__(self) -> None:
        for pattern in _require_strings("RegexText patterns", self.patterns):
            if re.compile(pattern).groupindex:  # fail at import, not at first use
                raise ValueError(f"named groups belong in Template, not RegexText: {pattern!r}")

    @property
    def alt(self) -> str:
        """Alternation of all patterns, each in its own group, with the case flag scoped."""
        return regex_alt(self.patterns, self.fold)

    @property
    def pattern(self) -> re.Pattern[str]:
        """Compiled :attr:`alt`."""
        return compiled(self.alt)


@dataclass(frozen=True, slots=True)
class Template:
    """Text with placeholders whose word order depends on the language.

    ``Template(("{name} anzeigen",))`` and ``Template(("Display {name}",))``: every variant has the
    same placeholders, so callers read ``m["name"]`` regardless of language.
    """

    variants: tuple[str, ...]
    fold: bool = True

    def __post_init__(self) -> None:
        names = {placeholder_names(variant) for variant in _require_strings("Template variants", self.variants)}
        for found in names:
            if len(set(found)) != len(found):
                raise ValueError(f"Template placeholder used twice in one variant: {self.variants!r}")
        if len({frozenset(found) for found in names}) != 1:
            raise ValueError(f"Template variants differ in their placeholders: {self.variants!r}")

    @property
    def placeholders(self) -> frozenset[str]:
        """The placeholder names, identical for every variant."""
        return frozenset(placeholder_names(self.variants[0]))

    def _patterns(self, groups: Mapping[str, str | HasAlt]) -> tuple[re.Pattern[str], ...]:
        unknown = set(groups) - self.placeholders
        if unknown:
            raise KeyError(f"unknown template placeholders: {sorted(unknown)}")
        sources = tuple(
            sorted((name, value if isinstance(value, str) else value.alt) for name, value in groups.items())
        )
        return template_patterns(self.variants, self.fold, sources)

    def search(self, s: str, **groups: str | HasAlt) -> re.Match[str] | None:
        """First variant found anywhere in ``s``; a ``str`` group value is a raw regex."""
        for pattern in self._patterns(groups):
            match = pattern.search(s)
            if match is not None:
                return match
        return None

    def match(self, s: str, **groups: str | HasAlt) -> re.Match[str] | None:
        """First variant matching at the start of ``s``."""
        for pattern in self._patterns(groups):
            match = pattern.match(s)
            if match is not None:
                return match
        return None

    def format(self, **values: str) -> str:
        """The first variant with its placeholders filled in."""
        missing = self.placeholders - set(values)
        if missing:
            raise KeyError(f"missing template values: {sorted(missing)}")
        return _PLACEHOLDER.sub(lambda match: values[match.group(1)], self.variants[0])


def alt_of(*texts: HasAlt) -> str:
    """Join several texts into one alternation group, e.g. ``Class|Klasse|Interface``."""
    if not texts:
        raise ValueError("alt_of needs at least one text")
    return "(?:" + "|".join(text.alt for text in texts) + ")"
