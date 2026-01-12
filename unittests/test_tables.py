"""Unit tests for the table catalog module."""

import pytest

from sapwebguimcp.tables.models import TableCatalog, TableField, TableInfo


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
