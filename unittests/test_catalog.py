"""Unit tests for the transaction catalog module.

Tests cover:
- TransactionInfo and TransactionCatalog models
- Area detection from transaction codes
- Search functionality (keyword, prefix, area filtering)
- Catalog loading and statistics
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sapguimcp.catalog.models import (
    SAP_AREA_PREFIXES,
    TransactionCatalog,
    TransactionInfo,
    detect_area,
)
from sapguimcp.catalog.search import (
    get_common_transactions,
    normalize_query,
    search_by_area,
    search_transactions,
    tokenize,
)

# =============================================================================
# Model Tests
# =============================================================================


class TestDetectArea:
    """Tests for area detection from transaction codes."""

    def test_sales_distribution_tcodes(self) -> None:
        """Test SD module detection."""
        assert detect_area("VA01") == "SD-Sales"
        assert detect_area("VA02") == "SD-Sales"
        assert detect_area("VL01N") == "SD-Shipping"
        assert detect_area("VF01") == "SD-Billing"

    def test_materials_management_tcodes(self) -> None:
        """Test MM module detection."""
        assert detect_area("ME21N") == "MM-Purchasing"
        assert detect_area("ME51N") == "MM-Purchasing"
        assert detect_area("MB01") == "MM-Inventory"
        assert detect_area("MM01") == "MM-General"

    def test_financial_accounting_tcodes(self) -> None:
        """Test FI module detection."""
        assert detect_area("FB01") == "FI-Postings"
        assert detect_area("FK01") == "FI-Vendors"
        assert detect_area("FD01") == "FI-Customers"
        assert detect_area("FS10") == "FI-GL"

    def test_basis_tcodes(self) -> None:
        """Test BC/Basis module detection."""
        assert detect_area("SE38") == "BC-Development"
        assert detect_area("SE11") == "BC-Development"
        assert detect_area("SM37") == "BC-Monitoring"
        assert detect_area("SU01") == "BC-Users"

    def test_unknown_tcodes(self) -> None:
        """Test that unknown prefixes return None."""
        assert detect_area("ZZ01") is None
        assert detect_area("YY99") is None
        assert detect_area("CUSTOM") is None

    def test_empty_and_short_tcodes(self) -> None:
        """Test edge cases for empty and short tcodes."""
        assert detect_area("") is None
        assert detect_area("V") is None
        assert detect_area("X") is None

    def test_case_insensitivity(self) -> None:
        """Test that detection is case-insensitive."""
        assert detect_area("va01") == "SD-Sales"
        assert detect_area("Va01") == "SD-Sales"
        assert detect_area("VA01") == "SD-Sales"

    def test_three_char_prefix_priority(self) -> None:
        """Test that 3-char prefixes are checked before 2-char."""
        # CO0* should match PP-Orders, not CO-General
        assert detect_area("CO01") == "PP-Orders"
        assert detect_area("CORT") == "CO-General"


class TestTransactionInfo:
    """Tests for TransactionInfo model."""

    def test_from_tstc_row_english_names(self) -> None:
        """Test creation from TSTC row with English/technical column names."""
        row = {
            "TCODE": "VA01",
            "PGMNA": "SAPMV45A",
            "DESSION": "100",
        }
        txn = TransactionInfo.from_tstc_row(row)

        assert txn.tcode == "VA01"
        assert txn.program == "SAPMV45A"
        assert txn.screen_number == "100"
        assert txn.area == "SD-Sales"
        assert txn.enriched is False

    def test_from_tstc_row_german_names(self) -> None:
        """Test creation from TSTC row with German display names."""
        row = {
            "Transaktionscode": "ME21N",
            "Programm": "SAPLMEGUI",
            "Dynpro": "200",
        }
        txn = TransactionInfo.from_tstc_row(row)

        assert txn.tcode == "ME21N"
        assert txn.program == "SAPLMEGUI"
        assert txn.screen_number == "200"
        assert txn.area == "MM-Purchasing"

    def test_from_tstc_row_missing_screen(self) -> None:
        """Test creation when screen number is missing."""
        row = {
            "TCODE": "SE38",
            "PGMNA": "SAPMS38M",
        }
        txn = TransactionInfo.from_tstc_row(row)

        assert txn.tcode == "SE38"
        assert txn.screen_number is None

    def test_from_tstc_row_strips_whitespace(self) -> None:
        """Test that values are properly stripped."""
        row = {
            "TCODE": "  VA01  ",
            "PGMNA": " SAPMV45A ",
            "DESSION": " 100 ",
        }
        txn = TransactionInfo.from_tstc_row(row)

        assert txn.tcode == "VA01"
        assert txn.program == "SAPMV45A"
        assert txn.screen_number == "100"

    def test_default_values(self) -> None:
        """Test default field values."""
        txn = TransactionInfo(tcode="TEST")

        assert txn.description == ""
        assert txn.program == ""
        assert txn.screen_number is None
        assert txn.transaction_type == "unknown"
        assert txn.area is None
        assert txn.enriched is False
        assert txn.gui_html is False
        assert txn.gui_java is False
        assert txn.gui_windows is False


class TestTransactionCatalog:
    """Tests for TransactionCatalog model."""

    def test_get_by_tcode_found(self) -> None:
        """Test looking up an existing transaction."""
        catalog = TransactionCatalog(
            transactions=[
                TransactionInfo(tcode="VA01", description="Create Sales Order"),
                TransactionInfo(tcode="VA02", description="Change Sales Order"),
            ]
        )

        result = catalog.get_by_tcode("VA01")
        assert result is not None
        assert result.description == "Create Sales Order"

    def test_get_by_tcode_not_found(self) -> None:
        """Test looking up a non-existent transaction."""
        catalog = TransactionCatalog(
            transactions=[
                TransactionInfo(tcode="VA01"),
            ]
        )

        result = catalog.get_by_tcode("ZZ99")
        assert result is None

    def test_get_by_tcode_case_insensitive(self) -> None:
        """Test that lookup is case-insensitive."""
        catalog = TransactionCatalog(
            transactions=[
                TransactionInfo(tcode="VA01"),
            ]
        )

        assert catalog.get_by_tcode("va01") is not None
        assert catalog.get_by_tcode("Va01") is not None

    def test_get_by_area(self) -> None:
        """Test filtering by area."""
        catalog = TransactionCatalog(
            transactions=[
                TransactionInfo(tcode="VA01", area="SD-Sales"),
                TransactionInfo(tcode="VA02", area="SD-Sales"),
                TransactionInfo(tcode="ME21N", area="MM-Purchasing"),
            ]
        )

        sd_txns = catalog.get_by_area("SD-Sales")
        assert len(sd_txns) == 2
        assert all(t.area == "SD-Sales" for t in sd_txns)

    def test_empty_catalog(self) -> None:
        """Test behavior of empty catalog."""
        catalog = TransactionCatalog()

        assert len(catalog.transactions) == 0
        assert catalog.get_by_tcode("VA01") is None
        assert catalog.get_by_area("SD-Sales") == []


# =============================================================================
# Search Tests
# =============================================================================


class TestSearchHelpers:
    """Tests for search helper functions."""

    def test_normalize_query(self) -> None:
        """Test query normalization."""
        assert normalize_query("va01") == "VA01"
        assert normalize_query("  VA01  ") == "VA01"
        assert normalize_query("Create Order") == "CREATE ORDER"

    def test_tokenize(self) -> None:
        """Test text tokenization."""
        assert tokenize("Create Sales Order") == ["CREATE", "SALES", "ORDER"]
        assert tokenize("VA01") == ["VA01"]
        assert tokenize("sales-order") == ["SALES", "ORDER"]
        assert tokenize("sales_order") == ["SALES", "ORDER"]
        assert tokenize("") == []


class TestSearchTransactions:
    """Tests for transaction search functionality."""

    @pytest.fixture
    def sample_catalog(self) -> TransactionCatalog:
        """Create a sample catalog for testing."""
        return TransactionCatalog(
            transactions=[
                TransactionInfo(
                    tcode="VA01",
                    description="Create Sales Order",
                    program="SAPMV45A",
                    area="SD-Sales",
                    enriched=True,
                ),
                TransactionInfo(
                    tcode="VA02",
                    description="Change Sales Order",
                    program="SAPMV45A",
                    area="SD-Sales",
                    enriched=True,
                ),
                TransactionInfo(
                    tcode="VA03",
                    description="Display Sales Order",
                    program="SAPMV45A",
                    area="SD-Sales",
                    enriched=True,
                ),
                TransactionInfo(
                    tcode="ME21N",
                    description="Create Purchase Order",
                    program="SAPLMEGUI",
                    area="MM-Purchasing",
                    enriched=True,
                ),
                TransactionInfo(
                    tcode="SE38",
                    description="ABAP Editor",
                    program="SAPMS38M",
                    area="BC-Development",
                    enriched=True,
                ),
            ]
        )

    def test_exact_tcode_match(self, sample_catalog: TransactionCatalog) -> None:
        """Test that exact tcode matches get highest score."""
        results = search_transactions(sample_catalog, "VA01")

        assert len(results) >= 1
        assert results[0].transaction.tcode == "VA01"
        assert results[0].score == 100.0
        assert results[0].match_type == "exact_tcode"

    def test_tcode_prefix_match(self, sample_catalog: TransactionCatalog) -> None:
        """Test that tcode prefix matches work."""
        results = search_transactions(sample_catalog, "VA")

        # Should find VA01, VA02, VA03 with prefix match
        va_results = [r for r in results if r.transaction.tcode.startswith("VA")]
        assert len(va_results) == 3
        assert all(r.match_type == "prefix_tcode" for r in va_results)
        assert all(r.score == 80.0 for r in va_results)

    def test_description_match(self, sample_catalog: TransactionCatalog) -> None:
        """Test that description matching works."""
        results = search_transactions(sample_catalog, "create order")

        # Should find VA01 and ME21N (both have "create" and "order")
        assert len(results) >= 2
        tcodes = [r.transaction.tcode for r in results]
        assert "VA01" in tcodes
        assert "ME21N" in tcodes

    def test_partial_description_match(self, sample_catalog: TransactionCatalog) -> None:
        """Test partial description matching."""
        results = search_transactions(sample_catalog, "sales")

        # Should find VA01, VA02, VA03 (all have "sales" in description)
        assert len(results) == 3
        assert all("sales" in r.transaction.description.lower() for r in results)

    def test_area_filter(self, sample_catalog: TransactionCatalog) -> None:
        """Test filtering by area."""
        results = search_transactions(sample_catalog, "order", area="MM")

        # Should only find MM-Purchasing transactions
        assert len(results) >= 1
        assert all(r.transaction.area.startswith("MM") for r in results if r.transaction.area)

    def test_limit_results(self, sample_catalog: TransactionCatalog) -> None:
        """Test that limit parameter works."""
        results = search_transactions(sample_catalog, "VA", limit=2)
        assert len(results) == 2

    def test_empty_query(self, sample_catalog: TransactionCatalog) -> None:
        """Test that empty query returns no results."""
        assert search_transactions(sample_catalog, "") == []
        assert search_transactions(sample_catalog, "   ") == []

    def test_no_matches(self, sample_catalog: TransactionCatalog) -> None:
        """Test behavior when no matches found."""
        results = search_transactions(sample_catalog, "ZZZZNONEXISTENT")
        assert results == []

    def test_case_insensitive_search(self, sample_catalog: TransactionCatalog) -> None:
        """Test that search is case-insensitive."""
        results_lower = search_transactions(sample_catalog, "va01")
        results_upper = search_transactions(sample_catalog, "VA01")
        results_mixed = search_transactions(sample_catalog, "Va01")

        assert len(results_lower) == len(results_upper) == len(results_mixed)
        assert results_lower[0].transaction.tcode == results_upper[0].transaction.tcode

    def test_program_match(self, sample_catalog: TransactionCatalog) -> None:
        """Test matching by program name."""
        results = search_transactions(sample_catalog, "SAPMS38M")

        assert len(results) >= 1
        assert any(r.transaction.tcode == "SE38" for r in results)

    def test_results_sorted_by_score(self, sample_catalog: TransactionCatalog) -> None:
        """Test that results are sorted by score descending."""
        # Add exact match for VA01
        results = search_transactions(sample_catalog, "VA01")

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestSearchByArea:
    """Tests for search_by_area function."""

    @pytest.fixture
    def sample_catalog(self) -> TransactionCatalog:
        """Create a sample catalog for testing."""
        return TransactionCatalog(
            transactions=[
                TransactionInfo(tcode="VA01", area="SD-Sales"),
                TransactionInfo(tcode="VA02", area="SD-Sales"),
                TransactionInfo(tcode="ME21N", area="MM-Purchasing"),
                TransactionInfo(tcode="SE38", area="BC-Development"),
            ]
        )

    def test_filter_by_exact_area(self, sample_catalog: TransactionCatalog) -> None:
        """Test filtering by exact area name."""
        results = search_by_area(sample_catalog, "SD-Sales")
        assert len(results) == 2
        assert all(t.area == "SD-Sales" for t in results)

    def test_filter_by_area_prefix(self, sample_catalog: TransactionCatalog) -> None:
        """Test filtering by area prefix."""
        results = search_by_area(sample_catalog, "SD")
        assert len(results) == 2

    def test_limit_results(self, sample_catalog: TransactionCatalog) -> None:
        """Test that limit parameter works."""
        results = search_by_area(sample_catalog, "SD", limit=1)
        assert len(results) == 1

    def test_no_matches(self, sample_catalog: TransactionCatalog) -> None:
        """Test behavior when no area matches."""
        results = search_by_area(sample_catalog, "HR")
        assert results == []


class TestGetCommonTransactions:
    """Tests for get_common_transactions function."""

    @pytest.fixture
    def sample_catalog(self) -> TransactionCatalog:
        """Create a sample catalog with various tcode lengths."""
        return TransactionCatalog(
            transactions=[
                # Short, common-looking tcodes (2-5 chars, no slashes, enriched)
                TransactionInfo(tcode="VA01", description="Create Sales Order", enriched=True),
                TransactionInfo(tcode="SE38", description="ABAP Editor", enriched=True),
                TransactionInfo(tcode="SM37", description="Job Overview", enriched=True),
                # Long tcodes
                TransactionInfo(tcode="PFCGMAINT", description="Profile Maintenance", enriched=True),
                # Tcodes with slashes (custom)
                TransactionInfo(tcode="/SAPAPO/RRP3", description="APO Planning", enriched=True),
                # Not enriched
                TransactionInfo(tcode="VA02", description="", enriched=False),
            ]
        )

    def test_returns_short_enriched_tcodes(self, sample_catalog: TransactionCatalog) -> None:
        """Test that common transactions are short, enriched tcodes."""
        results = get_common_transactions(sample_catalog)

        assert len(results) == 3
        tcodes = [t.tcode for t in results]
        assert "VA01" in tcodes
        assert "SE38" in tcodes
        assert "SM37" in tcodes

    def test_excludes_long_tcodes(self, sample_catalog: TransactionCatalog) -> None:
        """Test that long tcodes are excluded."""
        results = get_common_transactions(sample_catalog)
        assert not any(t.tcode == "PFCGMAINT" for t in results)

    def test_excludes_tcodes_with_slashes(self, sample_catalog: TransactionCatalog) -> None:
        """Test that tcodes with slashes are excluded."""
        results = get_common_transactions(sample_catalog)
        assert not any("/" in t.tcode for t in results)

    def test_excludes_not_enriched(self, sample_catalog: TransactionCatalog) -> None:
        """Test that non-enriched tcodes are excluded."""
        results = get_common_transactions(sample_catalog)
        assert not any(t.tcode == "VA02" for t in results)

    def test_limit_results(self, sample_catalog: TransactionCatalog) -> None:
        """Test that limit parameter works."""
        results = get_common_transactions(sample_catalog, limit=2)
        assert len(results) == 2

    def test_sorted_by_length(self, sample_catalog: TransactionCatalog) -> None:
        """Test that results are sorted by tcode length."""
        results = get_common_transactions(sample_catalog)
        lengths = [len(t.tcode) for t in results]
        assert lengths == sorted(lengths)


# =============================================================================
# Loader Tests
# =============================================================================


class TestCatalogLoader:
    """Tests for catalog loading functionality."""

    def test_load_catalog_from_json(self) -> None:
        """Test loading a catalog from a JSON file."""
        from sapguimcp.catalog.loader import load_catalog

        # Create a temporary catalog file
        catalog_data = {
            "transactions": [
                {"tcode": "VA01", "description": "Create Sales Order"},
                {"tcode": "VA02", "description": "Change Sales Order"},
            ],
            "source_system": "DEV",
            "language": "EN",
            "tstc_count": 2,
            "enriched_count": 2,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog_data, f)
            temp_path = Path(f.name)

        try:
            # Clear cache before test
            load_catalog.cache_clear()

            catalog = load_catalog(temp_path)

            assert len(catalog.transactions) == 2
            assert catalog.source_system == "DEV"
            assert catalog.language == "EN"
            assert catalog.get_by_tcode("VA01") is not None
        finally:
            temp_path.unlink()
            load_catalog.cache_clear()

    def test_load_catalog_missing_file(self) -> None:
        """Test loading from non-existent file returns empty catalog."""
        from sapguimcp.catalog.loader import load_catalog

        load_catalog.cache_clear()

        catalog = load_catalog(Path("/nonexistent/path/catalog.json"))
        assert len(catalog.transactions) == 0

    def test_reload_catalog_clears_cache(self) -> None:
        """Test that reload_catalog clears the cache."""
        from sapguimcp.catalog.loader import load_catalog, reload_catalog

        # Create temp catalog
        catalog_data = {"transactions": [{"tcode": "TEST1"}]}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog_data, f)
            temp_path = Path(f.name)

        try:
            load_catalog.cache_clear()

            # First load
            catalog1 = load_catalog(temp_path)
            assert len(catalog1.transactions) == 1

            # Modify file
            catalog_data["transactions"].append({"tcode": "TEST2"})
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(catalog_data, f)

            # Cached load should still have 1 transaction
            catalog2 = load_catalog(temp_path)
            assert len(catalog2.transactions) == 1

            # Reload should see the new data
            catalog3 = reload_catalog(temp_path)
            assert len(catalog3.transactions) == 2
        finally:
            temp_path.unlink()
            load_catalog.cache_clear()


# =============================================================================
# Scraper Model Tests (without live SAP)
# =============================================================================


class TestScraperModels:
    """Tests for scraper data handling (models only, no live SAP)."""

    def test_load_tstc_data(self) -> None:
        """Test loading raw TSTC data from JSON."""
        from sapguimcp.catalog.scraper import load_tstc_data

        tstc_data = {
            "success": True,
            "total_transactions": 2,
            "transactions": [
                {"TCODE": "VA01", "PGMNA": "SAPMV45A", "DESSION": "100"},
                {"TCODE": "ME21N", "PGMNA": "SAPLMEGUI", "DESSION": "200"},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(tstc_data, f)
            temp_path = Path(f.name)

        try:
            transactions = load_tstc_data(temp_path)

            assert len(transactions) == 2
            assert transactions[0]["TCODE"] == "VA01"
            assert transactions[1]["TCODE"] == "ME21N"
        finally:
            temp_path.unlink()

    def test_save_and_load_catalog(self) -> None:
        """Test saving and loading catalog.

        Note: Uses load_catalog_for_scraping (uncached) for scraper tests.
        The cached loader.load_catalog() is tested in TestCatalogLoader.
        """
        from sapguimcp.catalog.scraper import load_catalog_for_scraping, save_catalog

        catalog = TransactionCatalog(
            transactions=[
                TransactionInfo(tcode="VA01", description="Create Sales Order"),
            ],
            source_system="DEV",
            language="EN",
            last_updated=datetime.now(UTC),
            tstc_count=1,
            enriched_count=1,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            save_catalog(catalog, temp_path)
            loaded = load_catalog_for_scraping(temp_path)

            assert len(loaded.transactions) == 1
            assert loaded.transactions[0].tcode == "VA01"
            assert loaded.source_system == "DEV"
        finally:
            temp_path.unlink()


# =============================================================================
# Area Prefix Coverage
# =============================================================================


class TestAreaPrefixCoverage:
    """Test that SAP_AREA_PREFIXES dictionary is comprehensive."""

    def test_all_prefixes_have_valid_format(self) -> None:
        """Test that all area values follow the expected format."""
        for prefix, area in SAP_AREA_PREFIXES.items():
            # Prefix should be 2-3 uppercase letters
            assert len(prefix) in (2, 3), f"Prefix {prefix} has invalid length"
            assert prefix.isupper(), f"Prefix {prefix} should be uppercase"

            # Area should have format "XX-Name"
            assert "-" in area, f"Area {area} should contain hyphen"

    def test_common_modules_covered(self) -> None:
        """Test that common SAP modules are covered."""
        common_modules = ["SD", "MM", "FI", "CO", "HR", "PP", "PM", "QM", "PS"]

        for module in common_modules:
            matching_prefixes = [p for p in SAP_AREA_PREFIXES if SAP_AREA_PREFIXES[p].startswith(module)]
            assert len(matching_prefixes) > 0, f"Module {module} has no prefixes"


class TestFuzzySearch:
    """Tests for fuzzy matching via rapidfuzz (GH-250)."""

    def _make_catalog(self, transactions: list[TransactionInfo]) -> TransactionCatalog:
        return TransactionCatalog(transactions=transactions, source_system="test", language="DE")

    def _make_txn(self, tcode: str, description: str) -> TransactionInfo:
        return TransactionInfo(
            tcode=tcode,
            description=description,
            program="TEST",
            transaction_type="dialog",
            gui_html=True,
            gui_windows=True,
            enriched=True,
            retrieved_at=datetime.now(UTC),
        )

    def test_fuzzy_finds_emmacl_via_klarfalle(self) -> None:
        """The original GH-250 case: 'Klärfälle' should find 'Klärungsliste anzeigen'."""
        catalog = self._make_catalog([self._make_txn("EMMACL", "Klärungsliste anzeigen")])
        results = search_transactions(catalog, "Klärfälle", limit=10)
        tcodes = [r.transaction.tcode for r in results]
        assert "EMMACL" in tcodes, f"EMMACL not found via fuzzy search. Results: {tcodes}"

    def test_fuzzy_finds_non_substring_match(self) -> None:
        """Fuzzy matching finds results where query is NOT a substring of description."""
        catalog = self._make_catalog([self._make_txn("ZZ99", "Vertragskonto anlegen")])
        results = search_transactions(catalog, "Vertragskonten", limit=5)
        assert len(results) > 0, "Fuzzy should match 'Vertragskonten' against 'Vertragskonto anlegen'"
        assert results[0].match_type == "fuzzy"

    def test_exact_match_beats_fuzzy(self) -> None:
        """Exact tcode matches should always score higher than fuzzy."""
        catalog = self._make_catalog(
            [
                self._make_txn("VA01", "Kundenauftrag anlegen"),
                self._make_txn("ZZ01", "Kundenauftrag anlegen copy"),
            ]
        )
        results = search_transactions(catalog, "VA01", limit=5)
        assert results[0].score >= 80, "Exact/prefix match should score >= 80"
        assert results[0].transaction.tcode == "VA01"
