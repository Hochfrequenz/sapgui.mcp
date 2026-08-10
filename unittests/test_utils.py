"""Tests for sapguimcp.utils."""

import pytest

from sapguimcp.utils import as_sap_language, format_sap_date


class TestAsSapLanguage:
    """``sap-mcp-config`` types ``language`` as ``str`` since 1.1.0, so it needs narrowing."""

    @pytest.mark.parametrize("value", ["DE", "de", "De", " de "])
    def test_german_variants(self, value: str) -> None:
        assert as_sap_language(value) == "DE"

    @pytest.mark.parametrize("value", ["EN", "en", " en "])
    def test_english_variants(self, value: str) -> None:
        assert as_sap_language(value) == "EN"

    @pytest.mark.parametrize("value", ["", "FR", "anything else"])
    def test_unrecognised_falls_back_to_en(self, value: str) -> None:
        """EN is the same default the config layer applies for a missing language."""
        assert as_sap_language(value) == "EN"


class TestFormatSapDate:
    def test_german_format(self) -> None:
        assert format_sap_date("2026-02-22", "DE") == "22.02.2026"

    def test_english_format(self) -> None:
        assert format_sap_date("2026-02-22", "EN") == "02/22/2026"

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected YYYY-MM-DD format"):
            format_sap_date("22.02.2026", "DE")
