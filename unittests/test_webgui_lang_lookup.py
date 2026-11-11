"""``<html lang>`` lookup and the script argument convention for the WebGUI (#1044, phase 2c)."""

import pytest

from sapguimcp import lang
from unittests.lang.synthetic_pack import synthetic_pack


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("de", "DE"), ("de-DE", "DE"), ("EN_us", "EN"), (" en ", "EN"), ("fr-FR", "FR"), ("", None), ("  ", None)],
)
def test_language_for_html_lang(tag: str, expected: str | None) -> None:
    assert lang.language_for_html_lang(tag) == expected


def test_language_for_html_lang_uses_registered_packs() -> None:
    pack = synthetic_pack()
    with lang._register_for_tests(pack):
        assert lang.language_for_html_lang(f"{pack.html_lang}-YY") == pack.code
