"""Transaction catalog search implementation - RUNTIME USE.

===========================================================================
This module is for RUNTIME use by the search_transactions MCP tool.
It searches the bundled transactions.json - no SAP session required.

For DEVELOPMENT (building/updating the catalog), see scraper.py.
===========================================================================

Provides keyword + fuzzy search over the transaction catalog to help
Claude find relevant SAP transactions for user tasks.

SCORING (priority order):
1. Exact tcode match: 100
2. Tcode prefix match: 80
3. Description contains all query tokens: 60
4. Description contains some query tokens: 40 * match_ratio
5. Program name contains query: 20
6. Fuzzy match on description (rapidfuzz WRatio >= 50): 10-19

KNOWN LIMITATIONS:
- LANGUAGE: Descriptions are in German. English queries won't match well.
  Re-scrape with English UI to fix.
- AREA NOT SEARCHABLE: The `area` field is only used for filtering.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from sapguimcp.catalog.models import TransactionCatalog, TransactionInfo


@dataclass
class SearchResult:
    """A single search result with relevance score."""

    transaction: TransactionInfo
    score: float
    match_type: str  # "exact_tcode", "prefix_tcode", "description", "program", "fuzzy"


def normalize_query(query: str) -> str:
    """Normalize search query for matching."""
    return query.strip().upper()


def tokenize(text: str) -> list[str]:
    """Split text into searchable tokens."""
    # Split on whitespace and punctuation, filter empty
    tokens = re.split(r"[\s\-_/.,;:]+", text.upper())
    return [t for t in tokens if t]


def search_transactions(  # pylint: disable=too-many-locals,too-many-branches
    catalog: TransactionCatalog,
    query: str,
    area: str | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    """Search for transactions matching a query.

    Matching strategy (in priority order):
    1. Exact tcode match (score: 100) - "VA01" finds VA01 only
    2. Tcode prefix match (score: 80) - "VA" finds VA01, VA02, etc.
    3. Description contains all query tokens (score: 60)
    4. Description contains some query tokens (score: 40 * match_ratio)
    5. Program name match (score: 20) - fallback for technical users

    DESIGN DECISIONS:
    - Scores are on 0-100 scale for intuitive "percentage relevance"
    - Tcode matches score highest because they're most specific
    - Description partial matches use ratio to rank "2 of 3 words" > "1 of 3"
    - Program matches are rare but useful for "show me SAPMV45A transactions"

    Args:
        catalog: The transaction catalog to search
        query: Search query (tcode or description keywords)
        area: Optional area filter (e.g., "SD-Sales", "MM-Purchasing").
              This is a FILTER, not a search field.
        limit: Maximum results to return

    Returns:
        List of SearchResult sorted by score (highest first)
    """
    if not query or not query.strip():
        return []

    query_normalized = normalize_query(query)
    query_tokens = tokenize(query)

    results: list[SearchResult] = []

    for txn in catalog.transactions:
        # Apply area filter if specified
        if area and txn.area:
            if not txn.area.upper().startswith(area.upper()):
                continue
        elif area and not txn.area:
            continue

        score = 0.0
        match_type = ""

        tcode_upper = txn.tcode.upper()

        # 1. Exact tcode match
        if tcode_upper == query_normalized:
            score = 100.0
            match_type = "exact_tcode"

        # 2. Tcode prefix match (query is start of tcode)
        elif tcode_upper.startswith(query_normalized):
            score = 80.0
            match_type = "prefix_tcode"

        # 3. Description matching
        elif txn.description and query_tokens:
            desc_upper = txn.description.upper()
            desc_tokens = tokenize(txn.description)

            # Check how many query tokens appear in description
            matches = sum(1 for qt in query_tokens if qt in desc_upper or any(qt in dt for dt in desc_tokens))
            match_ratio = matches / len(query_tokens) if query_tokens else 0

            if match_ratio == 1.0:
                # All query tokens found
                score = 60.0
                match_type = "description"
            elif match_ratio > 0:
                # Partial match
                score = 40.0 * match_ratio
                match_type = "description"

        # 4. Program name match
        if score == 0 and txn.program and query_normalized in txn.program.upper():
            score = 20.0
            match_type = "program"

        # 5. Fuzzy match on description (catches typos, partial stems, word reordering)
        if score == 0 and txn.description:
            fuzzy_score = fuzz.WRatio(query, txn.description, score_cutoff=50)
            if fuzzy_score:
                # Map rapidfuzz 50-100 range to our 10-19 score range
                score = 10.0 + (fuzzy_score - 50) * 9.0 / 50.0
                match_type = "fuzzy"

        # Only include results with positive score
        if score > 0:
            results.append(SearchResult(transaction=txn, score=score, match_type=match_type))

    # Sort by score descending, then by tcode alphabetically
    results.sort(key=lambda r: (-r.score, r.transaction.tcode))

    return results[:limit]


def search_by_area(
    catalog: TransactionCatalog,
    area: str,
    limit: int = 50,
) -> list[TransactionInfo]:
    """Get all transactions for a specific SAP area/module.

    Args:
        catalog: The transaction catalog
        area: Area prefix to filter (e.g., "SD", "MM", "FI")
        limit: Maximum results

    Returns:
        List of matching transactions
    """
    area_upper = area.upper()
    matches = []

    for txn in catalog.transactions:
        if txn.area and txn.area.upper().startswith(area_upper):
            matches.append(txn)
            if len(matches) >= limit:
                break

    return matches


def get_common_transactions(
    catalog: TransactionCatalog,
    limit: int = 20,
) -> list[TransactionInfo]:
    """Get commonly used transactions (those with short, memorable tcodes).

    Heuristic: Short tcodes (2-5 chars) without slashes are typically
    the most commonly used standard SAP transactions.

    Args:
        catalog: The transaction catalog
        limit: Maximum results

    Returns:
        List of common transactions
    """
    common = []

    for txn in catalog.transactions:
        tcode = txn.tcode
        # Filter for standard-looking tcodes
        if (
            2 <= len(tcode) <= 5
            and "/" not in tcode
            and txn.enriched  # Only include enriched (have descriptions)
            and txn.description  # Must have a description
        ):
            common.append(txn)

    # Sort by tcode length (shorter = more common), then alphabetically
    common.sort(key=lambda t: (len(t.tcode), t.tcode))

    return common[:limit]
