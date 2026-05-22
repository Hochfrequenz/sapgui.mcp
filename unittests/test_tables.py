"""Unit tests for the table catalog module."""

import json
import tempfile
from pathlib import Path

import pytest

from sapguimcp.tables.models import TableCatalog, TableField, TableInfo


class TestTableField:
    """Tests for TableField model."""

    def test_numeric_field_has_decimals(self) -> None:
        """Numeric field has decimals set."""
        field = TableField(
            name="NETWR",
            description="Net value",
            data_type="CURR",
            length=15,
            decimals=2,
            is_key=False,
        )
        assert field.decimals == 2

    def test_non_numeric_field_decimals_none(self) -> None:
        """Non-numeric field has decimals=None."""
        field = TableField(
            name="MATNR",
            description="Material number",
            data_type="CHAR",
            length=40,
            is_key=True,
        )
        assert field.decimals is None

    def test_field_with_all_attributes(self) -> None:
        """Field stores all attributes correctly."""
        field = TableField(
            name="MANDT",
            description="Client",
            data_type="CLNT",
            length=3,
            is_key=True,
        )
        assert field.name == "MANDT"
        assert field.description == "Client"
        assert field.data_type == "CLNT"
        assert field.length == 3
        assert field.is_key is True


class TestTableInfo:
    """Tests for TableInfo model."""

    def test_table_with_fields(self) -> None:
        """Table stores fields correctly."""
        table = TableInfo(
            name="MARA",
            description="Allgemeine Materialdaten",
            delivery_class="A",
            fields=[
                TableField(name="MANDT", description="Client", data_type="CLNT", length=3, is_key=True),
                TableField(name="MATNR", description="Material", data_type="CHAR", length=40, is_key=True),
            ],
        )
        assert table.name == "MARA"
        assert table.description == "Allgemeine Materialdaten"
        assert table.delivery_class == "A"
        assert len(table.fields) == 2

    def test_table_default_empty_fields(self) -> None:
        """Table defaults to empty fields list."""
        table = TableInfo(
            name="TEST",
            description="Test table",
            delivery_class="C",
        )
        assert table.fields == []


class TestTableCatalog:
    """Tests for TableCatalog model."""

    def test_catalog_with_tables(self) -> None:
        """Catalog stores tables correctly."""
        catalog = TableCatalog(
            tables={
                "MARA": TableInfo(name="MARA", description="Material", delivery_class="A"),
                "MARC": TableInfo(name="MARC", description="Plant Data", delivery_class="A"),
            },
            version="2026-01-12",
            source_system="S4H",
        )
        assert len(catalog.tables) == 2
        assert "MARA" in catalog.tables
        assert catalog.version == "2026-01-12"

    def test_catalog_empty(self) -> None:
        """Empty catalog is valid."""
        catalog = TableCatalog()
        assert len(catalog.tables) == 0
        assert catalog.version == ""

    def test_get_table_found(self) -> None:
        """Get table by name (case-insensitive)."""
        catalog = TableCatalog(
            tables={"MARA": TableInfo(name="MARA", description="Material", delivery_class="A")},
        )
        assert catalog.get_table("MARA") is not None
        assert catalog.get_table("mara") is not None

    def test_get_table_not_found(self) -> None:
        """Get table returns None when not found."""
        catalog = TableCatalog()
        assert catalog.get_table("NONEXISTENT") is None


class TestTableLoader:
    """Tests for table catalog loading."""

    def test_load_catalog_from_json(self) -> None:
        """Load catalog from JSON file."""
        from sapguimcp.tables.loader import load_catalog

        catalog_data = {
            "tables": {
                "MARA": {
                    "name": "MARA",
                    "description": "Material Master",
                    "delivery_class": "A",
                    "fields": [
                        {"name": "MATNR", "description": "Material", "data_type": "CHAR", "length": 40, "is_key": True}
                    ],
                }
            },
            "version": "2026-01-12",
            "source_system": "S4H",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog_data, f)
            temp_path = Path(f.name)

        try:
            load_catalog.cache_clear()
            catalog = load_catalog(temp_path)

            assert len(catalog.tables) == 1
            assert catalog.get_table("MARA") is not None
            mara = catalog.get_table("MARA")
            assert mara is not None
            assert len(mara.fields) == 1
        finally:
            temp_path.unlink()
            load_catalog.cache_clear()

    def test_load_catalog_missing_file(self) -> None:
        """Missing file returns empty catalog."""
        from sapguimcp.tables.loader import load_catalog

        load_catalog.cache_clear()
        catalog = load_catalog(Path("/nonexistent/path.json"))
        assert len(catalog.tables) == 0

    def test_load_catalog_cached(self) -> None:
        """Same instance returned on repeated calls."""
        from sapguimcp.tables.loader import load_catalog

        load_catalog.cache_clear()

        catalog_data = {"tables": {}, "version": "test"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog_data, f)
            temp_path = Path(f.name)

        try:
            c1 = load_catalog(temp_path)
            c2 = load_catalog(temp_path)
            assert c1 is c2
        finally:
            temp_path.unlink()
            load_catalog.cache_clear()

    def test_get_catalog_never_raises(self) -> None:
        """get_catalog returns empty catalog on errors."""
        from sapguimcp.tables.loader import get_catalog, load_catalog

        load_catalog.cache_clear()
        catalog = get_catalog()
        assert isinstance(catalog, TableCatalog)


class TestTableSearch:
    """Tests for table search functionality."""

    @pytest.fixture
    def sample_catalog(self) -> TableCatalog:
        """Create a sample catalog for testing."""
        return TableCatalog(
            tables={
                "MARA": TableInfo(
                    name="MARA",
                    description="Allgemeine Materialdaten",
                    delivery_class="A",
                    fields=[
                        TableField(name="MANDT", description="Mandant", data_type="CLNT", length=3, is_key=True),
                        TableField(
                            name="MATNR", description="Materialnummer", data_type="CHAR", length=40, is_key=True
                        ),
                        TableField(name="MTART", description="Materialart", data_type="CHAR", length=4),
                    ],
                ),
                "MARC": TableInfo(
                    name="MARC",
                    description="Werksdaten zum Material",
                    delivery_class="A",
                    fields=[
                        TableField(
                            name="MATNR", description="Materialnummer", data_type="CHAR", length=40, is_key=True
                        ),
                        TableField(name="WERKS", description="Werk", data_type="CHAR", length=4, is_key=True),
                    ],
                ),
                "VBAK": TableInfo(
                    name="VBAK",
                    description="Verkaufsbeleg: Kopfdaten",
                    delivery_class="A",
                    fields=[
                        TableField(name="VBELN", description="Verkaufsbeleg", data_type="CHAR", length=10, is_key=True),
                    ],
                ),
            },
            version="test",
        )

    def test_exact_table_name_match(self, sample_catalog: TableCatalog) -> None:
        """Exact table name gets highest score."""
        from sapguimcp.tables.search import search_tables

        results = search_tables(sample_catalog, "MARA")

        assert len(results) >= 1
        assert results[0].table.name == "MARA"
        assert results[0].score == 100
        assert results[0].match_reason == "table name exact"

    def test_table_name_prefix_match(self, sample_catalog: TableCatalog) -> None:
        """Table name prefix match."""
        from sapguimcp.tables.search import search_tables

        results = search_tables(sample_catalog, "MAR")

        assert len(results) >= 2
        table_names = [r.table.name for r in results]
        assert "MARA" in table_names
        assert "MARC" in table_names

    def test_description_search(self, sample_catalog: TableCatalog) -> None:
        """Search in table description."""
        from sapguimcp.tables.search import search_tables

        results = search_tables(sample_catalog, "Material")

        assert len(results) >= 2
        table_names = [r.table.name for r in results]
        assert "MARA" in table_names
        assert "MARC" in table_names

    def test_field_name_search(self, sample_catalog: TableCatalog) -> None:
        """Search finds tables with matching field name."""
        from sapguimcp.tables.search import search_tables

        results = search_tables(sample_catalog, "MATNR", include_fields=True)

        assert len(results) >= 2
        table_names = [r.table.name for r in results]
        assert "MARA" in table_names
        assert "MARC" in table_names

    def test_field_description_search(self, sample_catalog: TableCatalog) -> None:
        """Search finds tables with matching field description."""
        from sapguimcp.tables.search import search_tables

        results = search_tables(sample_catalog, "Materialnummer", include_fields=True)

        assert len(results) >= 2

    def test_field_search_disabled(self, sample_catalog: TableCatalog) -> None:
        """include_fields=False skips field matching."""
        from sapguimcp.tables.search import search_tables

        results = search_tables(sample_catalog, "MATNR", include_fields=False)

        # MATNR is only a field name, not a table name or description
        # Should return empty or only tables where MATNR appears in name/description
        for r in results:
            assert "MATNR" in r.table.name.upper() or "MATNR" in r.table.description.upper()

    def test_limit_results(self, sample_catalog: TableCatalog) -> None:
        """Limit parameter works."""
        from sapguimcp.tables.search import search_tables

        results = search_tables(sample_catalog, "M", limit=2)
        assert len(results) <= 2

    def test_empty_query(self, sample_catalog: TableCatalog) -> None:
        """Empty query returns no results."""
        from sapguimcp.tables.search import search_tables

        assert search_tables(sample_catalog, "") == []
        assert search_tables(sample_catalog, "   ") == []

    def test_case_insensitive(self, sample_catalog: TableCatalog) -> None:
        """Search is case-insensitive."""
        from sapguimcp.tables.search import search_tables

        results_upper = search_tables(sample_catalog, "MARA")
        results_lower = search_tables(sample_catalog, "mara")

        assert len(results_upper) == len(results_lower)


class TestTableTools:
    """Tests for table MCP tool registration."""

    def test_register_table_tools(self) -> None:
        """Table tools register without error."""
        from fastmcp import FastMCP

        from sapguimcp.tools.table_tools import register_table_tools

        mcp = FastMCP("test")
        register_table_tools(mcp)

        # Verify tool was registered
        import asyncio

        tool_names = [t.name for t in asyncio.run(mcp.list_tools())]
        assert "search_tables" in tool_names


class TestIntegration:
    """Integration tests using bundled catalog."""

    def test_search_euitrans_returns_table(self) -> None:
        """Integration: search finds EUITRANS table in bundled catalog."""
        from sapguimcp.tables.loader import get_catalog, load_catalog
        from sapguimcp.tables.search import search_tables

        load_catalog.cache_clear()
        catalog = get_catalog()

        # Skip if catalog is empty (not yet populated)
        if len(catalog.tables) == 0:
            pytest.skip("Table catalog not populated yet")

        results = search_tables(catalog, "EUITRANS", include_fields=False, limit=5)

        assert len(results) > 0
        table = results[0].table
        score = results[0].score
        assert table.name == "EUITRANS"
        assert score >= 80  # Exact or prefix match
        assert len(table.fields) > 0


class TestFuzzyTableSearch:
    """Tests for fuzzy matching in table search (GH-250)."""

    def test_fuzzy_finds_table_by_partial_description(self) -> None:
        from sapguimcp.tables.search import search_tables

        table = TableInfo(
            name="T000",
            description="Mandanten in der Datenbank",
            delivery_class="S",
            fields=[TableField(name="MANDT", description="Mandant", data_type="CLNT", length=3)],
        )
        catalog = TableCatalog(tables={"T000": table}, source_system="test")
        results = search_tables(catalog, "Mandanten Datenbank", limit=5)
        assert len(results) > 0
        assert results[0].match_reason == "fuzzy description"
