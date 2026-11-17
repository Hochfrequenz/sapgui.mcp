"""``<html lang>`` lookup and the script argument convention for the WebGUI (#1044, phase 2c)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp import lang
from sapguimcp.backend.webgui.backend import WebGuiBackend, _logon_dropdown_text
from sapguimcp.backend.webgui.js_helpers import load_js, script_arg
from sapguimcp.lang.text import RegexText, Text
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


def test_script_arg_converts_texts_and_keeps_values() -> None:
    arg = script_arg({"hint": Text(("Hinweis",)), "row": RegexText(("a+",))}, label="Feld", count=2)
    assert arg == {
        "texts": {
            "hint": {"source": "Hinweis", "flags": "iu", "variants": ["Hinweis"]},
            "row": {"source": "(?:a+)", "flags": "iu"},
        },
        "label": "Feld",
        "count": 2,
    }


def test_script_arg_always_has_texts() -> None:
    assert script_arg(language="DE") == {"texts": {}, "language": "DE"}


def test_logon_dropdown_text_comes_from_the_pack() -> None:
    assert _logon_dropdown_text("DE") == "Deutsch"
    assert _logon_dropdown_text("EN") == "English"
    assert _logon_dropdown_text("FR") == "FR"


def test_set_language_field_has_no_ui_literal() -> None:
    script = load_js("set_language_field.js")
    assert "Deutsch" not in script
    assert "English" not in script
    assert "dropdownText" in script


@pytest.mark.anyio
async def test_login_passes_the_dropdown_text_to_the_script() -> None:
    page = MagicMock()
    for name in ("goto", "wait_for_load_state", "query_selector", "wait_for_selector", "fill", "evaluate", "click"):
        setattr(page, name, AsyncMock(return_value=object()))
    backend = WebGuiBackend.__new__(WebGuiBackend)
    backend._page = page
    with (
        patch.object(WebGuiBackend, "_find_okcode_field", new=AsyncMock(return_value=None)),
        patch.object(WebGuiBackend, "_post_login_setup", new=AsyncMock()),
    ):
        await backend.login("https://sap.example", "u", "p", "100", "DE")
    script, arg = page.evaluate.await_args_list[0].args
    assert script == load_js("set_language_field.js")
    assert arg == {"texts": {}, "language": "DE", "dropdownText": "Deutsch"}
