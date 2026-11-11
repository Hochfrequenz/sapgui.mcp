"""Completeness of the WebGUI test packs (#1044, spec section 10, "Language in the test suite")."""

import dataclasses
from collections.abc import Iterator

import pytest

from sapguimcp import lang
from sapguimcp.lang import Text
from unittests.webgui.testdata.lang_test import TEST_DE, UI_TEST_PACKS, UiTestPack, resolve_sap_language

EN = UI_TEST_PACKS["EN"]


def _leaves(pack: UiTestPack) -> Iterator[tuple[str, object]]:
    """``(section.field, value)`` for every text of a test pack."""
    for section in dataclasses.fields(pack):
        value = getattr(pack, section.name)
        if dataclasses.is_dataclass(value):
            for field in dataclasses.fields(value):
                yield f"{section.name}.{field.name}", getattr(value, field.name)


def _check_complete(pack: UiTestPack) -> None:
    """Same fields, kinds and flags as the EN test pack; every value a ``Text`` with variants."""
    leaves = dict(_leaves(pack))
    expected = dict(_leaves(EN))
    assert leaves.keys() == expected.keys()
    for path, leaf in leaves.items():
        assert isinstance(leaf, Text), path
        assert all(variant.strip() for variant in leaf.variants), path
        other = expected[path]
        assert isinstance(other, Text), path
        assert (leaf.fold, leaf.word) == (other.fold, other.word), path


def _check_untranslated_declared(pack: UiTestPack) -> None:
    equal = {path for path, leaf in _leaves(pack) if leaf == dict(_leaves(EN))[path]}
    assert equal == pack.same_as_en


def test_every_registered_language_has_a_test_pack() -> None:
    assert set(UI_TEST_PACKS) == set(lang.supported_languages())


@pytest.mark.parametrize("code", sorted(UI_TEST_PACKS))
def test_test_pack_is_complete(code: str) -> None:
    pack = UI_TEST_PACKS[code]
    assert pack.code == code
    _check_complete(pack)


def test_en_test_pack_declares_nothing_as_same_as_en() -> None:
    assert EN.same_as_en == frozenset()


@pytest.mark.parametrize("code", sorted(code for code in UI_TEST_PACKS if code != "EN"))
def test_untranslated_test_texts_are_declared(code: str) -> None:
    _check_untranslated_declared(UI_TEST_PACKS[code])


def test_guard_rejects_a_missing_translation() -> None:
    copied = dataclasses.replace(TEST_DE, bp=EN.bp)
    with pytest.raises(AssertionError):
        _check_untranslated_declared(copied)


def test_guard_rejects_a_flag_that_differs_from_en() -> None:
    changed = dataclasses.replace(TEST_DE, bp=dataclasses.replace(TEST_DE.bp, yes_button=Text(("Ja",))))
    with pytest.raises(AssertionError):
        _check_complete(changed)


@pytest.mark.parametrize(
    ("env", "expected"),
    [(None, "DE"), ("en", "EN"), ("DE", "DE"), ("QQ", "DE")],
)
def test_sap_language_fixture_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, env: str | None, expected: str
) -> None:
    if env is None:
        monkeypatch.delenv("SAP_LANGUAGE", raising=False)
    else:
        monkeypatch.setenv("SAP_LANGUAGE", env)
    assert resolve_sap_language() == expected
