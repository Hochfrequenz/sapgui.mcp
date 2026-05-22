"""
Tests for SPRO (Customizing IMG) search result parser.

Uses real YAML snapshots from exploration tests (DE) plus
synthetic snapshots for edge cases.
"""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.spro_parser import (
    _extract_results_section,
    parse_spro_search_results,
)

SPRO_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "spro_exploration"


# =============================================================================
# Real snapshot tests (DE)
# =============================================================================


class TestRealSearchResults:
    """Tests using the real DE search results snapshot for 'Land'."""

    @pytest.fixture
    def de_search_results(self) -> str:
        path = SPRO_SNAPSHOTS_DIR / "spro_search_results_land_de.yaml"
        if not path.exists():
            pytest.skip("DE search results snapshot not available")
        return path.read_text(encoding="utf-8")

    def test_parses_activities(self, de_search_results: str) -> None:
        result = parse_spro_search_results(de_search_results, "Land")
        assert result.success
        assert result.activity_count == 22
        assert len(result.activities) == result.activity_count

    def test_activity_has_name(self, de_search_results: str) -> None:
        result = parse_spro_search_results(de_search_results, "Land")
        for activity in result.activities:
            assert activity.activity_name, f"Activity missing name: {activity}"

    def test_activity_has_area(self, de_search_results: str) -> None:
        result = parse_spro_search_results(de_search_results, "Land")
        # Most activities should have an area (broad section)
        activities_with_area = [a for a in result.activities if a.area]
        assert len(activities_with_area) > 0

    def test_query_preserved(self, de_search_results: str) -> None:
        result = parse_spro_search_results(de_search_results, "Land")
        assert result.query == "Land"

    def test_retrieved_at_set(self, de_search_results: str) -> None:
        result = parse_spro_search_results(de_search_results, "Land")
        assert result.retrieved_at is not None

    def test_known_activity_present(self, de_search_results: str) -> None:
        """Check that a known activity from the snapshot is parsed."""
        result = parse_spro_search_results(de_search_results, "Land")
        names = [a.activity_name for a in result.activities]
        # From the real snapshot: "Zuordnung Kfz-Kennzeichen zu Land/Region pflegen"
        assert any("Kfz-Kennzeichen" in name for name in names)

    def test_parent_node_parsed(self, de_search_results: str) -> None:
        """Check that parent node column is parsed for activities that have one."""
        result = parse_spro_search_results(de_search_results, "Land")
        activities_with_parent = [a for a in result.activities if a.parent_node]
        assert len(activities_with_parent) > 0

    def test_no_selection_cells_in_results(self, de_search_results: str) -> None:
        """Ensure row selection hint text is not included as activity data."""
        result = parse_spro_search_results(de_search_results, "Land")
        for activity in result.activities:
            assert "Zum Auswählen" not in activity.activity_name
            assert "To select" not in activity.activity_name


class TestRealSearchResultsEN:
    """Tests using the real EN search results snapshot for 'country'."""

    @pytest.fixture
    def en_search_results(self) -> str:
        path = SPRO_SNAPSHOTS_DIR / "spro_search_results_country_en.yaml"
        if not path.exists():
            pytest.skip("EN search results snapshot not available")
        return path.read_text(encoding="utf-8")

    def test_parses_activities(self, en_search_results: str) -> None:
        result = parse_spro_search_results(en_search_results, "country")
        assert result.success
        assert result.activity_count > 0
        assert len(result.activities) == result.activity_count

    def test_known_activity_present(self, en_search_results: str) -> None:
        result = parse_spro_search_results(en_search_results, "country")
        names = [a.activity_name for a in result.activities]
        assert any("Country" in name for name in names)

    def test_no_selection_cells_in_results(self, en_search_results: str) -> None:
        result = parse_spro_search_results(en_search_results, "country")
        for activity in result.activities:
            assert "To select" not in activity.activity_name


# =============================================================================
# No results / edge cases
# =============================================================================


class TestNoResults:
    """Tests for snapshots without search results."""

    def test_no_results_dialog(self) -> None:
        """No results dialog in snapshot means empty results."""
        snapshot = """
- main "IMG anzeigen":
  - heading "IMG anzeigen" [level=1]
  - grid:
    - row "Row selection disabled.":
      - gridcell "Row selection disabled." [disabled]
"""
        result = parse_spro_search_results(snapshot, "nonexistent")
        assert result.success
        assert result.activity_count == 0
        assert result.activities == []

    def test_empty_snapshot(self) -> None:
        result = parse_spro_search_results("", "test")
        assert result.success
        assert result.activity_count == 0

    def test_query_preserved_on_no_results(self) -> None:
        result = parse_spro_search_results("no dialog here", "myquery")
        assert result.query == "myquery"


# =============================================================================
# Synthetic snapshot tests
# =============================================================================


class TestSyntheticSnapshots:
    """Tests using hand-crafted snapshots to cover parser edge cases."""

    def test_single_result(self) -> None:
        snapshot = """
  - dialog "Trefferliste zum Suchbegriff \\"test\\"":
    - heading "Trefferliste zum Suchbegriff \\"test\\"" [level=1]
    - grid:
      - rowgroup
      - rowgroup:
        - row "Spalte für Zeilenauswahl Gefundene Treffer Übergeordneter Knoten Im Bereich":
          - columnheader "Spalte für Zeilenauswahl"
          - columnheader "Gefundene Treffer"
          - columnheader "Übergeordneter Knoten"
          - columnheader "Im Bereich"
        - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. Test Activity Parent Node Test Area":
          - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
          - gridcell "Test Activity":
            - textbox
          - gridcell "Parent Node":
            - textbox
          - gridcell "Test Area":
            - textbox
      - rowgroup
    - toolbar:
      - button "Weiter"
"""
        result = parse_spro_search_results(snapshot, "test")
        assert result.success
        assert result.activity_count == 1
        assert result.activities[0].activity_name == "Test Activity"
        assert result.activities[0].parent_node == "Parent Node"
        assert result.activities[0].area == "Test Area"

    def test_multiple_results(self) -> None:
        snapshot = """
  - dialog "Trefferliste zum Suchbegriff \\"multi\\"":
    - heading "Trefferliste" [level=1]
    - grid:
      - rowgroup
      - rowgroup:
        - row "Spalte Gefundene Treffer":
          - columnheader "Gefundene Treffer"
        - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. Activity One Parent One Area One":
          - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
          - gridcell "Activity One":
            - textbox
          - gridcell "Parent One":
            - textbox
          - gridcell "Area One":
            - textbox
        - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. Activity Two Parent Two Area Two":
          - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
          - gridcell "Activity Two":
            - textbox
          - gridcell "Parent Two":
            - textbox
          - gridcell "Area Two":
            - textbox
      - rowgroup
    - toolbar:
      - button "Weiter"
"""
        result = parse_spro_search_results(snapshot, "multi")
        assert result.activity_count == 2
        assert result.activities[0].activity_name == "Activity One"
        assert result.activities[1].activity_name == "Activity Two"

    def test_empty_parent_and_area(self) -> None:
        snapshot = """
  - dialog "Trefferliste zum Suchbegriff \\"x\\"":
    - grid:
      - rowgroup:
        - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. Standalone Activity":
          - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
          - gridcell "Standalone Activity":
            - textbox
          - gridcell:
            - textbox
          - gridcell:
            - textbox
      - rowgroup
    - toolbar:
      - button "Weiter"
"""
        result = parse_spro_search_results(snapshot, "x")
        assert result.activity_count == 1
        assert result.activities[0].activity_name == "Standalone Activity"
        assert result.activities[0].parent_node == ""
        assert result.activities[0].area == ""

    def test_en_results_dialog(self) -> None:
        """Test that EN dialog title is also detected."""
        snapshot = """
  - dialog "Search Term \\"COUNTRY\\" Hit List":
    - heading "Search Term \\"COUNTRY\\" Hit List" [level=1]
    - grid:
      - rowgroup:
        - row "To select a row, press the space bar. Define Countries Enterprise Structure Financial Accounting":
          - gridcell "To select a row, press the space bar."
          - gridcell "Define Countries":
            - textbox
          - gridcell "Enterprise Structure":
            - textbox
          - gridcell "Financial Accounting":
            - textbox
      - rowgroup
    - toolbar:
      - button "Continue"
"""
        result = parse_spro_search_results(snapshot, "country")
        assert result.activity_count == 1
        assert result.activities[0].activity_name == "Define Countries"
        assert result.activities[0].parent_node == "Enterprise Structure"
        assert result.activities[0].area == "Financial Accounting"


# =============================================================================
# Internal helper tests
# =============================================================================


class TestExtractResultsSection:
    """Tests for _extract_results_section helper."""

    def test_extracts_de_section(self) -> None:
        snapshot = 'prefix\n  - dialog "Trefferliste zum Suchbegriff \\"x\\"":\n    - grid:\nmore'
        section = _extract_results_section(snapshot)
        assert section.startswith('dialog "Trefferliste')
        assert "prefix" not in section

    def test_extracts_en_section(self) -> None:
        snapshot = 'prefix\n  - dialog "Hit List for Search Term \\"y\\"":\n    - grid:\nmore'
        section = _extract_results_section(snapshot)
        assert section.startswith('dialog "Hit List')

    def test_empty_on_no_dialog(self) -> None:
        assert _extract_results_section("no results dialog here") == ""

    def test_empty_on_empty_input(self) -> None:
        assert _extract_results_section("") == ""
