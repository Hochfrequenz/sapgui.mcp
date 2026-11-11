"""SE24 / SE37 / SE38 on the language packs (#1044, phase 3, area 3).

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
from sapguimcp.backend.webgui.parsers.se24_parser import (
    map_visibility,
    parse_se24_attributes_snapshot,
    parse_se24_methods_snapshot,
    parse_se24_snapshot,
)
from sapguimcp.backend.webgui.parsers.se37_parser import parse_se37_exceptions_snapshot, parse_se37_snapshot
from sapguimcp.models import SE24Entry, SE24Error, SE37Entry, SE37Error
from sapguimcp.tools.se24_tools import _parse_attributes, _parse_methods
from sapguimcp.tools.se37_tools import _parse_se37_params

if TYPE_CHECKING:
    from sapguimcp.lang import LanguagePack

# One row per component: (language, visibility text, kind text, expected visibility, static, constant)
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


def test_map_visibility_exact_versus_contains(lang_de: LanguagePack) -> None:
    assert map_visibility(lang_de, "Privat") == "private"
    assert map_visibility(lang_de, "Privat (Geschützt)", exact=True) == "public"  # not the whole cell text
    assert map_visibility(lang_de, "Privat (Geschützt)", exact=False) == "private"
    assert map_visibility(lang_de, None) == "public"
    assert map_visibility(lang_de, "") == "public"


_GRID_DE = """- grid:
  - rowgroup:
    - row "Methode Art Sichtbarkeit Methodentyp Beschreibung":
      - columnheader "Methode"
    - row "PRIV_STATIC Statische Methode Privat Leer Eine":
      - gridcell "PRIV_STATIC":
      - gridcell "Statische Methode":
      - gridcell "Privat":
      - gridcell "Leer":
      - gridcell "Eine":
    - row "ABS Abstrakte Methode Geschützt Leer":
      - gridcell "ABS":
      - gridcell "Abstrakte Methode":
      - gridcell "Geschützt":
      - gridcell "Leer":
"""

_ATTR_GRID_DE = """- grid:
  - rowgroup:
    - row "Attribut Art Sichtbarkeit":
      - columnheader "Attribut"
    - row "GC_CONST Konstante Privat Type I":
      - gridcell "GC_CONST":
      - gridcell "Konstante":
      - gridcell "Privat":
      - gridcell "Type":
      - gridcell "I":
"""


def test_webgui_methods_grid_of_a_german_session_reads_private_static_and_abstract(lang_de: LanguagePack) -> None:
    priv, abstract = parse_se24_methods_snapshot(_GRID_DE, lang_de)
    assert (priv.visibility, priv.is_static, priv.is_abstract) == ("private", True, False)
    assert (abstract.visibility, abstract.is_abstract) == ("protected", True)


def test_webgui_attribute_grid_of_a_german_session_reads_the_constant(lang_de: LanguagePack) -> None:
    [const] = parse_se24_attributes_snapshot(_ATTR_GRID_DE, lang_de)
    assert (const.is_constant, const.is_static, const.visibility) == (True, True, "private")


@pytest.mark.parametrize(
    ("heading", "name", "object_type"),
    [
        ("Class Builder: Klasse CL_FOO anzeigen", "CL_FOO", "class"),
        ("Class Builder: Interface IF_FOO anzeigen", "IF_FOO", "class"),  # the type comes from the type row, not here
        ("Class Builder: Display Class CL_FOO", "CL_FOO", "class"),
    ],
)
def test_the_heading_name_is_read_in_both_languages(
    lang_de: LanguagePack, heading: str, name: str, object_type: str
) -> None:
    result = parse_se24_snapshot(f'- heading "{heading}" [level=1]', "cl_other", lang_de)
    assert isinstance(result, SE24Entry)
    assert (result.class_name, result.object_type) == (name, object_type)


def test_the_object_type_row_decides_between_class_and_interface(lang_de: LanguagePack) -> None:
    snapshot = '- heading "Class Builder: Interface IF_FOO anzeigen"\n- text Objekttyp "Interface"'
    result = parse_se24_snapshot(snapshot, "IF_FOO", lang_de)
    assert isinstance(result, SE24Entry)
    assert result.object_type == "interface"


@pytest.mark.parametrize("heading", ["Class Builder: Einstieg", "Class Builder: Initial Screen"])
def test_the_initial_screen_is_an_error_in_both_languages(lang_de: LanguagePack, heading: str) -> None:
    result = parse_se24_snapshot(f'- heading "{heading}"', "CL_X", lang_de)
    assert isinstance(result, SE24Error)
    assert "initial screen" in result.error


@pytest.mark.parametrize("message", ["Klasse ZCL_X existiert nicht", "Class ZCL_X does not exist"])
def test_a_missing_class_is_reported_in_both_languages(lang_de: LanguagePack, message: str) -> None:
    result = parse_se24_snapshot(f'- heading "Class Builder: Display"\n- status "{message}"', "ZCL_X", lang_de)
    assert isinstance(result, SE24Error)
    assert "not found" in result.error


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


def test_se37_heading_name_and_not_found_in_both_languages(lang_de: LanguagePack) -> None:
    ok = parse_se37_snapshot('- heading "Function Builder: Z_FM anzeigen" [level=1]', "z_fm", lang_de)
    assert isinstance(ok, SE37Entry)
    assert ok.function_module == "Z_FM"
    en = parse_se37_snapshot('- heading "Function Builder: Display Z_FM" [level=1]', "z_fm", lang_de)
    assert isinstance(en, SE37Entry)
    assert en.function_module == "Z_FM"
    for message in ("Z_FM ist noch nicht vorhanden", "Function module Z_FM does not exist", "Z_FM not found"):
        result = parse_se37_snapshot(f'- heading "Function Builder: Display"\n- status "{message}"', "Z_FM", lang_de)
        assert isinstance(result, SE37Error), message


def test_se37_exception_rows_use_the_display_button_of_the_pack(lang_de: LanguagePack) -> None:
    snapshot = '- row "NOT_FOUND Not found Anzeigen":\n  - gridcell\n'
    [exception] = parse_se37_exceptions_snapshot(snapshot, lang_de)
    assert (exception.name, exception.description) == ("NOT_FOUND", "Not found")


# --- the unsupported language is not swallowed ------------------------------------------------------------------


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
        ("se37_edit_tools", "register_se37_edit_tools", "sap_se37_edit", {"function_module": "Z", "new_source": "x"}),
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


@pytest.mark.parametrize(
    ("code", "title"),
    [("DE", "ABAP Editor: Einstieg"), ("EN", "ABAP Editor: Initial Screen")],
)
def test_the_se38_initial_screen_title_matches_in_both_languages(code: str, title: str) -> None:
    """The window titles of the SE38 initial screen, as read live with a DE and an EN logon."""
    assert lang.view_for(code).abapgit.se38_initial_title.contains(title)
