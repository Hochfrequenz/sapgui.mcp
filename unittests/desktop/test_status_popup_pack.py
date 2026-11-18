"""Desktop popup classification and activation confirmation on the language packs (#1044, phase 3, area 2).

These checks read ``lang.universal()``: they must work without a session language, on an
unsupported one, and match every registered language. The WebGUI counterparts are in
the WebGUI test directory.
"""

from __future__ import annotations

from typing import Any

import pytest

from sapguimcp import lang
from sapguimcp.backend.desktop import _classify_popup, _confirms_activation
from sapguimcp.models.base import PopupType
from sapguimcp.tools.sap_tools import parse_shortcut_from_title


@pytest.fixture(params=[None, "XX", "DE", "EN"], ids=["no-session", "unsupported", "DE", "EN"])
def any_session(request: pytest.FixtureRequest) -> Any:
    """Every session state the universal sections must work in."""
    with lang.use(request.param):
        yield request.param


# ---------------------------------------------------------------------------
# Session-free: popups, status type, key names
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("any_session")
@pytest.mark.parametrize(
    ("title", "message", "expected"),
    [
        ("Fehler", "", PopupType.ERROR),
        ("Error", "", PopupType.ERROR),
        ("Hinweis", "", PopupType.INFO),
        ("Information", "", PopupType.INFO),
        ("Bestätigung", "", PopupType.CONFIRM),
        ("Sichern bestätigen", "", PopupType.UNKNOWN),  # "bestätigen" is not "Bestätigung", as before
        ("Confirm", "", PopupType.CONFIRM),
        ("Daten sichern?", "Ja", PopupType.CONFIRM),
        ("Inaktive Objekte", "", PopupType.UNKNOWN),
        ("Inactive Objects", "", PopupType.UNKNOWN),
    ],
)
def test_desktop_popup_type_in_every_language(title: str, message: str, expected: PopupType) -> None:
    assert _classify_popup(title, message) == expected


@pytest.mark.usefixtures("any_session")
@pytest.mark.parametrize(
    ("message", "confirmed"),
    [
        ("Objekt wurde aktiviert", True),
        ("Object activated", True),
        ("Objekt konnte nicht aktiviert werden", False),
        ("Object could not be activated", False),
        ("Programm ZFOO gesichert", False),
        ("Oggetto attivato", True),
        ("La classe non è stata attivata", False),
        ("Gli oggetti non sono stati attivati", False),
        ("Le classi non sono state attivate", False),
    ],
)
def test_activation_confirmation_in_every_language(message: str, confirmed: bool) -> None:
    assert _confirms_activation(message) is confirmed


@pytest.mark.usefixtures("any_session")
@pytest.mark.parametrize(
    ("title", "shortcut"),
    [
        ("Sichern (Strg+S)", "Ctrl+S"),
        ("Save (Ctrl+S)", "Ctrl+S"),
        ("Beenden (Umschalt+F3)", "Shift+F3"),
        ("Weiter (Eingabe)", "Enter"),
        ("Löschen (Entf)", "Delete"),
        ("Sortieren (Strg+Umschalt+F4)", "Ctrl+Shift+F4"),
        ("Menü (Alt+F10)", "Alt+F10"),
        ("X (Strg+Umsch+F1)", "Ctrl+Shift+F1"),
        ("Zurück (F3)", "F3"),
    ],
)
def test_shortcuts_come_back_with_canonical_key_names(title: str, shortcut: str) -> None:
    """Bug fix: parse_shortcut_from_title returned localized names (Strg+S) that press_key rejects."""
    info = parse_shortcut_from_title(title)
    assert info is not None
    assert info.shortcut == shortcut


_REAL_TITLES = (
    "Abweichende Original- und Anmeldesprache",
    "Originalsprache und Anmeldesprache",
    "Different original and logon languages",
)


@pytest.mark.usefixtures("any_session")
@pytest.mark.parametrize("title", _REAL_TITLES)
def test_original_language_hint_matches_the_real_dialog_titles(title: str) -> None:
    """#1087: the desktop dismiss matches the lower-cased window title against the hint."""
    assert lang.universal().popup.original_language_hint.pattern.search(title.lower())


@pytest.mark.usefixtures("any_session")
@pytest.mark.parametrize(
    "title", ["anlegen klasse", "sprachen abgleichen original", "originaltext in der fremdsprache anzeigen"]
)
def test_original_language_hint_ignores_unrelated_titles(title: str) -> None:
    """Desktop presses Enter on a match, so near-miss titles must not match."""
    assert not lang.universal().popup.original_language_hint.pattern.search(title)
