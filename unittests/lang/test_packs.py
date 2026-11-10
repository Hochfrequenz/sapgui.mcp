"""Unit tests for the DE/EN packs and the leaf walk over a pack (#1044, phase 2a)."""

import dataclasses

import pytest

from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.invariant import INVARIANT
from sapguimcp.lang.schema import JobStatus, LanguagePack, iter_leaves, resolve, sections
from sapguimcp.lang.text import Template, Text


def test_packs_carry_their_language() -> None:
    assert (DE.code, DE.html_lang, DE.logon_dropdown) == ("DE", "de", "Deutsch")
    assert (EN.code, EN.html_lang, EN.logon_dropdown) == ("EN", "en", "English")


def test_canonical_mappings_are_read_only() -> None:
    with pytest.raises(TypeError):
        DE.sm37.status[JobStatus.READY] = Text(("x",))  # type: ignore[index]


def test_templates_keep_the_word_order_of_each_language() -> None:
    assert isinstance(DE.se24.display_title, Template)
    match = DE.se24.display_title.search("Klassenpflege: CL_FOO anzeigen", name=r"[A-Z0-9_/]+")
    assert match is not None
    assert match["name"] == "CL_FOO"
    assert EN.se37.display_title.format(name="Z_FM") == "Function Builder: Display Z_FM"


def test_invariant_texts() -> None:
    assert INVARIANT.sm34_hint == Text(("SM34",))


def test_sections_skip_scalar_pack_fields() -> None:
    names = [name for name, _ in sections(DE)]
    assert "code" not in names
    assert names[0] == "common"
    assert len(names) == len(dataclasses.fields(LanguagePack)) - 5


def test_iter_leaves_and_resolve() -> None:
    leaves = dict(iter_leaves(DE))
    assert leaves["se16.hit_count_label"] == Text(("Anzahl Treffer",))
    assert leaves["sm37.status[Ready]"] == Text(("Bereit",))
    assert resolve(DE, "sm37.status[Ready]") == Text(("Bereit",))
    with pytest.raises(KeyError):
        resolve(DE, "se16.missing")
