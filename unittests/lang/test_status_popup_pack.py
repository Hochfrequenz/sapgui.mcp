"""Status bar, popups, session pages and key names on the language packs (#1044, phase 3, area 2).

These checks read ``lang.universal()``: they must work without a session language, on an
unsupported one, and match every registered language. The WebGUI scripts run against the real
HTML snapshots in headless Chromium.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright

from sapguimcp import lang
from sapguimcp.backend.desktop import _classify_popup, _confirms_activation
from sapguimcp.backend.webgui.backend import WebGuiBackend, _parse_toolbar_note
from sapguimcp.models.base import PopupType
from sapguimcp.tools.sap_tools import SELECTORS, parse_shortcut_from_title

SNAPSHOTS = Path(__file__).resolve().parents[1] / "webgui" / "testdata" / "html_snapshots"


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
    ],
)
def test_activation_confirmation_in_every_language(message: str, confirmed: bool) -> None:
    assert _confirms_activation(message) is confirmed


@pytest.mark.usefixtures("any_session")
@pytest.mark.parametrize(
    ("note", "ok", "message"),
    [
        ('note "Erfolgreich Meldungsleiste Objekt wurde aktiviert"', True, "Objekt wurde aktiviert"),
        ('note "Success Message Bar Object activated"', True, "Object activated"),
        ('note "Fehler Meldungsleiste Syntaxfehler in Zeile 3"', False, "Syntaxfehler in Zeile 3"),
        ('note "Error Message Bar Syntax error in line 3"', False, "Syntax error in line 3"),
        ('note "Keine Syntaxfehler gefunden"', True, "Keine Syntaxfehler gefunden"),
        ('note "syntax error in program ZFOO"', False, "syntax error in program ZFOO"),
        # The prefixes are case-sensitive, as before: a lower-case note is not stripped.
        ('note "erfolgreich meldungsleiste x"', False, "erfolgreich meldungsleiste x"),
    ],
)
def test_toolbar_note_in_every_language(note: str, ok: bool, message: str) -> None:
    assert _parse_toolbar_note(note) == (ok, message)


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


def test_settings_button_selector_is_unchanged() -> None:
    """The test-only selector keeps the order of before the packs (English first, EN aria-label).

    The stems of packs added later (Italian) follow the German one.
    """
    assert SELECTORS["settings_button"] == (
        '[id*="settingsButton"], [title*="Setting" i], [title*="Einstellung" i], [title*="Impostazion" i], '
        'button[id*="gear" i], [aria-label*="Setting" i]'
    )


def test_popup_close_titles_keep_the_old_order() -> None:
    """check_popup.js tries [title*='Close'] before [title*='Schlie'], as before the packs; Italian comes after."""
    universal = lang.universal().popup.close
    assert lang.english_first(universal, lang.pack_for("EN").popup.close).variants == (
        "Close",
        "Schlie",
        "Chiudere",
        "Chiudi",
    )


# ---------------------------------------------------------------------------
# WebGUI scripts against the real snapshots
# ---------------------------------------------------------------------------


async def _on_snapshot(name: str, action: Any, html: str | None = None) -> Any:
    """Load a snapshot (or ``html``) into headless Chromium (page scripts off, no network), run ``action``."""
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            reason = f"Chromium cannot be launched here: {str(exc).splitlines()[0]}"
            if os.environ.get("CI"):
                pytest.fail(reason)  # CI installs Chromium; a silent skip would leave the JS untested
            pytest.skip(reason)
        try:
            context = await browser.new_context(java_script_enabled=False)
            await context.route("**/*", lambda route: route.abort())
            page = await context.new_page()
            content = html if html is not None else (SNAPSHOTS / name).read_text(encoding="utf-8")
            await page.set_content(content, wait_until="domcontentloaded")
            return await action(WebGuiBackend(page))
        finally:
            await browser.close()


async def _status(backend: WebGuiBackend) -> tuple[str, str]:
    info = await backend.get_status_bar()
    return info.type, info.message


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        # Bug fix: the noise filter knew only the German message-bar texts.
        ("se11_initial_en.html", ("none", "")),
        ("sm37_initial_en.html", ("none", "")),
        ("se16_initial_en.html", ("I", "Table Contents")),
        (
            "se38_error_popup_en.html",
            ("I", "Success Program AAAAAAAAAAAAAAAAAAAA does not existProgram AAAAAAAAAAAAAAAAAAAA does not exist"),
        ),
        # German results are unchanged.
        ("se11_initial_de.html", ("none", "")),
        (
            "se16_t000_content_de.html",
            ("E", "Fehler Bitte einen Tabellennamen eingebenBitte einen Tabellennamen eingebenTabelleninhalt"),
        ),
        ("se38_error_popup_de.html", ("I", "Das Programm AAAAAAAAAAAAAAAAAAAA ist nicht vorhanden")),
    ],
)
async def test_status_bar_noise_is_removed_in_both_languages(snapshot: str, expected: tuple[str, str]) -> None:
    assert await _on_snapshot(snapshot, _status) == expected


async def _field_ids(backend: WebGuiBackend) -> list[str]:
    return [field.id or "" for field in await backend.discover_fields()]


@pytest.mark.anyio
@pytest.mark.parametrize("language", ["de", "en"])
async def test_discover_fields_skips_readonly_dropdowns_in_both_languages(language: str) -> None:
    """Bug fix: the read-only dropdown check compared the German ARIA role description only (now ct=CB)."""
    ids = await _on_snapshot(f"su3_screen_{language}.html", _field_ids)
    assert ids  # the screen has fields
    for dropdown in ("M0:46:1:2B267::1:17", "M0:46:1:2B267::6:17", "M0:46:1:2B267::18:17"):
        assert dropdown not in ids


async def _popup(backend: WebGuiBackend) -> tuple[str | None, list[str], str | None]:
    popup = await backend.check_popup()
    assert popup is not None
    return popup.message, [button.label for button in popup.buttons], popup.close_button_id


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ("bp_validation_popup_de.html", ("Beenden", ["Ja", "Nein"], None)),
        ("bp_validation_popup_en.html", ("Exit", ["Yes", "No"], None)),
    ],
)
async def test_webgui_popup_message_skips_button_labels(snapshot: str, expected: Any) -> None:
    assert await _on_snapshot(snapshot, _popup) == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("snapshot", "close_id"),
    [("se38_error_popup_de.html", "SAPLSTRD353_1-close"), ("se38_error_popup_en.html", "SAPLSTRD352_1-close")],
)
async def test_webgui_popup_close_control_in_both_languages(snapshot: str, close_id: str) -> None:
    _, _, found = await _on_snapshot(snapshot, _popup)
    assert found == close_id


_MESSAGE_TEXT = '<div id="LSMSG_AREA"><span class="lsMsgText">{}</span></div>'
"""The dedicated message-text element: its text is the message, never noise-filtered."""
_CONTAINER_TEXT = '<div id="LSMSG_AREA"><span>{}</span></div>'
"""A generic span, as in the snapshots: its text carries the message bar's label and buttons."""


@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    [
        "Executed successfully",
        "Execute the report first",
        "Ausführen nicht möglich",
        "Function module was executed successfully",
        "You are not authorized to execute transaction SE38",
        "Message Bar settings saved",
    ],
)
async def test_message_text_element_is_never_noise_filtered(message: str) -> None:
    _, found = await _on_snapshot("", _status, html=_MESSAGE_TEXT.format(message))
    assert found == message


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # Lower-case message words survive: the noise is matched case-sensitively.
        ("Function module was executed successfully", "Function module was executed successfully"),
        ("Programm wird ausgeführt", "Programm wird ausgeführt"),
        # The real noise of the snapshots is still removed from container text.
        (
            "Business process code is not supported by EMMAExecute Emphasized",
            "Business process code is not supported by EMMA",
        ),
        ("Success Message Bar Object name missingView Details", "Success Object name missing"),
        ("Erfolgreich Meldungsleiste Daten gesichert", "Erfolgreich Daten gesichert"),
    ],
)
async def test_container_text_is_noise_filtered(message: str, expected: str) -> None:
    _, found = await _on_snapshot("", _status, html=_CONTAINER_TEXT.format(message))
    assert found == expected


_DROPDOWNS = (
    '<input id="sap-language-dropdown" ct="CB" readonly value="Deutsch" style="width:100px;height:20px">'
    '<input id="M0:46:::1:17" ct="CB" readonly value="Herr" style="width:100px;height:20px">'
    '<input id="M0:46:::2:17" ct="CBS" value="X" style="width:100px;height:20px">'
)


@pytest.mark.anyio
async def test_discover_fields_keeps_the_logon_language_dropdown() -> None:
    """Only read-only screen dropdowns are skipped; the logon page's language dropdown is reported as before."""
    ids = await _on_snapshot("", _field_ids, html=_DROPDOWNS)
    assert ids == ["sap-language-dropdown", "M0:46:::2:17"]
