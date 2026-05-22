"""Tests for WebGuiBackend helper functions."""

from sapguimcp.backend.webgui.backend import _parse_toolbar_note
from sapguimcp.backend.webgui.utils import escape_css_selector


def test_parse_toolbar_note_success_de() -> None:
    """German success note should be parsed correctly."""
    snapshot = 'toolbar\n  note "Erfolgreich Meldungsleiste keine Syntaxfehler gefunden"'
    ok, msg = _parse_toolbar_note(snapshot)
    assert ok is True
    assert "keine Syntaxfehler" in msg


def test_parse_toolbar_note_success_en() -> None:
    """English success note should be parsed correctly."""
    snapshot = 'toolbar\n  note "Success Message Bar No syntax errors found"'
    ok, msg = _parse_toolbar_note(snapshot)
    assert ok is True
    assert "No syntax errors" in msg


def test_parse_toolbar_note_error_de() -> None:
    """German error note should be parsed correctly."""
    snapshot = 'toolbar\n  note "Fehler Meldungsleiste Syntaxfehler in Zeile 10"'
    ok, msg = _parse_toolbar_note(snapshot)
    assert ok is False
    assert "Syntaxfehler" in msg


def test_parse_toolbar_note_no_note() -> None:
    """Missing note should return failure."""
    ok, msg = _parse_toolbar_note("toolbar\n  heading 'Test'")
    assert ok is False
    assert "No status message" in msg


def test_escape_css_selector_special_chars() -> None:
    """SAP IDs with colons and brackets should be escaped."""
    assert escape_css_selector("#M0:48::btn[5]") == r"#M0\:48\:\:btn\[5\]"


def test_escape_css_selector_already_escaped() -> None:
    """Already-escaped selectors should not be double-escaped."""
    selector = r"#M0\:48\:\:btn\[5\]"
    assert escape_css_selector(selector) == selector


def test_escape_css_selector_no_special_chars() -> None:
    """Simple IDs should pass through unchanged."""
    assert escape_css_selector("#simple-id") == "#simple-id"


def test_escape_css_selector_partially_escaped() -> None:
    """Partially-escaped selectors should only escape the unescaped chars."""
    assert escape_css_selector(r"#M0\:48::btn[5]") == r"#M0\:48\:\:btn\[5\]"


def test_escape_css_selector_empty() -> None:
    """Empty selector should pass through."""
    assert escape_css_selector("") == ""
