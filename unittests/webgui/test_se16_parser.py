"""Unit tests for SE16 (Data Browser) parser."""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.se16_parser import (
    parse_se16_columns,
    parse_se16_hit_count,
    parse_se16_rows,
    parse_se16_snapshot,
)

# Test data directory
TESTDATA_DIR = Path(__file__).parent / "testdata" / "se16_exploration"


class TestParseHitCount:
    """Tests for parse_se16_hit_count function."""

    def test_parse_simple_number(self) -> None:
        """Test parsing a simple number like '500'."""
        snapshot = 'textbox "Number of Hits": "500"'
        assert parse_se16_hit_count(snapshot) == 500

    def test_parse_german_locale_thousands(self) -> None:
        """Test parsing German locale with dot as thousands separator."""
        snapshot = 'textbox "Number of Hits": "5.000"'
        assert parse_se16_hit_count(snapshot) == 5000

    def test_parse_large_number(self) -> None:
        """Test parsing larger numbers with German locale."""
        snapshot = 'textbox "Number of Hits": "50.000"'
        assert parse_se16_hit_count(snapshot) == 50000

    def test_no_hit_count_field(self) -> None:
        """Test returns 0 when field is not found."""
        snapshot = "some other content without hit count"
        assert parse_se16_hit_count(snapshot) == 0

    def test_parse_from_real_snapshot(self) -> None:
        """Test parsing hit count from real SE16N snapshot."""
        snapshot_file = TESTDATA_DIR / "se16n_5000_debug.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            assert parse_se16_hit_count(snapshot) == 5000


class TestParseColumns:
    """Tests for parse_se16_columns function."""

    def test_parse_columns_from_header_row(self) -> None:
        """Test extracting column names from header row."""
        snapshot = """
      - row "Column for row selection Transaction Code Program":
        - columnheader "Column for row selection": To select all
        - columnheader "Transaction Code"
        - columnheader "Program"
        """
        columns = parse_se16_columns(snapshot)
        assert columns == ["Transaction Code", "Program"]

    def test_skips_selection_column(self) -> None:
        """Test that the row selection column is skipped."""
        snapshot = """
      - row "Column for row selection Field1 Field2":
        - columnheader "Column for row selection": helper text
        - columnheader "Field1"
        - columnheader "Field2"
        """
        columns = parse_se16_columns(snapshot)
        assert "Column for row selection" not in columns
        assert columns == ["Field1", "Field2"]

    def test_parse_from_real_snapshot(self) -> None:
        """Test parsing columns from real SE16N snapshot."""
        snapshot_file = TESTDATA_DIR / "se16n_5000_debug.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            columns = parse_se16_columns(snapshot)
            # TSTC table has these columns
            assert "Transaction Code" in columns
            assert "Program" in columns
            assert "Number" in columns
            assert len(columns) == 7


class TestParseRows:
    """Tests for parse_se16_rows function."""

    def test_parse_simple_row(self) -> None:
        """Test parsing a simple data row."""
        snapshot = """
      - row "Column for row selection Code Name":
        - columnheader "Column for row selection"
        - columnheader "Code"
        - columnheader "Name"
      - row "To select a row, press the space bar. ABC Test":
        - gridcell "To select a row, press the space bar."
        - gridcell "ABC":
          - textbox
        - gridcell "Test":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert len(rows) == 1
        assert rows[0]["Code"] == "ABC"
        assert rows[0]["Name"] == "Test"

    def test_parse_numeric_values_coerced(self) -> None:
        """Test that numeric values are coerced to int/float."""
        snapshot = """
      - row "Column for row selection ID Value":
        - columnheader "Column for row selection"
        - columnheader "ID"
        - columnheader "Value"
      - row "To select a row, press the space bar. 123 45.67":
        - gridcell "To select a row, press the space bar."
        - gridcell "123":
          - textbox
        - gridcell "45.67":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert len(rows) == 1
        assert rows[0]["ID"] == 123
        assert isinstance(rows[0]["ID"], int)
        assert rows[0]["Value"] == 45.67
        assert isinstance(rows[0]["Value"], float)

    def test_parse_empty_cells(self) -> None:
        """Test handling of empty cells."""
        snapshot = """
      - row "Column for row selection A B C":
        - columnheader "Column for row selection"
        - columnheader "A"
        - columnheader "B"
        - columnheader "C"
      - row "To select a row, press the space bar. Val1 Val3":
        - gridcell "To select a row, press the space bar."
        - gridcell "Val1":
          - textbox
        - gridcell:
          - textbox
        - gridcell "Val3":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert len(rows) == 1
        assert rows[0]["A"] == "Val1"
        assert rows[0]["B"] == ""
        assert rows[0]["C"] == "Val3"

    def test_parse_quoted_row_with_colons(self) -> None:
        """Test parsing rows that are YAML-quoted due to colons in values."""
        snapshot = """
      - row "Column for row selection Code Text":
        - columnheader "Column for row selection"
        - columnheader "Code"
        - columnheader "Text"
      - 'row "To select a row, press the space bar. ABC Activity: Test"':
        - gridcell "To select a row, press the space bar."
        - gridcell "ABC":
          - textbox
        - 'gridcell "Activity: Test"':
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert len(rows) == 1
        assert rows[0]["Code"] == "ABC"
        assert rows[0]["Text"] == "Activity: Test"

    def test_parse_from_quoted_row_snapshot(self) -> None:
        """Test parsing from snapshot with YAML-quoted rows (has colons)."""
        snapshot_file = TESTDATA_DIR / "se16n_norows_page69.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            rows = parse_se16_rows(snapshot)
            # This snapshot has rows with colons in transaction text
            assert len(rows) > 0
            # First row should have a transaction code starting with /ISDFPS/
            first_row = rows[0]
            assert "Transaction Code" in first_row
            assert first_row["Transaction Code"].startswith("/ISDFPS/")


class TestParseSe16Snapshot:
    """Tests for the main parse_se16_snapshot function."""

    def test_parse_complete_snapshot(self) -> None:
        """Test parsing a complete SE16N result snapshot."""
        snapshot_file = TESTDATA_DIR / "se16n_5000_debug.yaml"
        if snapshot_file.exists():
            snapshot = snapshot_file.read_text(encoding="utf-8")
            result = parse_se16_snapshot(snapshot)

            assert len(result.columns) == 7
            assert "Transaction Code" in result.columns
            # Should have ~13 rows visible in first page
            assert len(result.rows) >= 10

    def test_parse_t000_small_table(self) -> None:
        """Test parsing T000 results (small table with 6 rows)."""
        import json

        snapshot_file = TESTDATA_DIR / "se16n_t000_results.yaml"
        if snapshot_file.exists():
            content = snapshot_file.read_text(encoding="utf-8")
            # Handle JSON-wrapped snapshot
            if content.startswith("{"):
                data = json.loads(content)
                snapshot = data.get("snapshot", content)
            else:
                snapshot = content

            result = parse_se16_snapshot(snapshot)

            # T000 has columns like Client, Name, City, etc.
            assert len(result.columns) > 0
            assert "Client" in result.columns
            # T000 typically has 6 rows
            assert len(result.rows) == 6


class TestTypeCoercion:
    """Tests for value type coercion."""

    def test_integer_coercion(self) -> None:
        """Test that integer strings become int."""
        snapshot = """
      - row "Column for row selection Val":
        - columnheader "Column for row selection"
        - columnheader "Val"
      - row "To select a row, press the space bar. 42":
        - gridcell "To select a row, press the space bar."
        - gridcell "42":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert rows[0]["Val"] == 42
        assert isinstance(rows[0]["Val"], int)

    def test_negative_integer(self) -> None:
        """Test negative integer coercion."""
        snapshot = """
      - row "Column for row selection Val":
        - columnheader "Column for row selection"
        - columnheader "Val"
      - row "To select a row, press the space bar. -123":
        - gridcell "To select a row, press the space bar."
        - gridcell "-123":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert rows[0]["Val"] == -123

    def test_float_coercion(self) -> None:
        """Test that decimal strings become float."""
        snapshot = """
      - row "Column for row selection Val":
        - columnheader "Column for row selection"
        - columnheader "Val"
      - row "To select a row, press the space bar. 3.14":
        - gridcell "To select a row, press the space bar."
        - gridcell "3.14":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert rows[0]["Val"] == 3.14
        assert isinstance(rows[0]["Val"], float)

    def test_string_preserved(self) -> None:
        """Test that non-numeric strings stay as strings."""
        snapshot = """
      - row "Column for row selection Val":
        - columnheader "Column for row selection"
        - columnheader "Val"
      - row "To select a row, press the space bar. ABC123":
        - gridcell "To select a row, press the space bar."
        - gridcell "ABC123":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert rows[0]["Val"] == "ABC123"
        assert isinstance(rows[0]["Val"], str)

    def test_date_string_not_parsed(self) -> None:
        """Test that date strings remain as strings (no date parsing)."""
        snapshot = """
      - row "Column for row selection Val":
        - columnheader "Column for row selection"
        - columnheader "Val"
      - row "To select a row, press the space bar. 2024-01-15":
        - gridcell "To select a row, press the space bar."
        - gridcell "2024-01-15":
          - textbox
    - rowgroup
        """
        rows = parse_se16_rows(snapshot)
        assert rows[0]["Val"] == "2024-01-15"
        assert isinstance(rows[0]["Val"], str)


class TestLargeSnapshotParsing:
    """Tests for parsing large snapshots (5000+ rows simulation)."""

    def test_parse_multiple_pages_combined(self) -> None:
        """Test parsing when multiple page snapshots are combined."""
        # This simulates what the tool does when collecting rows
        snapshot_files = [
            TESTDATA_DIR / "se16n_pagination_initial.yaml",
            TESTDATA_DIR / "se16n_norows_page69.yaml",
        ]

        all_rows: list[dict] = []
        columns: list[str] | None = None

        for snapshot_file in snapshot_files:
            if snapshot_file.exists():
                # Handle JSON-wrapped snapshots
                content = snapshot_file.read_text(encoding="utf-8")
                if content.startswith("{"):
                    import json

                    data = json.loads(content)
                    snapshot = data.get("snapshot", content)
                else:
                    snapshot = content

                if columns is None:
                    columns = parse_se16_columns(snapshot)

                rows = parse_se16_rows(snapshot, columns)
                all_rows.extend(rows)

        if columns:
            assert len(columns) > 0
            assert len(all_rows) > 0
            # Both snapshots should have parsed successfully
            # Each page has ~13 rows
            assert len(all_rows) >= 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
