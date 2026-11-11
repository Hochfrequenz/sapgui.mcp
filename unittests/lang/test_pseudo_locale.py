"""Pseudo-locale round trip (#1044, spec section 10).

A pseudo pack replaces every text variant of EN with a unique marker ``⟦section.field[key]#n⟧`` that
no real DE/EN spelling resembles. Every field must then round-trip through the helper that code
uses to match, click, search or ship it to JavaScript (``contains`` / ``equals`` / ``alt`` /
``pattern`` / ``for_js`` / ``format``), and the session view of the pseudo language must hold only
markers plus the EN fallback.

Scope note: the spec also describes rewriting the parser fixtures and running the parsers against
a pseudo pack. That harness lives in ``test_pseudo_locale_parsers.py`` (ARIA parsers) and
``test_pseudo_locale_scripts.py`` (page scripts), on top of ``pseudo_fixtures.py``; this unit test
covers the pack and helper side only.
"""

import dataclasses
import re
from collections.abc import Iterator, Mapping

import pytest

from sapguimcp import lang
from sapguimcp.lang import _register_for_tests
from sapguimcp.lang.schema import LanguagePack, Leaf, canonical, iter_leaves, sections
from sapguimcp.lang.text import RegexText, Template, Text, compiled, placeholder_names

CODE = "PS"


def _marker(path: str, index: int) -> str:
    return f"⟦{path}#{index}⟧"


def _regex_marker(path: str, index: int) -> str:
    """A marker without regex metacharacters, so the pattern is its own literal and portable to JS."""
    return re.sub(r"[^\w⟦⟧]", "_", _marker(path, index))


def _pseudo_leaf(path: str, leaf: Leaf) -> Leaf:
    if isinstance(leaf, Text):
        return Text(tuple(_marker(path, i) for i, _ in enumerate(leaf.variants)), fold=leaf.fold, word=leaf.word)
    if isinstance(leaf, RegexText):
        return RegexText(tuple(_regex_marker(path, i) for i, _ in enumerate(leaf.patterns)), fold=leaf.fold)
    names = sorted(placeholder_names(leaf.variants[0]))
    tail = " ".join("{" + name + "}" for name in names)
    return Template(tuple(f"{_marker(path, i)} {tail}" for i, _ in enumerate(leaf.variants)), fold=leaf.fold)


def pseudo_pack() -> LanguagePack:
    """EN with every text replaced by its marker; nothing declared as the same as EN."""
    reference = lang.pack_for("EN")
    replaced: dict[str, object] = {}
    for section_name, section in sections(reference):
        values: dict[str, object] = {}
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            path = f"{section_name}.{field.name}"
            if isinstance(value, Mapping):
                values[field.name] = canonical(
                    {key: _pseudo_leaf(f"{path}[{key}]", leaf) for key, leaf in value.items()}
                )
            else:
                values[field.name] = _pseudo_leaf(path, value)
        replaced[section_name] = type(section)(**values)
    return dataclasses.replace(
        reference, code=CODE, html_lang="ps", logon_dropdown="Pseudo", same_as_en=frozenset(), **replaced
    )


PSEUDO = pseudo_pack()


@pytest.fixture
def ps() -> Iterator[LanguagePack]:
    with _register_for_tests(PSEUDO) as pack:
        yield pack


def _own_leaves() -> list[tuple[str, Leaf]]:
    return list(iter_leaves(PSEUDO))


def test_every_pack_field_is_covered() -> None:
    assert len(_own_leaves()) == len(list(iter_leaves(lang.pack_for("EN"))))
    assert len(_own_leaves()) > 100  # guards against an empty walk


@pytest.mark.usefixtures("ps")
@pytest.mark.parametrize("path", [path for path, _ in _own_leaves()])
def test_leaf_round_trips_through_its_helpers(path: str) -> None:
    own = dict(_own_leaves())[path]
    merged = dict(iter_leaves(lang.view_for(CODE)))[path]
    en = dict(iter_leaves(lang.pack_for("EN")))[path]
    assert merged.__class__ is own.__class__
    if isinstance(own, Text):
        assert isinstance(merged, Text)
        assert isinstance(en, Text)
        first = own.variants[0]
        # every marker survives the merge; the EN fallback is part of the view
        assert set(own.variants) <= set(merged.variants)
        assert set(en.variants) <= set(merged.variants)
        assert merged.equals(first)
        assert merged.contains(f"before {first} after")
        assert first in list(merged)  # clicking / filling candidates
        assert merged.pattern.search(f"before {first} after") is not None
        assert compiled(merged.alt).search(first) is not None
        assert merged.first_key({first: 1}) == 1
        js = merged.for_js()
        assert js["variants"][0] == first
        assert isinstance(js["source"], str)
    elif isinstance(own, RegexText):
        assert isinstance(merged, RegexText)
        assert merged.pattern.search(own.patterns[0]) is not None
        assert isinstance(merged.for_js()["source"], str)
    else:
        assert isinstance(own, Template)
        assert isinstance(merged, Template)
        values = {name: f"V{n}" for n, name in enumerate(sorted(own.placeholders))}
        text = merged.format(**values)
        assert text.startswith(_marker(path, 0))
        found = merged.search(text, **dict.fromkeys(values, r"V\d"))
        assert found is not None
        assert {name: found[name] for name in values} == values


@pytest.mark.usefixtures("ps")
def test_a_marker_never_matches_a_different_text() -> None:
    texts = [(path, leaf) for path, leaf in _own_leaves() if isinstance(leaf, Text)]
    markers = {path: _marker(path, 0) for path, _ in texts}
    for path, leaf in texts:
        others = [marker for other, marker in markers.items() if other != path]
        assert not any(leaf.equals(marker) for marker in others), path


@pytest.mark.usefixtures("ps")
def test_the_universal_view_holds_the_markers_of_every_text() -> None:
    universal = dict(iter_leaves(lang.universal()))
    for path, leaf in _own_leaves():
        if path not in universal:
            continue  # session-only sections are not part of the universal view
        candidate = universal[path]
        if isinstance(leaf, Text):
            assert isinstance(candidate, Text)
            assert candidate.equals(leaf.variants[0]), path


@pytest.mark.usefixtures("ps")
def test_session_view_has_no_de_spelling_left() -> None:
    universal_sections = {name for name, _ in sections(lang.universal())}
    de = {p: v for p, v in iter_leaves(lang.pack_for("DE")) if p.split(".")[0] not in universal_sections}
    en = dict(iter_leaves(lang.pack_for("EN")))
    with lang.use(CODE):
        view = dict(iter_leaves(lang.current()))
    for path, leaf in view.items():
        if not isinstance(leaf, Text) or not isinstance(de.get(path), Text) or not isinstance(en.get(path), Text):
            continue
        de_only = set(de[path].variants) - set(en[path].variants)
        assert not de_only & set(leaf.variants), path
