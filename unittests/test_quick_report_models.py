"""Unit tests for QuickReportResult and ScreenClassification models."""

import pytest
from pydantic import ValidationError

from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)


class TestScreenClassification:
    """Tests for ScreenClassification enum."""

    def test_values(self) -> None:
        assert ScreenClassification.TABLE == "table"
        assert ScreenClassification.EMPTY == "empty"
        assert ScreenClassification.ERROR == "error"
        assert ScreenClassification.UNKNOWN == "unknown"

    def test_from_string(self) -> None:
        assert ScreenClassification("table") == ScreenClassification.TABLE


class TestQuickReportResult:
    """Tests for QuickReportResult model."""

    def test_success_table_result(self) -> None:
        result = QuickReportResult(
            tcode="VA05",
            screen_type=ScreenClassification.TABLE,
            page_title="Auftragsübersicht",
            status_bar_type="S",
            status_bar_message="5 Einträge gelesen",
        )
        assert result.success is True
        assert result.screen_type == "table"
        assert result.tcode == "VA05"
        assert result.warnings == []
        assert result.table is None

    def test_success_empty_result(self) -> None:
        result = QuickReportResult(
            tcode="ME2M",
            screen_type=ScreenClassification.EMPTY,
            status_bar_type="I",
            status_bar_message="Keine Daten gefunden",
        )
        assert result.success is True
        assert result.screen_type == "empty"

    def test_success_error_screen_type(self) -> None:
        """success=True + screen_type=ERROR is valid (SAP responded with error)."""
        result = QuickReportResult(
            tcode="ME2M",
            screen_type=ScreenClassification.ERROR,
            status_bar_type="E",
            status_bar_message="Werk XXXX existiert nicht",
        )
        assert result.success is True
        assert result.screen_type == "error"

    def test_success_unknown_screen_type(self) -> None:
        result = QuickReportResult(
            tcode="ZCUSTOM01",
            screen_type=ScreenClassification.UNKNOWN,
        )
        assert result.success is True
        assert result.screen_type == "unknown"

    def test_infrastructure_failure(self) -> None:
        """success=False for infrastructure errors (no screen_type needed)."""
        result = QuickReportResult.failure(
            error="sap_quick_report requires WebGUI backend",
            tcode="VA05",
            screen_type=ScreenClassification.ERROR,
        )
        assert result.success is False
        assert result.error == "sap_quick_report requires WebGUI backend"

    def test_warnings_list(self) -> None:
        result = QuickReportResult(
            tcode="VA05",
            screen_type=ScreenClassification.TABLE,
            warnings=["Field 'FakeField' not found on screen"],
        )
        assert len(result.warnings) == 1

    def test_max_rows_field_constraint(self) -> None:
        """max_rows Field(ge=1) constraint is defined on the tool function, not the model.

        This is verified in test_quick_report_pipeline.py via the tool registration tests.
        """

    def test_json_roundtrip(self) -> None:
        original = QuickReportResult(
            tcode="VA05",
            screen_type=ScreenClassification.TABLE,
            page_title="Test",
            status_bar_type="S",
            status_bar_message="OK",
            warnings=["w1"],
        )
        json_str = original.model_dump_json()
        restored = QuickReportResult.model_validate_json(json_str)
        assert restored.tcode == original.tcode
        assert restored.screen_type == original.screen_type
        assert restored.warnings == original.warnings
