"""Completeness and translation guards over every registered language pack (#1044, spec section 10).

Phase 2a covers the checks that need no source scanner. The synthetic third language and the
no-literal scanner follow in phase 2b; that phase calls the ``_check_*`` helpers with its own pack.
"""

import dataclasses
import re
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Any

import pytest

from sapguimcp import lang
from sapguimcp.lang.de import DE
from sapguimcp.lang.schema import (
    DumpSection,
    JobStatus,
    Key,
    KeysSection,
    LanguagePack,
    Leaf,
    PackLike,
    PopupSection,
    TransportStatus,
    Visibility,
    canonical,
    iter_leaves,
    resolve,
    sections,
)
from sapguimcp.lang.text import RegexText, Template, Text

LANGUAGES = lang.supported_languages()
EN = lang.pack_for("EN")

# Every canonical mapping of the schema and the enum whose members it must cover.
CANONICAL: dict[str, type[StrEnum]] = {
    "keys.names": Key,
    "se09.status": TransportStatus,
    "se24.visibility": Visibility,
    "sm37.status": JobStatus,
    "st22.section": DumpSection,
}

ALL_SECTIONS = {"popup", "status_type", "session_pages", "keys"}


def _packs() -> list[LanguagePack]:
    return [lang.pack_for(code) for code in LANGUAGES]


def _mappings(pack: PackLike) -> dict[str, Mapping[StrEnum, Text]]:
    found: dict[str, Mapping[StrEnum, Text]] = {}
    for section_name, section in sections(pack):
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            if isinstance(value, Mapping):
                found[f"{section_name}.{field.name}"] = value
    return found


def _placeholders(leaf: Leaf) -> frozenset[str]:
    return leaf.placeholders if isinstance(leaf, Template) else frozenset()


# ---------------------------------------------------------------------------
# The guards. Each raises AssertionError (or KeyError for an unresolvable path).
# ---------------------------------------------------------------------------


def _check_scalars(pack: LanguagePack) -> None:
    assert pack.html_lang == pack.html_lang.lower()
    assert pack.logon_dropdown.strip()
    assert date(2026, 2, 22).strftime(pack.date_format)


def _check_leaves_are_texts(pack: PackLike) -> None:
    for path, leaf in iter_leaves(pack):
        assert isinstance(leaf, Text | RegexText | Template), path
        values = leaf.patterns if isinstance(leaf, RegexText) else leaf.variants
        assert values, path
        assert all(value.strip() for value in values), path


def _check_regexes_compile(pack: PackLike) -> None:
    for path, leaf in iter_leaves(pack):
        if isinstance(leaf, Template):
            leaf.search("")  # compiles one pattern per variant
        else:
            assert isinstance(leaf.pattern, re.Pattern), path


def _check_same_shape_as(pack: LanguagePack, reference: LanguagePack) -> None:
    """Same fields, same text kinds, same flags."""
    leaves = dict(iter_leaves(pack))
    expected = dict(iter_leaves(reference))
    assert leaves.keys() == expected.keys()
    for path, leaf in leaves.items():
        other = expected[path]
        assert type(leaf) is type(other), path
        assert leaf.fold == other.fold, path
        assert getattr(leaf, "word", False) == getattr(other, "word", False), path


def _check_same_placeholders(pack: LanguagePack, reference: LanguagePack) -> None:
    for path, leaf in iter_leaves(pack):
        assert _placeholders(leaf) == _placeholders(resolve(reference, path)), path


def _check_merge_modes(pack: LanguagePack) -> None:
    section_types = {name: type(section) for name, section in sections(pack)}
    for name, section_type in section_types.items():
        assert "MERGE" in vars(section_type), f"{name}: declare MERGE in the class body"
    assert {name for name, section_type in section_types.items() if section_type.MERGE == "all"} == ALL_SECTIONS
    assert {section_type.MERGE for section_type in section_types.values()} == {"all", "session_en"}


def _check_canonical_mappings(pack: PackLike) -> None:
    """Every canonical mapping is declared and covers every member of its enum."""
    mappings = _mappings(pack)
    expected = {path: members for path, members in CANONICAL.items() if path.split(".")[0] in dict(sections(pack))}
    assert mappings.keys() == expected.keys()
    for path, mapping in mappings.items():
        assert set(mapping) == set(CANONICAL[path]), path


def _check_no_collisions(view_name: str, mappings: dict[str, Mapping[StrEnum, Text]]) -> None:
    for path, mapping in mappings.items():
        owner: dict[str, StrEnum] = {}
        for member, text in mapping.items():
            for variant in text:
                key = variant.lower() if text.fold else variant
                assert owner.setdefault(key, member) == member, (
                    f"{view_name} {path}: {variant!r} maps to {owner[key]} and {member}"
                )


def _check_untranslated_declared(pack: LanguagePack, reference: LanguagePack) -> None:
    """A field equal to EN must be listed in ``same_as_en``, so a copied ``en.py`` fails."""
    equal = {path for path, leaf in iter_leaves(pack) if leaf == resolve(reference, path)}
    assert equal == pack.same_as_en


def _check_same_as_en_entries(pack: LanguagePack, reference: LanguagePack) -> None:
    """Stale entries fail: every entry names a field that exists and still equals EN."""
    for path in pack.same_as_en:
        assert resolve(pack, path) == resolve(reference, path), path


# ---------------------------------------------------------------------------
# The guards over every registered language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", LANGUAGES)
def test_pack_scalars(code: str) -> None:
    pack = lang.pack_for(code)
    assert pack.code == code
    _check_scalars(pack)


def test_html_lang_codes_are_unique() -> None:
    assert len({pack.html_lang for pack in _packs()}) == len(LANGUAGES)


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_leaf_is_a_text_value_with_variants(code: str) -> None:
    _check_leaves_are_texts(lang.pack_for(code))
    _check_leaves_are_texts(lang.view_for(code))


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_regex_compiles(code: str) -> None:
    _check_regexes_compile(lang.pack_for(code))
    _check_regexes_compile(lang.view_for(code))


def test_every_universal_regex_compiles() -> None:
    _check_regexes_compile(lang.universal())


@pytest.mark.parametrize("code", LANGUAGES)
def test_same_fields_kinds_and_flags_as_en(code: str) -> None:
    _check_same_shape_as(lang.pack_for(code), EN)


@pytest.mark.parametrize("code", LANGUAGES)
def test_same_placeholders_as_en(code: str) -> None:
    _check_same_placeholders(lang.pack_for(code), EN)


@pytest.mark.parametrize("code", LANGUAGES)
def test_merge_modes(code: str) -> None:
    _check_merge_modes(lang.pack_for(code))


def test_universal_holds_exactly_the_all_sections() -> None:
    assert {field.name for field in dataclasses.fields(lang.UniversalView)} == ALL_SECTIONS


@pytest.mark.parametrize("code", LANGUAGES)
def test_canonical_mappings_are_declared_and_cover_every_member(code: str) -> None:
    _check_canonical_mappings(lang.pack_for(code))
    _check_canonical_mappings(lang.view_for(code))


@pytest.mark.parametrize("code", LANGUAGES)
def test_no_variant_maps_to_two_members_in_a_session_view(code: str) -> None:
    with lang.use(code):
        _check_no_collisions(code, _mappings(lang.current()))


def test_no_variant_maps_to_two_members_in_the_universal_view() -> None:
    _check_no_collisions("universal", {"keys.names": lang.universal().keys.names})


def test_en_declares_nothing_as_same_as_en() -> None:
    assert EN.same_as_en == frozenset()


@pytest.mark.parametrize("code", [code for code in LANGUAGES if code != "EN"])
def test_untranslated_fields_are_declared(code: str) -> None:
    _check_untranslated_declared(lang.pack_for(code), EN)


@pytest.mark.parametrize("code", [code for code in LANGUAGES if code != "EN"])
def test_same_as_en_entries_resolve(code: str) -> None:
    _check_same_as_en_entries(lang.pack_for(code), EN)


# ---------------------------------------------------------------------------
# Negative tests: every guard rejects the defect it exists for. They replace manual mutation
# checks; ``dataclasses.replace`` builds the broken pack from DE.
# ---------------------------------------------------------------------------


def _broken(**changes: Any) -> LanguagePack:
    return dataclasses.replace(DE, **changes)


def test_guard_rejects_an_untranslated_field_that_is_not_declared() -> None:
    with pytest.raises(AssertionError):
        _check_untranslated_declared(_broken(same_as_en=frozenset()), EN)


def test_guard_rejects_a_copy_of_the_english_pack() -> None:
    with pytest.raises(AssertionError):
        _check_untranslated_declared(dataclasses.replace(EN, code="XX", same_as_en=frozenset()), EN)


def test_guard_rejects_a_same_as_en_entry_without_a_field() -> None:
    with pytest.raises(KeyError):
        _check_same_as_en_entries(_broken(same_as_en=DE.same_as_en | {"se16.missing"}), EN)


def test_guard_rejects_a_same_as_en_entry_that_no_longer_equals_en() -> None:
    with pytest.raises(AssertionError):
        _check_same_as_en_entries(_broken(same_as_en=DE.same_as_en | {"se16.hit_count_label"}), EN)


def test_guard_rejects_a_flag_that_differs_from_en() -> None:
    names = canonical({**DE.keys.names, Key.ALT: Text(("Alt",))})  # word=True dropped
    with pytest.raises(AssertionError):
        _check_same_shape_as(_broken(keys=KeysSection(names=names)), EN)


def test_guard_rejects_a_text_kind_that_differs_from_en() -> None:
    changed = dataclasses.replace(DE.se11, dictionary_type=Text(("Dictionary-Typ",)))
    with pytest.raises(AssertionError):
        _check_same_shape_as(_broken(se11=changed), EN)


def test_guard_rejects_a_canonical_mapping_without_a_member() -> None:
    status = canonical({member: text for member, text in DE.sm37.status.items() if member != JobStatus.CANCELED})
    with pytest.raises(AssertionError):
        _check_canonical_mappings(_broken(sm37=dataclasses.replace(DE.sm37, status=status)))


def test_guard_rejects_a_variant_that_maps_to_two_members() -> None:
    status = canonical({**DE.sm37.status, JobStatus.READY: Text(("Geplant",))})
    with pytest.raises(AssertionError, match="Geplant"):
        _check_no_collisions("DE", _mappings(_broken(sm37=dataclasses.replace(DE.sm37, status=status))))


def test_guard_rejects_a_template_with_other_placeholders_than_en() -> None:
    changed = dataclasses.replace(DE.se24, display_title=Template(("Klassenpflege: {object} anzeigen",)))
    with pytest.raises(AssertionError):
        _check_same_placeholders(_broken(se24=changed), EN)


def test_guard_rejects_a_section_without_its_own_merge_declaration() -> None:
    @dataclasses.dataclass(frozen=True, slots=True)
    class Inheriting(PopupSection):  # inherits MERGE instead of declaring it in its own body
        pass

    with pytest.raises(AssertionError, match="declare MERGE"):
        _check_merge_modes(_broken(popup=Inheriting()))
