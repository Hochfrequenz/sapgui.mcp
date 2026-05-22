"""Unit tests for class catalog search.

Tests cover:
- Class catalog loading
- Search by name and description
- Search terms like 'ISU', 'FKK', 'installation', 'contract' for IS-U relevance
"""

import pytest

from sapguimcp.classcatalog.loader import get_catalog, load_catalog
from sapguimcp.classcatalog.models import ClassCatalog, ClassEntry
from sapguimcp.classcatalog.search import ClassSearchResult, search_classes


class TestClassCatalogLoader:
    """Tests for class catalog loading."""

    def test_load_catalog_returns_catalog(self) -> None:
        """Test that load_catalog returns a ClassCatalog."""
        load_catalog.cache_clear()
        catalog = load_catalog()
        assert isinstance(catalog, ClassCatalog)

    def test_get_catalog_never_raises(self) -> None:
        """Test that get_catalog never raises exceptions."""
        catalog = get_catalog()
        assert isinstance(catalog, ClassCatalog)

    def test_catalog_has_classes(self) -> None:
        """Test that catalog contains classes."""
        catalog = get_catalog()
        assert catalog.total_count > 0
        assert len(catalog.classes) > 0


class TestClassCatalogSearch:
    """Tests for class catalog search functionality."""

    @pytest.fixture
    def sample_catalog(self) -> ClassCatalog:
        """Create a sample catalog for testing."""
        classes = {
            "CL_ISU_CONTRACT": ClassEntry(
                name="CL_ISU_CONTRACT",
                description="IS-U Contract",
                object_type="class",
            ),
            "CL_ISU_DEVICE": ClassEntry(
                name="CL_ISU_DEVICE",
                description="IS-U Device",
                object_type="class",
            ),
            "CL_FKK_SUPPORT": ClassEntry(
                name="CL_FKK_SUPPORT",
                description="FI-CA Support Utilities",
                object_type="class",
            ),
        }
        return ClassCatalog(classes=classes, total_count=len(classes))

    def test_exact_name_match(self, sample_catalog: ClassCatalog) -> None:
        """Test exact class name match."""
        results = search_classes(sample_catalog, "CL_ISU_CONTRACT")
        assert len(results) >= 1
        assert results[0].cls.name == "CL_ISU_CONTRACT"
        assert results[0].score == 100

    def test_name_prefix_match(self, sample_catalog: ClassCatalog) -> None:
        """Test class name prefix match."""
        results = search_classes(sample_catalog, "CL_ISU")
        assert len(results) >= 1
        assert results[0].score == 80

    def test_description_search(self, sample_catalog: ClassCatalog) -> None:
        """Test searching by description."""
        results = search_classes(sample_catalog, "Device")
        assert len(results) >= 1
        cls_names = [r.cls.name for r in results]
        assert "CL_ISU_DEVICE" in cls_names

    def test_empty_query_returns_empty(self, sample_catalog: ClassCatalog) -> None:
        """Test that empty query returns empty results."""
        assert search_classes(sample_catalog, "") == []

    def test_case_insensitive(self, sample_catalog: ClassCatalog) -> None:
        """Test that search is case-insensitive."""
        results_lower = search_classes(sample_catalog, "cl_isu_contract")
        results_upper = search_classes(sample_catalog, "CL_ISU_CONTRACT")
        assert len(results_lower) == len(results_upper)


class TestClassCatalogSearchIntegration:
    """Integration tests using real catalog data."""

    def test_search_isu_finds_relevant_classes(self) -> None:
        """Test searching for 'ISU' finds relevant classes."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("Class catalog not available")

        results = search_classes(catalog, "ISU", limit=20)
        assert len(results) > 0
        # Check that results contain ISU classes
        for r in results:
            has_isu = "ISU" in r.cls.name.upper() or "ISU" in r.cls.description.upper()
            assert has_isu, f"Class {r.cls.name} doesnt seem related to ISU"

    def test_search_fkk_finds_fica_classes(self) -> None:
        """Test searching for 'FKK' finds FI-CA classes."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("Class catalog not available")

        results = search_classes(catalog, "FKK", limit=20)
        assert len(results) > 0

    def test_search_installation_finds_relevant_classes(self) -> None:
        """Test searching for 'installation' finds relevant classes."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("Class catalog not available")

        results = search_classes(catalog, "installation", limit=20)
        assert len(results) > 0
        # Should find CL_ISU_INSTALLATION
        cls_names = [r.cls.name for r in results]
        assert any("INSTALLATION" in name for name in cls_names)

    def test_search_contract_finds_relevant_classes(self) -> None:
        """Test searching for 'contract' finds relevant classes."""
        catalog = get_catalog()
        if catalog.total_count == 0:
            pytest.skip("Class catalog not available")

        results = search_classes(catalog, "contract", limit=20)
        assert len(results) > 0
        cls_names = [r.cls.name for r in results]
        assert any("CONTRACT" in name for name in cls_names)


class TestFuzzyClassSearch:
    """Tests for fuzzy matching in class search (GH-250)."""

    def test_fuzzy_finds_class_by_partial_description(self) -> None:
        from sapguimcp.classcatalog.models import ClassCatalog, ClassEntry
        from sapguimcp.classcatalog.search import search_classes

        cls = ClassEntry(name="CL_TEST", description="Vertragsverwaltung Utilities")
        catalog = ClassCatalog(classes={"CL_TEST": cls}, source_system="test", language="DE")
        results = search_classes(catalog, "Vertragsverwalter", limit=5)
        assert len(results) > 0
        assert results[0].match_reason == "fuzzy description"
