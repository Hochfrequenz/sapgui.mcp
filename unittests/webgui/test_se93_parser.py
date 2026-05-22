"""
Unit tests for SE93 (Transaction Maintenance) parser.

Tests parsing of YAML accessibility snapshots from SE93 transaction display screens.
"""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.se93_parser import parse_se93_snapshot
from sapguimcp.models import SE93Entry, SE93Error

# Path to captured YAML snapshots
SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se93_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run integration tests first")
    return filepath.read_text(encoding="utf-8")


class TestTransactionTypeDetection:
    """Tests for detecting transaction type from heading."""

    def test_detect_dialog_transaction(self) -> None:
        """Dialog transaction heading should be detected."""
        snapshot = _load_snapshot("se93_va01_details")
        result = parse_se93_snapshot(snapshot, "VA01")

        assert isinstance(result, SE93Entry)
        assert result.transaction_type == "dialog"

    def test_detect_report_transaction(self) -> None:
        """Report transaction heading should be detected."""
        snapshot = _load_snapshot("se93_se38_details")
        result = parse_se93_snapshot(snapshot, "SE38")

        assert isinstance(result, SE93Entry)
        assert result.transaction_type == "report"

    def test_not_found_returns_error(self) -> None:
        """Transaction not found should return SE93Error."""
        snapshot = _load_snapshot("se93_not_found")
        result = parse_se93_snapshot(snapshot, "ZZZNOTEXIST99")

        assert isinstance(result, SE93Error)
        assert "not found" in result.error.lower()


class TestDialogTransactionParsing:
    """Tests for parsing dialog transaction details."""

    def test_parse_va01_basic_fields(self) -> None:
        """VA01 basic fields should be parsed correctly."""
        snapshot = _load_snapshot("se93_va01_details")
        result = parse_se93_snapshot(snapshot, "VA01")

        assert isinstance(result, SE93Entry)
        assert result.tcode == "VA01"
        assert result.transaction_type == "dialog"
        # German description
        assert "Kundenauftr" in result.description or "Sales Order" in result.description
        assert result.package == "VA"
        assert result.program == "SAPMV45A"

    def test_parse_va01_screen_number(self) -> None:
        """VA01 should have screen number (dialog-specific)."""
        snapshot = _load_snapshot("se93_va01_details")
        result = parse_se93_snapshot(snapshot, "VA01")

        assert isinstance(result, SE93Entry)
        assert result.screen_number == "101"
        # Report-specific fields should be None
        assert result.selection_screen is None

    def test_parse_va01_gui_capabilities(self) -> None:
        """VA01 GUI capabilities should be parsed."""
        snapshot = _load_snapshot("se93_va01_details")
        result = parse_se93_snapshot(snapshot, "VA01")

        assert isinstance(result, SE93Entry)
        assert result.gui_html is True
        assert result.gui_java is True
        assert result.gui_windows is True

    def test_parse_pfcg_with_auth_object(self) -> None:
        """PFCG should have authorization object."""
        snapshot = _load_snapshot("se93_pfcg_details")
        result = parse_se93_snapshot(snapshot, "PFCG")

        assert isinstance(result, SE93Entry)
        assert result.tcode == "PFCG"
        assert result.transaction_type == "dialog"
        assert result.authorization_object == "S_USER_AGR"


class TestReportTransactionParsing:
    """Tests for parsing report transaction details."""

    def test_parse_se38_basic_fields(self) -> None:
        """SE38 basic fields should be parsed correctly."""
        snapshot = _load_snapshot("se93_se38_details")
        result = parse_se93_snapshot(snapshot, "SE38")

        assert isinstance(result, SE93Entry)
        assert result.tcode == "SE38"
        assert result.transaction_type == "report"
        assert "ABAP" in result.description
        assert result.package == "SEDT"
        assert result.program == "RSABAPPROGRAM"

    def test_parse_se38_selection_screen(self) -> None:
        """SE38 should have selection screen (report-specific)."""
        snapshot = _load_snapshot("se93_se38_details")
        result = parse_se93_snapshot(snapshot, "SE38")

        assert isinstance(result, SE93Entry)
        assert result.selection_screen == "1000"
        # Dialog-specific fields should be None
        assert result.screen_number is None

    def test_parse_se38_gui_capabilities(self) -> None:
        """SE38 GUI capabilities should be parsed (no HTML for SE38)."""
        snapshot = _load_snapshot("se93_se38_details")
        result = parse_se93_snapshot(snapshot, "SE38")

        assert isinstance(result, SE93Entry)
        # SE38 doesn't support HTML GUI
        assert result.gui_html is False
        assert result.gui_java is True
        assert result.gui_windows is True

    def test_parse_se24_as_report(self) -> None:
        """SE24 (Class Builder) is a report transaction."""
        snapshot = _load_snapshot("se93_se24_details")
        result = parse_se93_snapshot(snapshot, "SE24")

        assert isinstance(result, SE93Entry)
        assert result.tcode == "SE24"
        assert result.transaction_type == "report"
        assert "Class" in result.description or "ABAP" in result.description
        assert result.selection_screen == "1000"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_uppercase_tcode_normalization(self) -> None:
        """Transaction code should be normalized to uppercase."""
        snapshot = _load_snapshot("se93_va01_details")
        result = parse_se93_snapshot(snapshot, "va01")

        assert isinstance(result, SE93Entry)
        assert result.tcode == "VA01"

    def test_empty_optional_fields(self) -> None:
        """Optional fields should be None when empty."""
        snapshot = _load_snapshot("se93_se24_details")
        result = parse_se93_snapshot(snapshot, "SE24")

        assert isinstance(result, SE93Entry)
        # SE24 doesn't have authorization object in our snapshot
        # start_variant is typically empty
        assert result.start_variant is None or result.start_variant == ""
