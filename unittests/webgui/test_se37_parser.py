"""
Unit tests for SE37 (Function Builder) parser.

Tests parsing of YAML accessibility snapshots from SE37 function module display screens.
"""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.se37_parser import (
    SE37TabSnapshots,
    parse_se37_exceptions_snapshot,
    parse_se37_parameters_snapshot,
    parse_se37_snapshot,
)
from sapguimcp.models import SE37Entry, SE37Error

# Path to captured YAML snapshots
SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se37_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run integration tests first")
    return filepath.read_text(encoding="utf-8")


class TestFunctionModuleDetection:
    """Tests for detecting function module from heading."""

    def test_detect_fm_from_heading(self) -> None:
        """Function module name should be extracted from heading."""
        snapshot = _load_snapshot("se37_rfc_read_table_main")
        result = parse_se37_snapshot(snapshot, "RFC_READ_TABLE")

        assert isinstance(result, SE37Entry)
        assert result.function_module == "RFC_READ_TABLE"

    def test_not_found_returns_error(self) -> None:
        """Function module not found should return SE37Error."""
        snapshot = _load_snapshot("se37_not_found")
        result = parse_se37_snapshot(snapshot, "ZZZNOTEXIST_FM_99")

        assert isinstance(result, SE37Error)
        assert "not found" in result.error.lower()


class TestImportParameterParsing:
    """Tests for parsing import parameters."""

    def test_parse_import_parameters(self) -> None:
        """Import parameters should be parsed correctly."""
        snapshot = _load_snapshot("se37_rfc_read_table_import")
        params = parse_se37_parameters_snapshot(snapshot, "import")

        assert len(params) >= 5  # RFC_READ_TABLE has multiple import params

        # Find QUERY_TABLE parameter
        query_table = next((p for p in params if p.name == "QUERY_TABLE"), None)
        assert query_table is not None
        assert query_table.category == "import"
        assert query_table.typing == "LIKE"
        assert query_table.reference_type == "DD02L-TABNAME"

    def test_import_optional_flag(self) -> None:
        """Optional flag should be parsed for import parameters."""
        snapshot = _load_snapshot("se37_rfc_read_table_import")
        params = parse_se37_parameters_snapshot(snapshot, "import")

        # DELIMITER has optional checked
        delimiter = next((p for p in params if p.name == "DELIMITER"), None)
        assert delimiter is not None
        assert delimiter.optional is True

    def test_import_default_value(self) -> None:
        """Default value should be parsed for import parameters."""
        snapshot = _load_snapshot("se37_rfc_read_table_import")
        params = parse_se37_parameters_snapshot(snapshot, "import")

        # DELIMITER has default SPACE
        delimiter = next((p for p in params if p.name == "DELIMITER"), None)
        assert delimiter is not None
        assert delimiter.default_value == "SPACE"


class TestExportParameterParsing:
    """Tests for parsing export parameters."""

    def test_parse_export_parameters(self) -> None:
        """Export parameters should be parsed correctly."""
        snapshot = _load_snapshot("se37_rfc_read_table_export")
        params = parse_se37_parameters_snapshot(snapshot, "export")

        assert len(params) >= 1  # RFC_READ_TABLE has ET_DATA

        # Find ET_DATA parameter
        et_data = next((p for p in params if p.name == "ET_DATA"), None)
        assert et_data is not None
        assert et_data.category == "export"
        assert et_data.typing == "TYPE"
        assert et_data.reference_type == "SDTI_RESULT_TAB"


class TestTablesParameterParsing:
    """Tests for parsing tables parameters."""

    def test_parse_tables_parameters(self) -> None:
        """Tables parameters should be parsed correctly."""
        snapshot = _load_snapshot("se37_rfc_read_table_tables")
        params = parse_se37_parameters_snapshot(snapshot, "tables")

        assert len(params) >= 2  # RFC_READ_TABLE has FIELDS, DATA (OPTIONS has quotes in desc)

        # Find DATA parameter
        data_param = next((p for p in params if p.name == "DATA"), None)
        assert data_param is not None
        assert data_param.category == "tables"
        assert data_param.typing == "LIKE"
        assert data_param.reference_type == "TAB512"


class TestExceptionsParsing:
    """Tests for parsing exceptions."""

    def test_parse_exceptions(self) -> None:
        """Exceptions should be parsed correctly."""
        snapshot = _load_snapshot("se37_rfc_read_table_exceptions")
        exceptions = parse_se37_exceptions_snapshot(snapshot)

        assert len(exceptions) >= 4  # RFC_READ_TABLE has multiple exceptions

        # Find TABLE_NOT_AVAILABLE exception
        table_not_avail = next((e for e in exceptions if e.name == "TABLE_NOT_AVAILABLE"), None)
        assert table_not_avail is not None
        assert "Dictionary" in table_not_avail.description or "nicht" in table_not_avail.description


class TestFullParsing:
    """Tests for full function module parsing with all tabs."""

    def test_full_parse_rfc_read_table(self) -> None:
        """RFC_READ_TABLE should be fully parsed with all tabs."""
        main_snapshot = _load_snapshot("se37_rfc_read_table_main")

        tab_snapshots = SE37TabSnapshots(
            import_tab=_load_snapshot("se37_rfc_read_table_import"),
            export_tab=_load_snapshot("se37_rfc_read_table_export"),
            tables_tab=_load_snapshot("se37_rfc_read_table_tables"),
            exceptions_tab=_load_snapshot("se37_rfc_read_table_exceptions"),
        )

        result = parse_se37_snapshot(main_snapshot, "RFC_READ_TABLE", tab_snapshots)

        assert isinstance(result, SE37Entry)
        assert result.function_module == "RFC_READ_TABLE"
        assert len(result.import_parameters) >= 5
        assert len(result.export_parameters) >= 1
        assert len(result.tables_parameters) >= 2  # Some params have quotes in desc
        assert len(result.exceptions) >= 4

    def test_uppercase_fm_normalization(self) -> None:
        """Function module name should be normalized to uppercase."""
        main_snapshot = _load_snapshot("se37_rfc_read_table_main")
        result = parse_se37_snapshot(main_snapshot, "rfc_read_table")

        assert isinstance(result, SE37Entry)
        assert result.function_module == "RFC_READ_TABLE"
