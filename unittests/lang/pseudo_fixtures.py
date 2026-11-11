"""Pseudo-locale fixture rewriting for the parser harness (#1044, spec section 10).

The idea: rewrite a captured DE or EN fixture so that every text the language pack knows shows up
in a spelling no real language has, run the parser on the original under its own language and on
the rewritten fixture under a pseudo pack, and compare. A parser that still carries a DE or EN
spelling of its own (instead of a pack field) finds nothing in the rewritten fixture and differs.

How the rewriting works
-----------------------

The pseudo language is a **letter-wise transliteration**: ``Methoden`` becomes ``Ɱēŧħōđēņ``. Every
ASCII letter and ``ä ö ü ß`` has one pseudo letter with a simple upper/lower pair, and nothing
else changes (digits, punctuation, whitespace, placeholders, regex syntax).

- The pseudo pack is the session view of the source language (``lang.view_for``), with every
  ``Text`` variant, every literal part of a ``Template`` and every literal of a ``RegexText``
  transliterated: same field, same index, same ``fold`` / ``word`` flags.
- In a fixture, every occurrence of every pack variant is transliterated in place, honouring the
  field's flags (case-insensitive for ``fold``, word boundaries for ``word``). Everything the pack
  does not know stays as it is - it is data.

A transliteration rather than the opaque ``⟦section.field#n⟧`` markers of
``test_pseudo_locale.py``, for four reasons the markers cannot meet on real fixtures:

1. Two fields may hold the same text (``Name`` is a column title in several sections). A fixture
   occurrence cannot be assigned to one field's marker, but it has exactly one transliteration.
2. A variant may be part of a longer one (``Job`` / ``Jobname``). Transliteration is compositional,
   so ``contains`` keeps working on both.
3. Case and word boundaries survive, so ``fold=False`` and ``word=True`` fields behave as before.
4. It is reversible (:func:`restore`), so parser output that echoes UI text (column titles,
   descriptions) can be compared exactly instead of field by field.

The EN merge is disabled as the spec asks: the pseudo pack is registered and used *unmerged*
(:func:`pseudo_session` seeds the view cache with the pack itself), so nothing falls back to a
real EN or DE spelling. It is built from the *merged* view of the source language instead, so a
text that a German screen shows in English (the documented fallback) is rewritten as well.

What is not rewritten (documented limits)
-----------------------------------------

- ARIA role keywords (``- text:``, ``- button``) and state attributes (``[selected]``,
  ``[level=1]``): they are structure, not text, and ``text`` / ``tab`` / ``row`` are pack texts.
- An occurrence that covers a technical name only in part (an all-uppercase token such as
  ``CL_SALV_TABLE`` or ``SAPLSE16N``; ``DATA`` in ``ET_DATA``): the name is data, and parsers read
  such names with ``[A-Z0-9_/]+``. A pack text that *is* the whole token (``OK``, or ``PRIVATE``
  in a change-mode grid) is rewritten.
- The ABAP typing keywords ``TYPE`` and ``LIKE`` in upper case: source code, not the column title.
- In HTML only text nodes and the values of ``title`` / ``aria-label`` / ``alt`` / ``placeholder``
  / ``value`` attributes; ids, classes, ``lsdata`` and scripts stay (spec: "blind replacement of
  short variants would corrupt ids and lsdata").
"""

from __future__ import annotations

import dataclasses
import html
import json
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from html.parser import HTMLParser
from typing import Any
from unittest.mock import patch

from sapguimcp import lang
from sapguimcp.lang import _register_for_tests
from sapguimcp.lang.schema import LanguagePack, Leaf, UniversalView, canonical, iter_leaves, sections
from sapguimcp.lang.text import RegexText, Template, Text

CODE = "PS"

# =============================================================================
# The pseudo alphabet
# =============================================================================

_LOWER = "abcdefghijklmnopqrstuvwxyzäöüß"
_PSEUDO_LOWER = "āƀċđēƒġħīĵķļɱņōƥɋŗŝŧūʋŵẋŷżǟȫǖƨ"
_PSEUDO_UPPER = "ĀɃĊĐĒƑĠĦĪĴĶĻⱮŅŌƤɊŖŜŦŪƲŴẊŶŻǞȪǕƧ"
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ"  # no upper-case ß in SAP texts

_TO_PSEUDO = str.maketrans(_LOWER + _UPPER, _PSEUDO_LOWER + _PSEUDO_UPPER[: len(_UPPER)])
_FROM_PSEUDO = str.maketrans(_PSEUDO_LOWER + _PSEUDO_UPPER[: len(_UPPER)], _LOWER + _UPPER)
PSEUDO_LETTERS = frozenset(_PSEUDO_LOWER + _PSEUDO_UPPER)


def check_alphabet() -> None:
    """Every pseudo letter is a single letter with a simple case pair, and no source letter."""
    assert len(_LOWER) == len(_PSEUDO_LOWER) == len(_PSEUDO_UPPER) == len(set(_PSEUDO_LOWER + _PSEUDO_UPPER)) // 2
    assert not PSEUDO_LETTERS & set(_LOWER + _UPPER)
    for low, up in zip(_PSEUDO_LOWER, _PSEUDO_UPPER, strict=True):
        assert low.isalpha(), low
        assert up.isalpha(), up
        assert (low.upper(), up.lower(), low.lower(), up.upper()) == (up, low, low, up), (low, up)
        assert re.fullmatch(low, up, re.IGNORECASE), (low, up)
        assert re.fullmatch(r"\w", low)
        assert re.fullmatch(r"\w", up)


def to_pseudo(text: str) -> str:
    """Transliterate every letter of ``text``."""
    return text.translate(_TO_PSEUDO)


def restore(value: Any) -> Any:
    """Undo the transliteration in every string of a JSON-like value (parser output)."""
    if isinstance(value, str):
        return value.translate(_FROM_PSEUDO)
    if isinstance(value, Mapping):
        return {restore(key): restore(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [restore(item) for item in value]
    return value


# =============================================================================
# The pseudo pack
# =============================================================================

_PLACEHOLDER = re.compile(r"\{[A-Za-z_]\w*\}")
_REGEX_SYNTAX = re.compile(
    r"\\.|\[(?:\\.|[^\]\\])*\]|\(\?(?:[:=!]|<[=!])|\{\d+(?:,\d*)?\}",
    re.DOTALL,
)
"""Parts of a pack regex that are syntax, not text: escapes, character classes, group openers, counts."""


def _outside(pattern: re.Pattern[str], text: str, change: Callable[[str], str]) -> str:
    """Apply ``change`` to the parts of ``text`` that ``pattern`` does not match."""
    parts: list[str] = []
    position = 0
    for match in pattern.finditer(text):
        parts.append(change(text[position : match.start()]))
        parts.append(match.group())
        position = match.end()
    parts.append(change(text[position:]))
    return "".join(parts)


def pseudo_regex(pattern: str) -> str:
    """Transliterate the literal letters of a pack regex, keeping its syntax."""
    for syntax in _REGEX_SYNTAX.findall(pattern):
        if syntax.startswith("[") and re.search(r"[A-Za-zäöüÄÖÜß]", re.sub(r"\\.", "", syntax)):
            # a letter class such as [a-z] would need its own translation; no pack has one today
            raise NotImplementedError(f"character class with letters in a pack regex: {pattern!r}")
    return _outside(_REGEX_SYNTAX, pattern, to_pseudo)


def pseudo_leaf(leaf: Leaf) -> Leaf:
    """The same leaf (kind, flags, variant count and order) in the pseudo language."""
    if isinstance(leaf, Text):
        return Text(tuple(to_pseudo(variant) for variant in leaf.variants), fold=leaf.fold, word=leaf.word)
    if isinstance(leaf, RegexText):
        return RegexText(tuple(pseudo_regex(pattern) for pattern in leaf.patterns), fold=leaf.fold)
    return Template(tuple(_outside(_PLACEHOLDER, variant, to_pseudo) for variant in leaf.variants), fold=leaf.fold)


def _pseudo_section(section: Any) -> Any:
    values: dict[str, object] = {}
    for field in dataclasses.fields(section):
        value = getattr(section, field.name)
        if isinstance(value, Mapping):
            values[field.name] = canonical({key: pseudo_leaf(leaf) for key, leaf in value.items()})
        else:
            values[field.name] = pseudo_leaf(value)
    return type(section)(**values)


# =============================================================================
# Finding pack texts in a fixture
# =============================================================================

_TECHNICAL_NAME = re.compile(r"(?<![\w/])[A-Z0-9_/]*[A-Z][A-Z0-9_/]*(?![\w/])")
"""An all-uppercase token (``CL_SALV_TABLE``, ``SAPLSE16N/0200``, ``OK``)."""


def _word_char(text: str, index: int) -> bool:
    return 0 <= index < len(text) and (text[index].isalnum() or text[index] == "_")


def _lower_same_length(text: str) -> str:
    lowered = text.lower()
    if len(lowered) == len(text):
        return lowered
    return "".join(char.lower() if len(char.lower()) == 1 else char for char in text)


@dataclass(frozen=True)
class Matcher:
    """Finds every occurrence of the texts of one language view in a string."""

    literals: tuple[tuple[str, bool, bool], ...]
    """``(variant, fold, word)``, the variant lower-cased when it folds."""
    regexes: tuple[re.Pattern[str], ...]
    """``RegexText`` patterns; a whole match is pack text."""
    templates: tuple[re.Pattern[str], ...]
    """``Template`` variants; the literal parts (groups named ``lit<n>``) are pack text."""

    def spans(self, text: str) -> set[tuple[int, int]]:
        """Every span of ``text`` that is pack text; spans may overlap."""
        found: set[tuple[int, int]] = set()
        lowered = _lower_same_length(text)
        for variant, fold, word in self.literals:
            haystack = lowered if fold else text
            start = haystack.find(variant)
            while start != -1:
                end = start + len(variant)
                if not word or not (_word_char(text, start - 1) or _word_char(text, end)):
                    found.add((start, end))
                start = haystack.find(variant, start + 1)
        for pattern in self.regexes:
            found.update(match.span() for match in pattern.finditer(text))
        for pattern in self.templates:
            for match in pattern.finditer(text):
                found.update(match.span(name) for name in pattern.groupindex if name.startswith("lit"))
        return found


def _template_pattern(variant: str, fold: bool) -> re.Pattern[str]:
    """One template variant; placeholders stay inside one quoted string or line."""
    parts: list[str] = []
    position = 0
    count = 0
    for match in _PLACEHOLDER.finditer(variant):
        literal = variant[position : match.start()]
        if literal:
            parts.append(f"(?P<lit{count}>" + r"\s+".join(re.escape(p) for p in re.split(r"\s+", literal)) + ")")
            count += 1
        parts.append(r'[^"\n<>]+' if match.end() == len(variant) else r'[^"\n<>]+?')
        position = match.end()
    if variant[position:]:
        literal = variant[position:]
        parts.append(f"(?P<lit{count}>" + r"\s+".join(re.escape(p) for p in re.split(r"\s+", literal)) + ")")
    return re.compile("".join(parts), re.IGNORECASE if fold else 0)


def _matcher(view: LanguagePack, universal: UniversalView) -> Matcher:
    """The matcher for a session view plus the universal view."""
    leaves = [leaf for _, leaf in iter_leaves(view)] + [leaf for _, leaf in iter_leaves(universal)]
    literals: set[tuple[str, bool, bool]] = set()
    regexes: dict[tuple[str, bool], re.Pattern[str]] = {}
    templates: dict[tuple[str, bool], re.Pattern[str]] = {}
    for leaf in leaves:
        if isinstance(leaf, Text):
            literals.update((variant.lower() if leaf.fold else variant, leaf.fold, leaf.word) for variant in leaf)
        elif isinstance(leaf, RegexText):
            for pattern in leaf.patterns:
                # one line at a time: [\s\S]* in a pattern must not run across the whole fixture
                regexes[(pattern, leaf.fold)] = re.compile(
                    pattern.replace(r"[\s\S]", r"[^\n]"), re.IGNORECASE if leaf.fold else 0
                )
        else:
            for variant in leaf.variants:
                templates[(variant, leaf.fold)] = _template_pattern(variant, leaf.fold)
    return Matcher(
        literals=tuple(sorted(literals)),
        regexes=tuple(regexes.values()),
        templates=tuple(templates.values()),
    )


@dataclass(frozen=True)
class PseudoLocale:
    """The pseudo counterpart of one source language."""

    source: str
    """The real language the pseudo pack is derived from (``DE`` or ``EN``)."""
    view: LanguagePack
    """The merged session view of the source language - what a parser gets for the original fixture."""
    pack: LanguagePack
    """The pseudo pack: ``view`` transliterated, used unmerged."""
    universal: UniversalView
    """``lang.universal()`` transliterated (same variant order)."""
    matcher: Matcher
    """Finds the texts of ``view`` and of the real universal view in a fixture."""


@cache
def pseudo_locale(source: str) -> PseudoLocale:
    """Build the pseudo pack for ``source``. Call it outside :func:`pseudo_session`."""
    view = lang.view_for(source)
    replaced = {name: _pseudo_section(section) for name, section in sections(view)}
    pack = dataclasses.replace(
        view, code=CODE, html_lang="ps", logon_dropdown="Pseudo", same_as_en=frozenset(), **replaced
    )
    real_universal = lang.universal()
    universal = UniversalView(
        **{
            field.name: _pseudo_section(getattr(real_universal, field.name))
            for field in dataclasses.fields(UniversalView)
        }
    )
    return PseudoLocale(
        source=source, view=view, pack=pack, universal=universal, matcher=_matcher(view, real_universal)
    )


@contextmanager
def pseudo_session(source: str) -> Iterator[PseudoLocale]:
    """A session in the pseudo language of ``source``, with every merge disabled.

    ``lang.current()`` returns the pseudo pack itself (no EN fallback) and ``lang.universal()``
    only the pseudo texts, so code that reads the registry instead of taking ``t`` cannot fall
    back to a real spelling either.
    """
    locale = pseudo_locale(source)
    with _register_for_tests(locale.pack):
        lang._views[CODE] = locale.pack  # pylint: disable=protected-access  # the unmerged pack is the view
        with patch.object(lang, "universal", lambda: locale.universal), lang.use(CODE):
            yield locale


# =============================================================================
# Rewriting fixtures
# =============================================================================


@dataclass
class Rewrite:
    """A rewritten fixture and what happened to it."""

    text: str
    replaced: int = 0
    """Number of pack-text occurrences that were transliterated."""
    kept_as_data: int = 0
    """Occurrences left alone because they are data (part of a technical name, an ABAP keyword)."""


_ABAP_KEYWORDS = frozenset({"TYPE", "LIKE"})
"""Upper-case words of ABAP typing (``ET_DATA TYPE SDTI_RESULT_TAB``). They are source code, the
same in every logon language, although the column title ``Type`` matches them case-insensitively."""


def _cuts_a_name(start: int, end: int, name_at: Mapping[int, tuple[int, int]]) -> bool:
    """``True`` if the span covers a technical name only in part (``DATA`` in ``ET_DATA``)."""
    for index in (start, end - 1):
        name = name_at.get(index)
        if name is not None and not (start <= name[0] and name[1] <= end):
            return True
    return False


def _rewrite_text(text: str, source: str, protected: list[tuple[int, int]] | None = None) -> Rewrite:
    """Transliterate every pack-text occurrence in ``text`` outside the ``protected`` spans."""
    locked = bytearray(len(text))
    for start, end in protected or ():
        locked[start:end] = b"\x01" * (end - start)
    names = [match.span() for match in _TECHNICAL_NAME.finditer(text) if match.end() - match.start() > 1]
    name_at: dict[int, tuple[int, int]] = {}
    for span in names:
        for index in range(*span):
            name_at[index] = span
    mask = bytearray(len(text))
    result = Rewrite(text)
    for start, end in pseudo_locale(source).matcher.spans(text):
        if any(locked[start:end]):
            continue
        if _cuts_a_name(start, end, name_at) or text[start:end] in _ABAP_KEYWORDS:
            result.kept_as_data += 1
            continue
        result.replaced += 1
        mask[start:end] = b"\x01" * (end - start)
    result.text = "".join(to_pseudo(char) if flag else char for char, flag in zip(text, mask, strict=True))
    return result


_ARIA_STRUCTURE = re.compile(
    r"^\s*-\s+'?/?[a-z]+"  # the role keyword (or a /url property) that opens a line
    r"|\[(?:ref|level|selected|checked|disabled|expanded|pressed|active|cursor|nth)(?:=[^\]\n]*)?\]",
    re.MULTILINE,
)


def rewrite_aria(snapshot: str, source: str) -> Rewrite:
    """Rewrite an ARIA snapshot: everything but role keywords and state attributes is text."""
    return _rewrite_text(snapshot, source, [match.span() for match in _ARIA_STRUCTURE.finditer(snapshot)])


def rewrite_plain(text: str, source: str) -> Rewrite:
    """Rewrite plain text (status-bar messages, desktop screen text, list output)."""
    return _rewrite_text(text, source)


_HTML_TEXT_ATTRIBUTES = frozenset({"title", "aria-label", "alt", "placeholder", "value"})
_HTML_ATTRIBUTE = re.compile(r"""\s+(?P<name>[^\s=/>"']+)(?:\s*=\s*(?P<value>"[^"]*"|'[^']*'|[^\s>]+))?""")
_HTML_RAW_TEXT = frozenset({"script", "style"})
_HTML_REFERENCE = re.compile(r"(&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)")


class _HtmlRewriter(HTMLParser):
    """Rebuilds an HTML document piece by piece, passing text runs and text attributes to ``change``.

    With an identity ``change`` the output equals the input, character for character.
    """

    def __init__(self, change: Callable[[str], str]) -> None:
        super().__init__(convert_charrefs=False)
        self._change = change
        self._parts: list[str] = []
        self._run: list[str] = []
        self._raw_text = False

    def rewrite(self, document: str) -> str:
        self.feed(document)
        self.close()
        self._flush()
        return "".join(self._parts)

    def _flush(self) -> None:
        if self._run:
            raw = "".join(self._run)
            self._run.clear()
            self._parts.append(raw if not raw.strip() else self._text(raw))

    def _text(self, raw: str) -> str:
        """Change the text of ``raw`` markup, leaving its character references as they are.

        The text is decoded for ``change`` (so ``Men&uuml; &amp; mehr`` is seen as shown on the
        screen) and the changed letters are written back over the raw pieces. ``change`` keeps the
        length, so every piece finds its place again; a reference that decodes to a changed letter
        is replaced by that letter.
        """
        pieces = [piece for piece in _HTML_REFERENCE.split(raw) if piece]
        decoded = [html.unescape(piece) if _HTML_REFERENCE.fullmatch(piece) else piece for piece in pieces]
        before = "".join(decoded)
        after = self._change(before)
        if after == before:
            return raw
        assert len(after) == len(before), "the text change must keep the length"
        out: list[str] = []
        position = 0
        for piece, text in zip(pieces, decoded, strict=True):
            changed = after[position : position + len(text)]
            position += len(text)
            out.append(piece if changed == text else changed)
        return "".join(out)

    def _attribute(self, match: re.Match[str]) -> str:
        value = match.group("value")
        if value is None or match.group("name").lower() not in _HTML_TEXT_ATTRIBUTES or value[0] not in "\"'":
            return match.group()
        return match.group()[: match.start("value") - match.start()] + value[0] + self._text(value[1:-1]) + value[0]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        self._flush()
        raw = self.get_starttag_text() or ""
        name = re.match(r"<[^\s/>]+", raw)
        head = name.group() if name else ""
        self._parts.append(head + _HTML_ATTRIBUTE.sub(self._attribute, raw[len(head) :]))
        self._raw_text = tag in _HTML_RAW_TEXT

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self._raw_text = False

    def handle_endtag(self, tag: str) -> None:
        self._flush()
        self._parts.append(f"</{tag}>")
        self._raw_text = False

    def handle_data(self, data: str) -> None:
        if self._raw_text:
            self._flush()
            self._parts.append(data)
        else:
            self._run.append(data)

    def handle_entityref(self, name: str) -> None:
        self._run.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._run.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._flush()
        self._parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._flush()
        self._parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._flush()
        self._parts.append(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self._flush()
        self._parts.append(f"<![{data}]>")


def rebuild_html(document: str, change: Callable[[str], str]) -> str:
    """``document`` with ``change`` applied to its text runs and text attributes."""
    return _HtmlRewriter(change).rewrite(document)


def rewrite_html(document: str, source: str) -> Rewrite:
    """Rewrite an HTML snapshot: text nodes and the text attributes of tags only.

    Character references are decoded for matching, so ``&Auml;ndern`` is found like plain text.
    Scripts, styles, ids, classes and ``lsdata`` stay as they are.
    """
    total = Rewrite("")

    def change(text: str) -> str:
        piece = _rewrite_text(text, source)
        total.replaced += piece.replaced
        total.kept_as_data += piece.kept_as_data
        return piece.text

    total.text = rebuild_html(document, change)
    return total


def unwrap_envelope(content: str, key: str = "snapshot") -> str:
    """The ARIA snapshot (or ``html``) of a fixture, which some captures wrap in a JSON tool result."""
    if content.lstrip().startswith("{"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return content
        if isinstance(data, dict) and isinstance(data.get(key), str):
            return str(data[key])
    return content
