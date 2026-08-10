"""Tests for sapguimcp.utils.

``format_sap_date`` is covered separately in ``test_date_helpers.py``.
"""

import logging

import pytest

from sapguimcp.utils import as_sap_language


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

    def test_unrecognised_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """The fallback must not be silent: EN dates are MM/DD/YYYY, which a DE screen misreads."""
        with caplog.at_level(logging.WARNING, logger="sapguimcp.utils"):
            as_sap_language("FR")
        assert len(caplog.records) == 1
        # The value travels as structured context, not in the message text.
        assert getattr(caplog.records[0], "language", None) == "FR"

    @pytest.mark.parametrize("value", ["de", "DE", "en", "EN"])
    def test_recognised_is_not_logged(self, value: str, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="sapguimcp.utils"):
            as_sap_language(value)
        assert caplog.records == []
