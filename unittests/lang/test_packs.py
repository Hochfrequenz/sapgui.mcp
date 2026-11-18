"""Unit tests for the DE/EN packs and the leaf walk over a pack (#1044, phase 2a)."""

import dataclasses

import pytest

from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.invariant import INVARIANT
from sapguimcp.lang.schema import JobStatus, LanguagePack, iter_leaves, resolve, sections
from sapguimcp.lang.text import Text


def test_packs_carry_their_language() -> None:
    assert (DE.code, EN.code) == ("DE", "EN")


def test_canonical_mappings_are_read_only() -> None:
    with pytest.raises(TypeError):
        DE.sm37.status[JobStatus.READY] = Text(("x",))  # type: ignore[index]


def test_invariant_texts() -> None:
    assert INVARIANT.sm34_hint == Text(("SM34",))


def test_sections_skip_scalar_pack_fields() -> None:
    names = [name for name, _ in sections(DE)]
    assert "code" not in names
    assert names[0] == "common"
    assert len(names) == len(dataclasses.fields(LanguagePack)) - 3


def test_iter_leaves_and_resolve() -> None:
    leaves = dict(iter_leaves(DE))
    assert leaves["se16.results_title"] == Text(("Treffer",))
    assert leaves["sm37.status[Ready]"] == Text(("Bereit",))
    assert resolve(DE, "sm37.status[Ready]") == Text(("Bereit",))
    with pytest.raises(KeyError):
        resolve(DE, "se16.missing")


@pytest.mark.parametrize("label", ["Maintain", "Edit"])
def test_en_sm30_maintain_button_variants(label: str) -> None:
    """S/4HANA labels the SM30 maintain button "Edit", ECC "Maintain"."""
    assert EN.sm30.maintain.contains(label)
