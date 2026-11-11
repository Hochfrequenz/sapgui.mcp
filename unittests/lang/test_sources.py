"""``lang/sources.py``: one SAP source per pack field (#1044, phase 2c)."""

import dataclasses

import pytest

from sapguimcp import lang
from sapguimcp.lang.schema import iter_leaves
from sapguimcp.lang.sources import SOURCES, Manual, Message
from sapguimcp.lang.text import Template


def _paths(code: str) -> set[str]:
    return {path for path, _leaf in iter_leaves(lang.pack_for(code))}


@pytest.mark.parametrize("code", lang.supported_languages())
def test_every_pack_field_has_exactly_one_source(code: str) -> None:
    paths = _paths(code)
    assert sorted(paths - set(SOURCES)) == [], "add a source (or Manual) for these fields"
    assert sorted(set(SOURCES) - paths) == [], "these sources name fields that do not exist"


def test_every_manual_source_names_a_reason() -> None:
    assert [path for path, source in SOURCES.items() if isinstance(source, Manual) and not source.reason.strip()] == []


def test_sourced_keys_are_upper_case_technical_ids() -> None:
    for path, source in SOURCES.items():
        if isinstance(source, Manual):
            continue
        for field in dataclasses.fields(source):
            value = getattr(source, field.name)
            if field.name not in {"length", "relation"}:
                assert value == value.strip().upper(), f"{path}: {field.name}={value!r}"


def test_templates_come_from_messages_or_are_manual() -> None:
    en = dict(iter_leaves(lang.pack_for("EN")))
    for path, leaf in en.items():
        if isinstance(leaf, Template):
            assert isinstance(SOURCES[path], Message | Manual), path
