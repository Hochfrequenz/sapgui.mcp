"""Tests for SAP date format helper."""

import pytest

from sapguimcp.utils import format_sap_date


class TestFormatSapDate:
    """Tests for format_sap_date conversion."""

    def test_de_format(self) -> None:
        assert format_sap_date("2026-02-22", "DE") == "22.02.2026"

    def test_en_format(self) -> None:
        assert format_sap_date("2026-02-22", "EN") == "02/22/2026"

    def test_de_single_digit_day(self) -> None:
        assert format_sap_date("2026-01-05", "DE") == "05.01.2026"

    def test_en_single_digit_month(self) -> None:
        assert format_sap_date("2026-01-05", "EN") == "01/05/2026"

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError):
            format_sap_date("not-a-date", "DE")

    def test_lowercase_language_not_supported(self) -> None:
        """Lowercase language codes are not valid SapLanguage values (Literal['DE', 'EN'])."""
        # "de" doesn't match "DE", so it falls through to EN format
        assert format_sap_date("2026-02-22", "de") == "02/22/2026"  # type: ignore[arg-type]
