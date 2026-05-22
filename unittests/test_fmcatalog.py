"""Unit tests for function module catalog search.

Tests cover:
- FM catalog loading
- Search by name, description, and parameter info
- Search terms like 'anlage', 'installation', 'vertrag' for IS-U relevance
"""

import pytest

from sapguimcp.fmcatalog.loader import get_catalog, load_catalog
from sapguimcp.fmcatalog.models import FMCatalog, FMParameter, FunctionModuleEntry
from sapguimcp.fmcatalog.search import FMSearchResult, search_function_modules


class TestFMCatalogLoader:
    """Tests for FM catalog loading."""

    def test_load_catalog_returns_catalog(self) -> None:
        """Test that load_catalog returns an FMCatalog."""
        load_catalog.cache_clear()
        catalog = load_catalog()
        assert isinstance(catalog, FMCatalog)

    def test_get_catalog_never_raises(self) -> None:
        """Test that get_catalog never raises exceptions."""
        catalog = get_catalog()
        assert isinstance(catalog, FMCatalog)

    def test_catalog_has_function_modules(self) -> None:
        """Test that catalog contains function modules."""
        catalog = get_catalog()
        assert catalog.total_count > 0
        assert len(catalog.function_modules) > 0


class TestFMCatalogSearch:
    """Tests for FM catalog search functionality."""

    @pytest.fixture
    def sample_catalog(self) -> FMCatalog:
        """Create a sample catalog for testing."""
        fms = {
            "ISU_DB_EANL_SINGLE": FunctionModuleEntry(
                name="ISU_DB_EANL_SINGLE",
                description="Read installation data",
                area="ISU",
                import_params=[
                    FMParameter(
                        name="X_ANLAGE",
                        typing="LIKE",
                        reference_type="EANLH-ANLAGE",
                        description="Anlage",
                    ),
                ],
            ),
            "FKK_CREATE_DOC": FunctionModuleEntry(
                name="FKK_CREATE_DOC",
                description="Create FI-CA document",
                area="FICA",
                import_params=[
                    FMParameter(
                        name="I_FKKKO",
                        typing="LIKE",
                        reference_type="FKKKO",
                        description="Belegkopf",
                    ),
                ],
            ),
            "BAPI_ISUPARTNER_CREATEFROMDATA": FunctionModuleEntry(
                name="BAPI_ISUPARTNER_CREATEFROMDATA",
                description="Create business partner",
                area="ISU",
                import_params=[
                    FMParameter(
                        name="PARTNER",
                        typing="LIKE",
                        reference_type="BAPIBPPARA-PARTNER",
                        description="Nummer des Geschaeftspartners",
                    ),
                ],
            ),
        }
        return FMCatalog(function_modules=fms, total_count=len(fms))

    def test_exact_name_match(self, sample_catalog: FMCatalog) -> None:
        """Test exact FM name match."""
        results = search_function_modules(sample_catalog, "FKK_CREATE_DOC")
        assert len(results) >= 1
        assert results[0].fm.name == "FKK_CREATE_DOC"
        assert results[0].score == 100

    def test_name_prefix_match(self, sample_catalog: FMCatalog) -> None:
        """Test FM name prefix match."""
        results = search_function_modules(sample_catalog, "ISU_DB")
        assert len(results) >= 1
        assert results[0].fm.name == "ISU_DB_EANL_SINGLE"
        assert results[0].score == 80

    def test_parameter_description_search_anlage(self, sample_catalog: FMCatalog) -> None:
        """Test searching by parameter description 'Anlage'."""
        results = search_function_modules(sample_catalog, "anlage")
        assert len(results) >= 1
        fm_names = [r.fm.name for r in results]
        assert "ISU_DB_EANL_SINGLE" in fm_names

    def test_empty_query_returns_empty(self, sample_catalog: FMCatalog) -> None:
        """Test that empty query returns empty results."""
        assert search_function_modules(sample_catalog, "") == []

    def test_case_insensitive(self, sample_catalog: FMCatalog) -> None:
        """Test that search is case-insensitive."""
        results_lower = search_function_modules(sample_catalog, "fkk_create_doc")
        results_upper = search_function_modules(sample_catalog, "FKK_CREATE_DOC")
        assert len(results_lower) == len(results_upper)


class TestFMCatalogSearchIntegration:
    """Integration tests using real catalog data with IS-U search terms."""

    def test_search_anlage_finds_relevant_fms(self) -> None:
        """Test searching for 'anlage' (installation) finds relevant FMs."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("FM catalog not available")

        results = search_function_modules(catalog, "anlage", limit=20)
        assert len(results) > 0
        # Check that results are relevant
        for r in results[:5]:
            has_anlage = (
                "ANLAGE" in r.fm.name.upper()
                or "ANLAGE" in r.fm.description.upper()
                or any("ANLAGE" in p.description.upper() for p in r.fm.all_params())
                or any("ANLAGE" in p.reference_type.upper() for p in r.fm.all_params())
            )
            assert has_anlage, f"FM {r.fm.name} doesn't seem related to anlage"

    def test_search_vertrag_finds_contract_fms(self) -> None:
        """Test searching for 'vertrag' (contract) finds relevant FMs."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("FM catalog not available")

        results = search_function_modules(catalog, "vertrag", limit=20)
        assert len(results) > 0

    def test_search_partner_finds_business_partner_fms(self) -> None:
        """Test searching for 'partner' finds business partner FMs."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("FM catalog not available")

        results = search_function_modules(catalog, "partner", limit=20)
        assert len(results) > 0
        fm_names = [r.fm.name for r in results]
        has_partner_fm = any("PARTNER" in name for name in fm_names)
        assert has_partner_fm, "No partner-related FMs found"

    def test_search_fkk_finds_fica_fms(self) -> None:
        """Test searching for FKK prefix finds FI-CA FMs."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("FM catalog not available")

        results = search_function_modules(catalog, "FKK", limit=50)
        assert len(results) > 10
        for r in results:
            assert "FKK" in r.fm.name


class TestFuzzyFMSearch:
    """Tests for fuzzy matching in FM search (GH-250)."""

    def test_fuzzy_finds_fm_by_partial_description(self) -> None:
        from sapguimcp.fmcatalog.models import FMCatalog, FunctionModuleEntry
        from sapguimcp.fmcatalog.search import search_function_modules

        fm = FunctionModuleEntry(name="Z_TEST_FM", description="Rechnungsstellung durchführen")
        catalog = FMCatalog(function_modules={"Z_TEST_FM": fm}, source_system="test", language="DE")
        results = search_function_modules(catalog, "Rechnungen", limit=5)
        assert len(results) > 0
        assert results[0].match_reason == "fuzzy description"
