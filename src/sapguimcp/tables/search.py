"""Table catalog search implementation - RUNTIME USE.

===========================================================================
This module is for RUNTIME use by the search_tables MCP tool.
It searches the bundled tables.json - no SAP session required.

For DEVELOPMENT (building/updating the catalog), see scraper.py.
===========================================================================

SCORING ALGORITHM:
- Table name exact match: 100
- Table name prefix match: 80
- Table name contains: 60
- Table description contains: 50
- Field name exact match: 40
- Field name contains: 30
- Field description contains: 20
- Fuzzy match on description (>= 50): 5-14
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

from sapguimcp.tables.models import TableCatalog, TableInfo


@dataclass
class TableSearchResult:
    """A single search result with relevance score."""

    table: TableInfo
    score: float
    match_reason: str


def search_tables(  # pylint: disable=too-many-branches
    catalog: TableCatalog,
    query: str,
    include_fields: bool = True,
    limit: int = 10,
) -> list[TableSearchResult]:
    """Search for tables matching a query.

    Args:
        catalog: The table catalog to search
        query: Search query (table name, description, or field name/description)
        include_fields: Also search field names and descriptions
        limit: Maximum results to return

    Returns:
        List of TableSearchResult sorted by score (highest first)
    """
    if not query or not query.strip():
        return []

    query_upper = query.strip().upper()
    results: list[TableSearchResult] = []

    for table in catalog.tables.values():
        score = 0.0
        match_reason = ""

        table_name_upper = table.name.upper()
        desc_upper = table.description.upper()

        # Table name matching
        if table_name_upper == query_upper:
            score = 100
            match_reason = "table name exact"
        elif table_name_upper.startswith(query_upper):
            score = 80
            match_reason = "table name prefix"
        elif query_upper in table_name_upper:
            score = 60
            match_reason = "table name contains"
        # Table description matching
        elif query_upper in desc_upper:
            score = 50
            match_reason = "table description contains"

        # Field matching (only if include_fields and no table-level match yet)
        if include_fields and score == 0:
            for field in table.fields:
                field_name_upper = field.name.upper()
                field_desc_upper = field.description.upper()

                if field_name_upper == query_upper:
                    score = 40
                    match_reason = f"field {field.name} exact"
                    break
                if query_upper in field_name_upper:
                    score = 30
                    match_reason = f"field {field.name} contains"
                    break
                if query_upper in field_desc_upper:
                    score = 20
                    match_reason = f"field {field.name} description contains"
                    break

        # Fuzzy match on table description only (not fields — too noisy)
        if score == 0 and table.description:
            fuzzy_score = fuzz.WRatio(query, table.description, score_cutoff=50)
            if fuzzy_score:
                score = 5.0 + (fuzzy_score - 50) * 9.0 / 50.0
                match_reason = "fuzzy description"

        if score > 0:
            results.append(TableSearchResult(table=table, score=score, match_reason=match_reason))

    # Sort by score descending, then by table name alphabetically
    results.sort(key=lambda r: (-r.score, r.table.name))

    return results[:limit]
