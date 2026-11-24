"""Core packs: log on in a language that has only the ``universal()`` sections (#1081).

A core-only session gets popup classification, activation checks and key names in its own language;
the transaction tools fail early with ``UnsupportedLanguageError``. Every language's ``universal()``
keywords also apply to EN and DE sessions, so the collision guard checks them against EN/DE texts.
"""

import dataclasses
from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from sapguimcp import lang
from sapguimcp.backend.desktop import _classify_popup, _confirms_activation
from sapguimcp.lang import CorePack, UnsupportedLanguageError, _register_for_tests
from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.schema import Key, Leaf, PackLike, UniversalView, iter_leaves, merge
from sapguimcp.lang.text import RegexText, Text
from sapguimcp.models.base import PopupType
from sapguimcp.session_language import set_session_language
from sapguimcp.tools.sap_tools import parse_shortcut_from_title
from sapguimcp.tools.se16_tools import register_se16_tools
from unittests.lang.synthetic_pack import CORE_CODE, core_pack, core_word

FULL = lang.supported_languages()  # snapshots of the real packs; a new full or core pack must not break these tests
LOGON = lang.logon_languages()
YY = core_pack()


@pytest.fixture
def yy() -> Iterator[CorePack]:
    with _register_for_tests(YY) as pack:
        yield pack


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("yy")
def test_a_core_language_is_a_logon_language_but_not_a_full_one() -> None:
    assert lang.logon_languages() == (*LOGON, CORE_CODE)
    assert lang.supported_languages() == FULL
    with pytest.raises(UnsupportedLanguageError):
        lang.pack_for(CORE_CODE)


@pytest.mark.usefixtures("yy")
@pytest.mark.parametrize(
    ("code", "level"), [("DE", "full"), ("en", "full"), (CORE_CODE, "core"), ("QQ", "none"), (None, "none")]
)
def test_language_support(code: str | None, level: str) -> None:
    assert lang.language_support(code) == level


def test_registration_is_scoped_to_the_block() -> None:
    ctrl = lang.universal().keys.names[Key.CTRL].variants
    with _register_for_tests(YY):
        assert lang.language_support(CORE_CODE) == "core"
    assert lang.logon_languages() == LOGON
    assert lang.language_support(CORE_CODE) == "none"
    assert lang.universal().keys.names[Key.CTRL].variants == ctrl


def test_registration_refuses_a_code_that_has_a_full_pack() -> None:
    with pytest.raises(ValueError, match="already registered"), _register_for_tests(dataclasses.replace(YY, code="DE")):
        pass


@pytest.mark.usefixtures("yy")
def test_current_explains_that_the_language_has_only_a_core_pack() -> None:
    with (
        lang.use(CORE_CODE),
        pytest.raises(
            UnsupportedLanguageError, match=rf"SE24 lookup needs a full language pack for {CORE_CODE}, .* core pack"
        ) as excinfo,
    ):
        lang.current("SE24 lookup")
    assert excinfo.value.supported == FULL


def test_a_core_pack_is_not_a_language_pack() -> None:
    assert isinstance(YY, UniversalView)
    assert not isinstance(YY, lang.LanguagePack)


# ---------------------------------------------------------------------------
# The language-independent core works in the core language
# ---------------------------------------------------------------------------


def test_universal_holds_the_core_language_after_the_other_ones() -> None:
    ctrl = lang.universal().keys.names[Key.CTRL].variants
    with _register_for_tests(YY):
        assert lang.universal().keys.names[Key.CTRL].variants == (*ctrl, core_word("Ctrl"))


@pytest.mark.usefixtures("yy")
@pytest.mark.parametrize("session", [CORE_CODE, "DE", None])
def test_popups_activation_and_key_names_of_the_core_language(session: str | None) -> None:
    with lang.use(session):
        assert _classify_popup(core_word("Error"), "") == PopupType.ERROR
        assert _classify_popup(core_word("Information"), "") == PopupType.INFO
        assert _classify_popup(core_word("Confirm"), "") == PopupType.CONFIRM
        assert _confirms_activation(f"Object {core_word('activated')}")
        assert not _confirms_activation(f"Object {core_word('could not')} {core_word('activated')}")
        info = parse_shortcut_from_title(f"X ({core_word('Ctrl')}+S)")
    assert info is not None
    assert info.shortcut == "Ctrl+S"


# ---------------------------------------------------------------------------
# A transaction tool fails early and clearly, as an MCP error (not an empty result)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.usefixtures("yy")
async def test_a_transaction_tool_in_a_core_language_fails_with_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = AsyncMock()

    async def get_backend(**_kwargs: object) -> AsyncMock:
        set_session_language(CORE_CODE)  # what BackendManager does for a session logged on in YY
        return backend

    monkeypatch.setattr("sapguimcp.tools.se16_tools.get_backend", get_backend)
    server = FastMCP("t")
    register_se16_tools(server)
    async with Client(server) as client:
        with pytest.raises(ToolError, match=rf"sap_se16_query needs a full language pack for {CORE_CODE}"):
            await client.call_tool("sap_se16_query", {"table": "T000"})
    assert not backend.mock_calls  # failed before touching SAP


# ---------------------------------------------------------------------------
# Collision guard: another language's texts must not match EN/DE texts that EN/DE do not match
# ---------------------------------------------------------------------------

_EN_DE_TEXTS = (
    # popup titles and texts
    "Fehler",
    "Error",
    "Hinweis",
    "Information",
    "Bestätigung",
    "Sichern bestätigen",
    "Confirm",
    "Daten sichern? Ja",
    "Inaktive Objekte",
    "Inactive Objects",
    "ABAP-Laufzeitfehler",
    "ABAP Runtime Errors",
    "Abweichende Original- und Anmeldesprache",
    "Originalsprache und Anmeldesprache",
    "Different original and logon languages",
    "Requests",
    "Objekttyp CL_X ist nicht vorhanden",
    # abapGit messages
    "Transport required: provide P_TRKORR",
    "Branch restore failed: was refs/heads/main; Transport required",
    # status-bar messages
    "Objekt wurde aktiviert",
    "Object activated",
    "Objekt konnte nicht aktiviert werden",
    "Object could not be activated",
    "Programm ZFOO gesichert",
    "Daten gesichert",
    "Document saved",
    "Object is locked by another user",
    # window titles and key names
    "SAP Easy Access",
    "Sichern (Strg+S)",
    "Save (Ctrl+S)",
    "Beenden (Umschalt+F3)",
    "Weiter (Eingabe)",
    "Löschen (Entf)",
)
"""EN/DE screen texts from the popup, status and shortcut tests."""

_UNIVERSAL = {field.name for field in dataclasses.fields(UniversalView)}
_OWN = dict(iter_leaves(merge([DE, EN])))


def _universal_leaves(pack: PackLike) -> dict[str, Leaf]:
    """Every text of the ``universal()`` sections, so a new field there is guarded without an edit."""
    return {path: leaf for path, leaf in iter_leaves(pack) if path.split(".")[0] in _UNIVERSAL}


def _matches(leaf: Leaf, text: str) -> bool:
    """Wider than any call site: a substring in any case (the desktop lower-cases titles itself)."""
    if isinstance(leaf, RegexText):
        return bool(leaf.pattern.search(text) or leaf.pattern.search(text.lower()))
    return any(variant.lower() in text.lower() for variant in leaf.variants)


def _new_matches(leaves: dict[str, Leaf]) -> list[str]:
    """Texts a field matches although the EN and DE values of the same field do not."""
    return [
        f"{path} matches {text!r}"
        for path, leaf in leaves.items()
        for text in _EN_DE_TEXTS
        if _matches(leaf, text) and not _matches(_OWN[path], text)
    ]


@pytest.mark.parametrize("code", [code for code in LOGON if code not in ("DE", "EN")])
def test_no_registered_language_changes_how_en_de_texts_are_read(code: str) -> None:
    """Every shipped full or core pack besides DE and EN."""
    pack = lang._CORE_PACKS.get(code) or lang.pack_for(code)  # pylint: disable=protected-access
    assert _new_matches(_universal_leaves(pack)) == []


def test_the_test_core_pack_changes_no_en_de_reading() -> None:
    assert _new_matches(_universal_leaves(YY)) == []


def test_the_guard_covers_every_universal_field() -> None:
    assert {path.split("[")[0] for path in _universal_leaves(YY)} >= {
        "popup.type_error",
        "popup.inactive_objects",
        "popup.original_language_hint",
        "popup.abapgit_transport_required",
        "status_type.activation_denied",
        "session_pages.debugger_window",
        "keys.names",
    }


@pytest.mark.parametrize(
    ("path", "leaf", "text"),
    [
        ("popup.type_error", Text(("Objekt",)), "Objekttyp CL_X ist nicht vorhanden"),
        ("popup.inactive_objects", Text(("Daten",), fold=False), "Daten gesichert"),
        ("popup.original_language_hint", RegexText(("gesichert",)), "Daten gesichert"),
        ("popup.abapgit_no_task", Text(("required",)), "Transport required: provide P_TRKORR"),
        ("keys.names[Ctrl]", Text(("Weiter",), word=True), "Weiter (Eingabe)"),
    ],
)
def test_a_colliding_word_fails_the_guard(path: str, leaf: Leaf, text: str) -> None:
    """A word of the new language that also occurs in EN or DE text would change how that text is read."""
    assert f"{path} matches {text!r}" in _new_matches({**_universal_leaves(YY), path: leaf})
