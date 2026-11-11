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
        ("Zurück (F3)", "F3"),
    ],
)
def test_shortcuts_come_back_with_canonical_key_names(title: str, shortcut: str) -> None:
    """Bug fix: parse_shortcut_from_title returned localized names (Strg+S) that press_key rejects."""
    info = parse_shortcut_from_title(title)
    assert info is not None
    assert info.shortcut == shortcut


def test_settings_button_selector_keeps_both_languages() -> None:
    selector = SELECTORS["settings_button"]
    assert '[title*="Einstellungen" i]' in selector
    assert '[title*="Settings" i]' in selector
    assert '[id*="settingsButton"]' in selector


# ---------------------------------------------------------------------------
# WebGUI scripts against the real snapshots
# ---------------------------------------------------------------------------


async def _on_snapshot(name: str, action: Any) -> Any:
    """Load a snapshot into headless Chromium (page scripts off, no network) and run ``action``."""
    path = SNAPSHOTS / name
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
            await page.set_content(path.read_text(encoding="utf-8"), wait_until="domcontentloaded")
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
