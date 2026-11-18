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
