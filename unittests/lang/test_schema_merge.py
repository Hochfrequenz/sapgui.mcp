"""Unit tests for the generic language pack merge (#1044, phase 2a)."""

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from sapguimcp.lang.schema import JobStatus, PopupSection, canonical, merge
from sapguimcp.lang.text import RegexText, Template, Text


@dataclasses.dataclass(frozen=True, slots=True)
class _Toy:
    code: str
    label: Text
    status: Mapping[JobStatus, Text]


def test_merge_concatenates_variants_without_duplicates() -> None:
    assert merge([Text(("Anzeigen", "Display")), Text(("Display",))]) == Text(("Anzeigen", "Display"))


def test_merge_keeps_flags() -> None:
    assert merge([Text(("Alt",), word=True), Text(("Alt",), word=True)]).word


def test_merge_rejects_differing_flags() -> None:
    with pytest.raises(ValueError, match="flags differ"):
        merge([Text(("a",)), Text(("a",), word=True)])


def test_merge_rejects_differing_kinds() -> None:
    with pytest.raises(TypeError, match="cannot merge"):
        merge([Text(("a",)), RegexText(("a",))])


def test_merge_regex_and_templates() -> None:
    assert merge([RegexText(("a.*",)), RegexText(("b.*",))]).patterns == ("a.*", "b.*")
    merged = merge([Template(("{n} anzeigen",)), Template(("Display {n}",))])
    assert merged.variants == ("{n} anzeigen", "Display {n}")


def test_merge_dataclasses_field_by_field() -> None:
    first = _Toy("DE", Text(("Geplant",)), canonical({JobStatus.SCHEDULED: Text(("Geplant",))}))
    second = _Toy(
        "EN",
        Text(("Scheduled",)),
        canonical({JobStatus.SCHEDULED: Text(("Scheduled",)), JobStatus.READY: Text(("Ready",))}),
    )
    merged = merge([first, second])
    assert merged.code == "DE"  # scalars come from the first item
    assert merged.label.variants == ("Geplant", "Scheduled")
    assert isinstance(merged.status, MappingProxyType)
    assert merged.status[JobStatus.SCHEDULED].variants == ("Geplant", "Scheduled")
    assert merged.status[JobStatus.READY].variants == ("Ready",)


def test_merge_needs_items() -> None:
    with pytest.raises(ValueError, match="at least one"):
        merge([])


def test_merge_mode_survives_slots() -> None:
    assert PopupSection.MERGE == "all"
    assert "MERGE" in vars(PopupSection)
    assert "MERGE" not in {field.name for field in dataclasses.fields(PopupSection)}
