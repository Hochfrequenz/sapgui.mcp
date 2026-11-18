"""Tests for parse_shortcut_from_title in sap_tools."""

from sapguimcp.tools.sap_tools import parse_shortcut_from_title


class TestParseShortcutFromTitle:
    """Tests for the shortcut parser."""

    def test_simple_fkey(self) -> None:
        result = parse_shortcut_from_title("Person anlegen (F5)")
        assert result is not None
        assert result.action == "Person anlegen"
        assert result.shortcut == "F5"

    def test_ctrl_combo(self) -> None:
        result = parse_shortcut_from_title("Save (Strg+S)")
        assert result is not None
        assert result.action == "Save"
        assert result.shortcut == "Ctrl+S"  # canonical English key names (#1044)

    def test_shift_combo(self) -> None:
        result = parse_shortcut_from_title("Beenden (Umschalt+F3)")
        assert result is not None
        assert result.action == "Beenden"
        assert result.shortcut == "Shift+F3"

    def test_not_a_shortcut_date(self) -> None:
        result = parse_shortcut_from_title("Created (2024-01-01)")
        assert result is None

    def test_empty_string(self) -> None:
        result = parse_shortcut_from_title("")
        assert result is None

    def test_none_returns_none(self) -> None:
        """Regression: sap_get_shortcuts crashes with 'NoneType' has no attribute 'strip'
        when JS returns null title values from SAP screens like SE09."""
        result = parse_shortcut_from_title(None)  # type: ignore[arg-type]
        assert result is None

    def test_whitespace_only(self) -> None:
        result = parse_shortcut_from_title("   ")
        assert result is None

    def test_no_parens(self) -> None:
        result = parse_shortcut_from_title("Just a button")
        assert result is None
