"""Unit tests for SM30 (Table Maintenance View) parser."""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.sm30_parser import (
    detect_sm30_view_type,
    parse_sm30_columns,
    parse_sm30_rows,
    parse_sm30_snapshot,
)

# Test data directory
TESTDATA_DIR = Path(__file__).parent / "testdata" / "sm30_exploration"


class TestDetectViewType:
    """Tests for detect_sm30_view_type function."""

    def test_flat_table_detected(self) -> None:
        """A snapshot with columnheader elements should be detected as flat."""
        snapshot = """
- main "Sicht anzeigen":
  - grid:
    - rowgroup:
      - row "header":
        - columnheader "Country"
        - columnheader "Name"
        """
        assert detect_sm30_view_type(snapshot) == "flat"

    def test_initial_screen_is_unsupported(self) -> None:
        """A snapshot still on initial screen should be unsupported."""
        snapshot = """
- 'main "Tabellensicht-Pflege: Einstieg"':
  - heading "Tabellensicht-Pflege: Einstieg"
  - textbox "Tabelle/Sicht": V_T002
        """
        assert detect_sm30_view_type(snapshot) == "unsupported"

    def test_no_grid_is_unsupported(self) -> None:
        """A snapshot without grid or columnheaders should be unsupported."""
        snapshot = """
- main "Some other screen":
  - heading "Some random screen"
        """
        assert detect_sm30_view_type(snapshot) == "unsupported"

    def test_real_v_t005_snapshot_de(self) -> None:
        """Test detection from real DE snapshot if available."""
        snapshot_file = TESTDATA_DIR / "sm30_v_t005_display_de.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            assert detect_sm30_view_type(snapshot) == "flat"

    def test_real_v_t005_snapshot_en(self) -> None:
        """Test detection from real EN snapshot if available."""
        snapshot_file = TESTDATA_DIR / "sm30_v_t005_display_en.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            assert detect_sm30_view_type(snapshot) == "flat"


class TestParseColumns:
    """Tests for parse_sm30_columns function."""

    def test_parse_simple_columns(self) -> None:
        """Test extracting column names from a simple grid."""
        snapshot = """
  - grid:
    - rowgroup:
      - row "Spalte für Zeilenauswahl Land/Reg. Land/Region":
        - columnheader "Spalte für Zeilenauswahl"
        - columnheader "Land/Reg."
        - columnheader "Land/Region"
      - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. AD Andorra":
        - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
        """
        columns = parse_sm30_columns(snapshot)
        assert columns == ["Land/Reg.", "Land/Region"]

    def test_skips_selection_column_de(self) -> None:
        """German selection column should be skipped."""
        snapshot = """
  - grid:
    - rowgroup:
      - row "header":
        - columnheader "Spalte für Zeilenauswahl"
        - columnheader "Land"
        - columnheader "Bezeichnung"
      - row "Zum Auswählen einer Zeile data":
        """
        columns = parse_sm30_columns(snapshot)
        assert "Spalte für Zeilenauswahl" not in columns
        assert columns == ["Land", "Bezeichnung"]

    def test_skips_selection_column_en(self) -> None:
        """English selection column should be skipped."""
        snapshot = """
  - grid:
    - rowgroup:
      - row "header":
        - columnheader "Column for row selection"
        - columnheader "Country"
        - columnheader "Name"
      - row "To select a row DE Germany":
        """
        columns = parse_sm30_columns(snapshot)
        assert "Column for row selection" not in columns
        assert columns == ["Country", "Name"]

    def test_many_columns(self) -> None:
        """Test parsing many columns (SM30 views can have 20+)."""
        headers = "\n".join(f'        - columnheader "Col{i}"' for i in range(20))
        snapshot = f"""
  - grid:
    - rowgroup:
      - row "header":
{headers}
      - row "Zum Auswählen einer Zeile data":
        """
        columns = parse_sm30_columns(snapshot)
        assert len(columns) == 20

    def test_real_v_t005_snapshot(self) -> None:
        """Test parsing columns from real V_T005 snapshot if available."""
        for lang in ["de", "en"]:
            snapshot_file = TESTDATA_DIR / f"sm30_v_t005_display_{lang}.yaml"
            if snapshot_file.exists():
                snapshot = snapshot_file.read_text(encoding="utf-8")
                columns = parse_sm30_columns(snapshot)
                assert len(columns) > 0, f"No columns found in {lang} snapshot"


class TestParseRows:
    """Tests for parse_sm30_rows function."""

    def test_parse_simple_rows_de(self) -> None:
        """Test parsing rows with German hint text."""
        snapshot = """
  - grid:
    - rowgroup
    - rowgroup:
      - row "Spalte für Zeilenauswahl Land/Reg. Land/Region":
        - columnheader "Spalte für Zeilenauswahl"
        - columnheader "Land/Reg."
        - columnheader "Land/Region"
      - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. AD Andorra":
        - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
        - gridcell "AD":
          - textbox
        - gridcell "Andorra":
          - textbox
      - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. AE Ver.Arab.Emir.":
        - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
        - gridcell "AE":
          - textbox
        - gridcell "Ver.Arab.Emir.":
          - textbox
    - rowgroup
        """
        rows = parse_sm30_rows(snapshot)
        assert len(rows) == 2
        assert rows[0].values["Land/Reg."] == "AD"
        assert rows[0].values["Land/Region"] == "Andorra"
        assert rows[1].values["Land/Reg."] == "AE"
        assert rows[1].values["Land/Region"] == "Ver.Arab.Emir."

    def test_parse_simple_rows_en(self) -> None:
        """Test parsing rows with English hint text."""
        snapshot = """
  - grid:
    - rowgroup:
      - row "Column for row selection Country Name":
        - columnheader "Column for row selection"
        - columnheader "Country"
        - columnheader "Name"
      - row "To select a row, press the space bar. DE Germany":
        - gridcell "To select a row, press the space bar."
        - gridcell "DE":
          - textbox
        - gridcell "Germany":
          - textbox
      - row "To select a row, press the space bar. FR France":
        - gridcell "To select a row, press the space bar."
        - gridcell "FR":
          - textbox
        - gridcell "France":
          - textbox
    - rowgroup
        """
        rows = parse_sm30_rows(snapshot)
        assert len(rows) == 2
        assert rows[0].values["Country"] == "DE"
        assert rows[0].values["Name"] == "Germany"
        assert rows[1].values["Country"] == "FR"
        assert rows[1].values["Name"] == "France"

    def test_parse_empty_cells(self) -> None:
        """Test handling of empty gridcells."""
        snapshot = """
  - grid:
    - rowgroup:
      - row "header":
        - columnheader "Column for row selection"
        - columnheader "A"
        - columnheader "B"
      - row "To select a row data":
        - gridcell "To select a row, press the space bar."
        - gridcell "Val1":
          - textbox
        - gridcell:
          - textbox
    - rowgroup
        """
        rows = parse_sm30_rows(snapshot)
        assert len(rows) == 1
        assert rows[0].values["A"] == "Val1"
        assert rows[0].values["B"] == ""

    def test_button_between_rows_ignored(self) -> None:
        """Buttons between rows (like empty separator buttons) should be skipped."""
        snapshot = """
  - grid:
    - rowgroup:
      - row "Spalte für Zeilenauswahl Land":
        - columnheader "Spalte für Zeilenauswahl"
        - columnheader "Land"
      - button ""
      - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. DE":
        - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
        - gridcell "DE":
          - textbox
    - rowgroup
        """
        rows = parse_sm30_rows(snapshot)
        assert len(rows) == 1
        assert rows[0].values["Land"] == "DE"

    def test_real_v_t005_snapshot(self) -> None:
        """Test parsing rows from real V_T005 snapshot if available."""
        for lang in ["de", "en"]:
            snapshot_file = TESTDATA_DIR / f"sm30_v_t005_display_{lang}.yaml"
            if snapshot_file.exists():
                snapshot = snapshot_file.read_text(encoding="utf-8")
                rows = parse_sm30_rows(snapshot)
                assert len(rows) > 0, f"No rows found in {lang} snapshot"


class TestParseSm30Snapshot:
    """Tests for the main parse_sm30_snapshot function."""

    def test_view_not_found_de(self) -> None:
        """Test German not-found message (real ARIA structure)."""
        snapshot = """
- 'main "Tabellensicht-Pflege: Einstieg"':
  - 'heading "Tabellensicht-Pflege: Einstieg" [level=1]'
  - textbox "Tabelle/Sicht": ZZZNOTEXIST99
  - note "Fehler Meldungsleiste Tabelle/View ZZZNOTEXIST99 ist nicht im Dictionary vorhanden"
        """
        result = parse_sm30_snapshot(snapshot, "ZZZNOTEXIST99")
        assert not result.success
        assert "not found" in result.error.lower()
        assert result.view_type == "unsupported"

    def test_view_not_found_en(self) -> None:
        """Test English not-found message."""
        snapshot = """
- 'main "Table View Maintenance: Initial Screen"':
  - 'heading "Table View Maintenance: Initial Screen" [level=1]'
  - textbox "Table/View": ZZZNOTEXIST99
  - note "Error Message Bar Table/View ZZZNOTEXIST99 does not exist"
        """
        result = parse_sm30_snapshot(snapshot, "ZZZNOTEXIST99")
        assert not result.success
        assert "not found" in result.error.lower()

    def test_successful_flat_table_de(self) -> None:
        """Test parsing a successful German flat table view."""
        snapshot = """
- 'main "Sicht \\"Globale Parameter\\" anzeigen: Übersicht"':
  - 'heading "Sicht \\"Globale Parameter\\" anzeigen: Übersicht" [level=1]'
  - grid:
    - rowgroup
    - rowgroup:
      - row "Spalte für Zeilenauswahl Land/Reg. Land/Region":
        - columnheader "Spalte für Zeilenauswahl"
        - columnheader "Land/Reg."
        - columnheader "Land/Region"
      - button ""
      - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. DE Deutschland":
        - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
        - gridcell "DE":
          - textbox
        - gridcell "Deutschland":
          - textbox
    - rowgroup
    - rowgroup
  - button "Eintrag 1 von 50"
        """
        result = parse_sm30_snapshot(snapshot, "V_T005")
        assert result.success
        assert result.view_type == "flat"
        assert result.view_name == "V_T005"
        assert result.columns == ["Land/Reg.", "Land/Region"]
        assert result.row_count == 50  # From "Eintrag 1 von 50" button
        assert len(result.rows) == 1  # Only 1 row in snapshot
        assert result.rows[0].values["Land/Reg."] == "DE"
        assert result.rows[0].values["Land/Region"] == "Deutschland"
        assert result.description == "Globale Parameter"

    def test_successful_flat_table_en(self) -> None:
        """Test parsing a successful English flat table view."""
        snapshot = """
- 'main "Display View \\"Countries\\": Overview"':
  - 'heading "Display View \\"Countries\\": Overview" [level=1]'
  - grid:
    - rowgroup:
      - row "Column for row selection Country Name":
        - columnheader "Column for row selection"
        - columnheader "Country"
        - columnheader "Name"
      - row "To select a row, press the space bar. DE Germany":
        - gridcell "To select a row, press the space bar."
        - gridcell "DE":
          - textbox
        - gridcell "Germany":
          - textbox
    - rowgroup
  - button "Entry 1 of 100"
        """
        result = parse_sm30_snapshot(snapshot, "V_T005")
        assert result.success
        assert result.view_type == "flat"
        assert result.columns == ["Country", "Name"]
        assert result.row_count == 100  # From "Entry 1 of 100" button
        assert result.rows[0].values["Country"] == "DE"
        assert result.description == "Countries"

    def test_real_v_t005_de(self) -> None:
        """Test full parse from real DE snapshot if available."""
        snapshot_file = TESTDATA_DIR / "sm30_v_t005_display_de.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            result = parse_sm30_snapshot(snapshot, "V_T005")
            assert result.success
            assert result.view_type == "flat"
            assert len(result.columns) > 0
            assert result.row_count > 0
            assert len(result.rows) > 0
            # V_T005 should have country code and name columns
            first_row = result.rows[0]
            assert len(first_row.values) == len(result.columns)

    def test_real_v_t005_en(self) -> None:
        """Test full parse from real EN snapshot if available."""
        snapshot_file = TESTDATA_DIR / "sm30_v_t005_display_en.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            result = parse_sm30_snapshot(snapshot, "V_T005")
            assert result.success
            assert result.view_type == "flat"
            assert len(result.columns) > 0
            assert result.row_count > 0

    def test_real_not_found_de(self) -> None:
        """Test not-found from real DE snapshot if available."""
        snapshot_file = TESTDATA_DIR / "sm30_not_found_de.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            result = parse_sm30_snapshot(snapshot, "ZZZNOTEXIST99")
            assert not result.success

    def test_real_v_t002_not_found_de(self) -> None:
        """Test V_T002 (not in dictionary) from real DE snapshot if available."""
        snapshot_file = TESTDATA_DIR / "sm30_v_t002_display_de.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            result = parse_sm30_snapshot(snapshot, "V_T002")
            assert not result.success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
