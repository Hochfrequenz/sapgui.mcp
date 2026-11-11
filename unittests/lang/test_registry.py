"""Unit tests for the language pack registry and accessors (#1044, phase 2a)."""

import subprocess
import sys

import pytest

from sapguimcp import lang
from sapguimcp.lang import UnsupportedLanguageError
from sapguimcp.lang.de import DE
from sapguimcp.lang.schema import Key
from sapguimcp.session_language import current_language

UNKNOWN = "QQ"  # a language key no pack will ever use, so a new pack (e.g. IT) does not break these tests
BASE = lang.supported_languages()
BASE_TEXT = ", ".join(BASE)


def test_supported_languages_in_registration_order() -> None:
    assert lang.supported_languages()[:2] == ("DE", "EN")


def test_pack_for_normalizes_the_code() -> None:
    assert lang.pack_for(" de ") is DE


def test_pack_for_an_unknown_language() -> None:
    with pytest.raises(UnsupportedLanguageError, match=f"supported: {BASE_TEXT}") as excinfo:
        lang.pack_for(UNKNOWN)
    assert excinfo.value.language == UNKNOWN
    assert excinfo.value.supported == BASE


def test_use_sets_the_session_language() -> None:
    with lang.use("de"):
        assert current_language() == "DE"
    assert current_language() is None


def test_current_merges_the_session_pack_with_en() -> None:
    with lang.use("DE"):
        view = lang.current()
    assert view.code == "DE"
    assert view.same_as_en == DE.same_as_en
    assert view.se16.hit_count_label.variants == ("Anzahl Treffer", "Number of Hits")


def test_current_for_en_has_only_en() -> None:
    with lang.use("EN"):
        assert lang.current().se16.hit_count_label.variants == ("Number of Hits",)


def test_current_is_cached() -> None:
    with lang.use("DE"):
        assert lang.current() is lang.current()


def test_all_sections_in_the_session_view_match_every_language() -> None:
    with lang.use("EN"):
        assert lang.current().keys.names[Key.CTRL].variants == ("Ctrl", "Strg")


def test_current_without_a_session_language() -> None:
    with lang.use(None), pytest.raises(UnsupportedLanguageError, match="none is known"):
        lang.current("SE24 lookup")


def test_current_for_a_language_without_a_pack() -> None:
    with (
        lang.use(UNKNOWN),
        pytest.raises(UnsupportedLanguageError, match=f"SE24 lookup needs a language pack for {UNKNOWN}"),
    ):
        lang.current("SE24 lookup")


def test_universal_needs_no_session() -> None:
    with lang.use(None):
        names = lang.universal().keys.names
    assert names[Key.CTRL].variants == ("Strg", "Ctrl")
    assert names[Key.ALT].variants == ("Alt",)
    assert names[Key.ESCAPE].variants == ("Escape", "Esc")
    assert lang.universal() is lang.universal()


def test_invariant_is_a_constant_of_its_own_type() -> None:
    assert isinstance(lang.INVARIANT, lang.Invariant)
    assert lang.INVARIANT.sm34_hint.variants == ("SM34",)


def test_universal_is_not_a_language_pack() -> None:
    assert not isinstance(lang.universal(), lang.LanguagePack)
    assert isinstance(lang.universal(), lang.UniversalView)


def test_lang_de_fixture(lang_de: lang.LanguagePack) -> None:
    assert current_language() == "DE"
    assert lang_de is lang.current()
    assert lang_de.code == "DE"


def test_lang_en_fixture(lang_en: lang.LanguagePack) -> None:
    assert current_language() == "EN"
    assert lang_en is lang.current()
    assert lang_en.code == "EN"


def test_lang_does_not_import_the_config() -> None:
    """``models.config`` imports ``lang``; the reverse would be an import cycle (spec section 1)."""
    code = "import sys, sapguimcp.lang; sys.exit('sapguimcp.models.config' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0  # noqa: S603
