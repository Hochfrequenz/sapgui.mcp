"""A synthetic third language through the registry and every guard (#1044, spec section 10).

Exercises the N-language merge, template group naming, flag consistency and the
``UnsupportedLanguageError`` path before a real third language exists.
"""

import dataclasses
from collections.abc import Iterator

import pytest

from sapguimcp import lang
from sapguimcp.lang import UnsupportedLanguageError, _register_for_tests
from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.schema import JobStatus, Key, KeysSection, LanguagePack, canonical, merge
from sapguimcp.lang.text import RegexText, Text
from unittests.lang.synthetic_pack import CODE, MARK, mark, synthetic_pack
from unittests.lang.test_pack_completeness import (
    _check_canonical_mappings,
    _check_leaves_are_texts,
    _check_merge_modes,
    _check_no_collisions,
    _check_regexes_compile,
    _check_same_as_en_entries,
    _check_same_placeholders,
    _check_same_shape_as,
    _check_scalars,
    _check_untranslated_declared,
    _mappings,
)

XX = synthetic_pack()


@pytest.fixture
def xx() -> Iterator[LanguagePack]:
    with _register_for_tests(XX) as pack:
        yield pack


# ---------------------------------------------------------------------------
# The registration helper
# ---------------------------------------------------------------------------


def test_registration_is_scoped_to_the_block() -> None:
    before = lang.universal()  # primes the cache the helper has to clear
    with _register_for_tests(XX):
        assert lang.supported_languages() == ("DE", "EN", CODE)
        assert lang.pack_for("xx") is XX
        assert lang.universal() is not before
    assert lang.supported_languages() == ("DE", "EN")
    assert lang.universal().keys.names[Key.CTRL].variants == ("Strg", "Ctrl")
    with pytest.raises(UnsupportedLanguageError, match=r"supported: DE, EN$"):
        lang.pack_for(CODE)


def test_registration_clears_the_session_views() -> None:
    de_before = lang.view_for("DE")
    with _register_for_tests(XX):
        de_inside = lang.view_for("DE")
        assert de_inside is not de_before
        assert de_inside.keys.names[Key.CTRL].variants == ("Strg", "Ctrl", f"{MARK}Ctrl")
    assert lang.view_for("DE").keys.names[Key.CTRL].variants == ("Strg", "Ctrl")


def test_registration_refuses_a_registered_code() -> None:
    with pytest.raises(ValueError, match="already registered"), _register_for_tests(dataclasses.replace(XX, code="DE")):
        pass
    assert lang.pack_for("DE") is DE


def test_registration_refuses_an_unnormalized_code() -> None:
    with pytest.raises(ValueError, match="upper-case"), _register_for_tests(dataclasses.replace(XX, code="xx")):
        pass
    assert lang.supported_languages() == ("DE", "EN")


def test_registration_is_undone_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError, match="boom"), _register_for_tests(XX):
        raise RuntimeError("boom")
    assert lang.supported_languages() == ("DE", "EN")


# ---------------------------------------------------------------------------
# Every 2a guard over the synthetic pack
# ---------------------------------------------------------------------------


def test_synthetic_pack_passes_every_guard(xx: LanguagePack) -> None:
    view = lang.view_for(CODE)
    _check_scalars(xx)
    for pack in (xx, view):
        _check_leaves_are_texts(pack)
        _check_regexes_compile(pack)
        _check_canonical_mappings(pack)
    _check_regexes_compile(lang.universal())
    _check_same_shape_as(xx, EN)
    _check_same_placeholders(xx, EN)
    _check_merge_modes(xx)
    _check_untranslated_declared(xx, EN)
    _check_same_as_en_entries(xx, EN)
    assert len({lang.pack_for(code).html_lang for code in lang.supported_languages()}) == 3


@pytest.mark.parametrize("code", ["DE", "EN", CODE])
@pytest.mark.usefixtures("xx")
def test_no_variant_maps_to_two_members_with_three_languages(code: str) -> None:
    with lang.use(code):
        _check_no_collisions(code, _mappings(lang.current()))
    _check_no_collisions("universal", {"keys.names": lang.universal().keys.names})


def test_a_synthetic_pack_without_its_same_as_en_entry_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        _check_untranslated_declared(dataclasses.replace(XX, same_as_en=frozenset()), EN)


# ---------------------------------------------------------------------------
# N-language merge
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("xx")
def test_session_en_sections_hold_the_session_pack_then_en() -> None:
    with lang.use(CODE):
        view = lang.current()
    assert view.code == CODE
    assert view.same_as_en == XX.same_as_en
    assert view.se16.hit_count_label.variants == (f"{MARK}Number of Hits", "Number of Hits")  # no DE
    assert lang.view_for("DE").se16.hit_count_label.variants == ("Anzahl Treffer", "Number of Hits")  # no XX


@pytest.mark.usefixtures("xx")
def test_all_sections_hold_every_language() -> None:
    with lang.use(CODE):
        assert lang.current().keys.names[Key.CTRL].variants == (f"{MARK}Ctrl", "Strg", "Ctrl")  # session first
    assert lang.universal().keys.names[Key.CTRL].variants == ("Strg", "Ctrl", f"{MARK}Ctrl")  # registration order
    assert lang.universal().keys.names[Key.ALT].variants == ("Alt",)  # same_as_en: de-duplicated


@pytest.mark.usefixtures("xx")
def test_canonical_mapping_matches_every_language() -> None:
    status = lang.view_for(CODE).sm37.status
    assert status[JobStatus.READY].equals(f"{MARK}Ready")
    assert status[JobStatus.READY].equals("Ready")
    assert not status[JobStatus.READY].equals("Bereit")


# ---------------------------------------------------------------------------
# Template group naming across languages
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("xx")
def test_template_groups_have_the_same_name_in_every_language() -> None:
    title = lang.view_for(CODE).se24.display_title
    for heading in (f"{MARK}Class Builder: Display ZCL_FOO", "Class Builder: Display ZCL_FOO"):
        match = title.search(heading, name=r"[A-Z0-9_/]+")
        assert match is not None, heading
        assert match["name"] == "ZCL_FOO"


def test_a_three_language_template_merge_keeps_one_group_name() -> None:
    merged = merge([DE.se24.display_title, EN.se24.display_title, XX.se24.display_title])
    assert len(merged.variants) == len(DE.se24.display_title.variants) + 2
    for heading in (
        "Klassenpflege: ZCL_FOO anzeigen",
        "Class Builder: ZCL_FOO anzeigen",
        "Class Builder: Display ZCL_FOO",
        f"{MARK}Class Builder: Display ZCL_FOO",
    ):
        match = merged.search(heading, name=r"[A-Z0-9_/]+")
        assert match is not None, heading
        assert match["name"] == "ZCL_FOO"


def test_regex_marker_covers_every_branch_of_an_alternation() -> None:
    marked = mark(RegexText(("Alpha|Beta",)))
    assert marked.pattern.search(f"{MARK}Beta")
    assert not marked.pattern.search("Beta")


# ---------------------------------------------------------------------------
# Flag consistency
# ---------------------------------------------------------------------------


def _with_ctrl(text: Text) -> LanguagePack:
    return dataclasses.replace(XX, keys=KeysSection(names=canonical({**XX.keys.names, Key.CTRL: text})))


def test_a_flag_that_differs_from_en_fails_the_shape_guard() -> None:
    with pytest.raises(AssertionError):
        _check_same_shape_as(_with_ctrl(Text((f"{MARK}Ctrl",))), EN)  # word=True dropped


def test_a_flag_that_differs_fails_the_merge_of_every_language() -> None:
    with _register_for_tests(_with_ctrl(Text((f"{MARK}Ctrl",)))), pytest.raises(ValueError, match="flags differ"):
        lang.universal()


def test_a_kind_that_differs_fails_the_session_merge() -> None:
    broken = dataclasses.replace(XX, se11=dataclasses.replace(XX.se11, dictionary_type=Text(("Typ",))))
    with _register_for_tests(broken), pytest.raises(TypeError, match="cannot merge"):
        lang.view_for(CODE)


# ---------------------------------------------------------------------------
# UnsupportedLanguageError
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("xx")
def test_current_names_the_third_language_while_it_is_registered() -> None:
    with lang.use("IT"), pytest.raises(UnsupportedLanguageError, match="supported: DE, EN, XX") as excinfo:
        lang.current("SE24 lookup")
    assert excinfo.value.supported == ("DE", "EN", CODE)


def test_current_fails_for_the_third_language_once_it_is_gone() -> None:
    with _register_for_tests(XX), lang.use(CODE):
        assert lang.current().code == CODE
    with (
        lang.use(CODE),
        pytest.raises(UnsupportedLanguageError, match=r"needs a language pack for XX; supported: DE, EN$"),
    ):
        lang.current("SE24 lookup")
