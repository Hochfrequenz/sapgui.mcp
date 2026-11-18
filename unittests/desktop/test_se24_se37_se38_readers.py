"""SE24 / SE37 / SE38 readers on the language packs (#1044, phase 3, area 3).

Covers the single-language bug of the SE24 table readers (visibility, static and constant were matched in English
only, so German private methods came out public), both languages for the readers that moved to the pack, and
the guarantee that a missing session language is never turned into an entry error.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from sapguimcp import lang
from sapguimcp.tools.se24_tools import _parse_attributes, _parse_methods
from sapguimcp.tools.se37_tools import _parse_se37_params

if TYPE_CHECKING:
    from sapguimcp.lang import LanguagePack


# One row per component: (visibility text, kind text, expected visibility, static)
_DE_ROWS = [
    ("Öffentlich", "Instanzmethode", "public", False),
    ("Geschützt", "Statische Methode", "protected", True),
    ("Privat", "Statische Methode", "private", True),
    ("Private", "Instanzmethode", "private", False),  # the domain text of SEOEXPOSE is English in both languages
    # live desktop table control on a DE logon: the DDIC domain texts are English
    ("Protected", "Static Method", "protected", True),
    ("Public", "Instance Method", "public", False),
]


_EN_ROWS = [
    ("Public", "Instance method", "public", False),
    ("Protected", "Static method", "protected", True),
    ("Private", "Static method", "private", True),
]


@pytest.mark.parametrize(("visibility", "kind", "expected", "static"), _DE_ROWS)
def test_desktop_methods_of_a_german_session_keep_visibility_and_static(
    lang_de: LanguagePack, visibility: str, kind: str, expected: str, static: bool
) -> None:
    rows = [{"Methode": "M", "Art": kind, "Sichtbarkeit": visibility, "Beschreibung": "d"}]
    [method] = _parse_methods(rows, lang_de)
    assert (method.visibility, method.is_static, method.description) == (expected, static, "d")


@pytest.mark.parametrize(("visibility", "kind", "expected", "static"), _EN_ROWS)
def test_desktop_methods_of_an_english_session_keep_visibility_and_static(
    lang_en: LanguagePack, visibility: str, kind: str, expected: str, static: bool
) -> None:
    rows = [{"Method": "M", "Level": kind, "Visibility": visibility, "Description": "d"}]
    [method] = _parse_methods(rows, lang_en)
    assert (method.visibility, method.is_static, method.description) == (expected, static, "d")


def test_desktop_attributes_of_a_german_session_read_private_protected_static_and_constant(
    lang_de: LanguagePack,
) -> None:
    rows = [
        {"Attribut": "A", "Art": "Instanzattribut", "Sichtbarkeit": "Privat", "Bezugstyp": "I", "Initialer Wert": "5"},
        {"Attribut": "B", "Art": "Statisches Attribut", "Sichtbarkeit": "Geschützt"},
        {"Attribut": "C", "Art": "Konstante", "Sichtbarkeit": "Öffentlich", "Initialer Wert": ""},
    ]
    a, b, c = _parse_attributes(rows, lang_de)
    assert (a.visibility, a.is_static, a.is_constant, a.type_ref, a.default_value) == (
        "private",
        False,
        False,
        "I",
        "5",
    )
    assert (b.visibility, b.is_static, b.is_constant) == ("protected", True, False)
    assert (c.visibility, c.is_static, c.is_constant, c.default_value) == ("public", False, True, None)


def test_desktop_attributes_of_an_english_session_read_the_same(lang_en: LanguagePack) -> None:
    rows = [
        {"Attribute": "A", "Level": "Instance attribute", "Visibility": "Private", "Assoc.Type": "I"},
        {"Attribute": "C", "Level": "Constant", "Visibility": "Public"},
    ]
    a, c = _parse_attributes(rows, lang_en)
    assert (a.visibility, a.is_constant, a.type_ref) == ("private", False, "I")
    assert (c.visibility, c.is_constant) == ("public", True)


_PARAM_DE = {
    "Parametername": "IV_X",
    "Typisierung": "TYPE",
    "Bezugstyp": "STRING",
    "Standardwert": "'A'",
    "Optional": "X",
    "Wertübergabe": "X",
    "Kurztext": "Text",
}


_PARAM_EN = {
    "Parameter Name": "IV_X",
    "Typing": "TYPE",
    "Associated Type": "STRING",
    "Default Value": "'A'",
    "Optional": "X",
    "Pass Value": "X",
    "Short Text": "Text",
}


@pytest.mark.parametrize(("row", "code"), [(_PARAM_DE, "DE"), (_PARAM_EN, "EN")])
def test_se37_signature_rows_read_the_same_in_both_languages(row: dict[str, str], code: str) -> None:
    with lang.use(code):
        t = lang.current("test")
    [param] = _parse_se37_params([row], "import", t)
    assert (param.name, param.typing, param.reference_type, param.default_value) == ("IV_X", "TYPE", "STRING", "'A'")
    assert (param.optional, param.pass_by_value, param.description) == (True, True, "Text")


def _tool_function(module: Any, register: str, tool: str) -> Any:
    mcp = FastMCP("test")
    getattr(module, register)(mcp)
    captured: dict[str, Any] = {}
    original = mcp.tool

    def _capture(*args: Any, **kwargs: Any) -> Any:
        decorator = original(*args, **kwargs)

        def _wrap(fn: Any) -> Any:
            captured[fn.__name__] = fn
            return decorator(fn)

        return _wrap

    mcp.tool = _capture  # type: ignore[method-assign,assignment]
    getattr(module, register)(mcp)
    return captured[tool]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("module", "register", "tool", "args"),
    [
        ("se24_tools", "register_se24_tools", "sap_se24_lookup", {"classes": "CL_X"}),
        ("se37_tools", "register_se37_tools", "sap_se37_lookup", {"function_modules": "Z_X"}),
        (
            "se24_edit_tools",
            "register_se24_edit_tools",
            "sap_se24_edit",
            {"class_name": "C", "method_name": "M", "new_source": "x"},
        ),
        ("se38_edit_tools", "register_se38_edit_tools", "sap_se38_edit", {"program_name": "Z", "new_source": "x"}),
    ],
)
async def test_a_session_without_a_language_pack_raises_instead_of_failing_quietly(
    module: str, register: str, tool: str, args: dict[str, str]
) -> None:
    mod = importlib.import_module(f"sapguimcp.tools.{module}")
    fn = _tool_function(mod, register, tool)
    backend = MagicMock()
    backend.backend_type = "desktop"
    with (
        patch.object(mod, "get_backend", new=AsyncMock(return_value=backend)),
        lang.use("XX"),
        pytest.raises(lang.UnsupportedLanguageError),
    ):
        await fn(**args)
