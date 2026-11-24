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
from sapguimcp.lang.schema import Key, PopupSection, StatusTypeSection, UniversalView, merge
from sapguimcp.lang.text import Text
from sapguimcp.models.base import PopupType
from sapguimcp.session_language import set_session_language
from sapguimcp.tools.sap_tools import parse_shortcut_from_title
from sapguimcp.tools.se16_tools import register_se16_tools
from unittests.lang.synthetic_pack import CORE_CODE, core_pack, core_word

FULL = lang.supported_languages()  # the real full packs; a new pack must not break these tests
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
    assert lang.logon_languages() == (*FULL, CORE_CODE)
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
    with _register_for_tests(YY):
        assert lang.language_support(CORE_CODE) == "core"
    assert lang.logon_languages() == FULL
    assert lang.language_support(CORE_CODE) == "none"
    assert lang.universal().keys.names[Key.CTRL].variants == ("Strg", "Ctrl")


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


@pytest.mark.usefixtures("yy")
def test_universal_holds_the_core_language_after_the_full_ones() -> None:
    assert lang.universal().keys.names[Key.CTRL].variants == ("Strg", "Ctrl", core_word("Ctrl"))


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
# Collision guard: another language's keywords must not change how EN/DE texts are read
# ---------------------------------------------------------------------------

_EN_DE_POPUPS = (
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
    "Different original and logon languages",
    "Requests",
    "Object is locked by another user",
    "Objekttyp CL_X ist nicht vorhanden",
    "Transport required: provide P_TRKORR",
)
"""EN/DE popup titles and texts from the popup tests, as ``_classify_popup`` sees them."""

_EN_DE_STATUS = (
    "Objekt wurde aktiviert",
    "Object activated",
    "Objekt konnte nicht aktiviert werden",
    "Object could not be activated",
    "Programm ZFOO gesichert",
    "Daten gesichert",
    "Document saved",
    "Object is locked by another user",
)
"""EN/DE status-bar messages from the activation and status tests."""

_POPUP_FIELDS = ("type_error", "type_info", "type_confirm")
_STATUS_FIELDS = ("activation_confirmed", "activation_denied")


def _new_matches(popup: PopupSection, status: StatusTypeSection) -> list[str]:
    """Keyword fields that match an EN/DE text the EN and DE keywords of the same field do not match."""
    own_popup = merge([DE.popup, EN.popup])
    own_status = merge([DE.status_type, EN.status_type])
    checks: list[tuple[str, Text, Text, tuple[str, ...]]] = [
        *((f"popup.{name}", getattr(popup, name), getattr(own_popup, name), _EN_DE_POPUPS) for name in _POPUP_FIELDS),
        *(
            (f"status_type.{name}", getattr(status, name), getattr(own_status, name), _EN_DE_STATUS)
            for name in _STATUS_FIELDS
        ),
    ]
    return [
        f"{path} matches {text!r}"
        for path, theirs, own, texts in checks
        for text in texts
        if theirs.contains(text) and not own.contains(text)
    ]


@pytest.mark.parametrize("code", [code for code in lang.logon_languages() if code not in ("DE", "EN")])
def test_no_registered_language_changes_en_de_classification(code: str) -> None:
    """Every shipped full or core pack besides DE and EN."""
    pack = lang._CORE_PACKS.get(code) or lang.pack_for(code)  # pylint: disable=protected-access
    assert _new_matches(pack.popup, pack.status_type) == []


def test_the_test_core_pack_changes_no_en_de_classification() -> None:
    assert _new_matches(YY.popup, YY.status_type) == []


def test_a_colliding_core_keyword_fails_the_guard() -> None:
    """A word of the new language that also occurs in German text would turn DE popups into errors."""
    colliding = dataclasses.replace(YY.popup, type_error=Text(("Objekt",)))
    assert _new_matches(colliding, YY.status_type) == [
        "popup.type_error matches 'Inaktive Objekte'",
        "popup.type_error matches 'Objekttyp CL_X ist nicht vorhanden'",
    ]
