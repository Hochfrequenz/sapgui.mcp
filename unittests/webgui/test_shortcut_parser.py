"""Tests for parse_shortcut_from_title in sap_tools."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from sapguimcp.tools.sap_tools import parse_shortcut_from_title

HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"


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
        assert result.shortcut == "Strg+S"

    def test_shift_combo(self) -> None:
        result = parse_shortcut_from_title("Beenden (Umschalt+F3)")
        assert result is not None
        assert result.action == "Beenden"
        assert result.shortcut == "Umschalt+F3"

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


class TestParseShortcutFromSe09Snapshot:
    """Regression tests using the SE09 HTML snapshot.

    The original bug occurred on SE09 (Transport Organizer) where some SAP DOM
    elements return null from el.title at runtime even though the [title] CSS
    selector matches them. Static HTML can't reproduce null titles, so we
    inject None values alongside the real titles to verify the parser handles
    the mixed input that JS would produce on a live SE09 screen.
    """

    @pytest.fixture()
    def se09_titles(self) -> list[str | None]:
        """Extract all title attribute values from the SE09 snapshot, plus injected Nones."""
        snapshot_path = HTML_SNAPSHOTS_DIR / "se09_shortcuts_de.html"
        if not snapshot_path.exists():
            pytest.skip("SE09 snapshot not available — run integration tests first")

        html = snapshot_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        titles: list[str | None] = [el.get("title") for el in soup.find_all(attrs={"title": True})]

        # Inject None values to simulate SAP's runtime behavior where el.title
        # returns null for some custom elements (the actual bug trigger)
        titles.insert(0, None)
        titles.insert(len(titles) // 2, None)
        titles.append(None)

        return titles

    def test_parser_handles_all_se09_titles_including_none(self, se09_titles: list[str | None]) -> None:
        """Parse every title from SE09 snapshot (including injected Nones) without crashing."""
        shortcuts = []
        for title in se09_titles:
            result = parse_shortcut_from_title(title)  # type: ignore[arg-type]
            if result is not None:
                shortcuts.append(result)

        # SE09 has known shortcuts like F3, F5, F6, F9
        shortcut_keys = [s.shortcut for s in shortcuts]
        assert any("F3" in k for k in shortcut_keys), f"Expected F3 shortcut on SE09. Found: {shortcut_keys}"

    def test_none_titles_are_skipped(self, se09_titles: list[str | None]) -> None:
        """Verify None values (the bug trigger) don't produce shortcuts."""
        for title in se09_titles:
            if title is None:
                assert parse_shortcut_from_title(title) is None  # type: ignore[arg-type]
