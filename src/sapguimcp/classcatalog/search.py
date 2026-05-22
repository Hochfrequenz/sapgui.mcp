"""Class catalog search - RUNTIME USE.

SCORING ALGORITHM:
- Class name exact match: 100
- Class name prefix match: 80
- Class name contains: 60
- Class description contains: 50
- Fuzzy match on description (>= 50): 5-14
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

from sapguimcp.classcatalog.models import ClassCatalog, ClassEntry


@dataclass
class ClassSearchResult:
    """A single search result with relevance score."""

    cls: ClassEntry
    score: float
    match_reason: str


def search_classes(
    catalog: ClassCatalog,
    query: str,
    limit: int = 10,
) -> list[ClassSearchResult]:
    """Search for classes matching a query.

    Args:
        catalog: The class catalog to search
        query: Search query (class name or description)
        limit: Maximum results to return

    Returns:
        List of ClassSearchResult sorted by score (highest first)
    """
    if not query or not query.strip():
        return []

    query_upper = query.strip().upper()
    results: list[ClassSearchResult] = []

    for cls in catalog.classes.values():
        score = 0.0
        match_reason = ""

        cls_name_upper = cls.name.upper()
        desc_upper = cls.description.upper()

        # Class name matching
        if cls_name_upper == query_upper:
            score = 100
            match_reason = "name exact"
        elif cls_name_upper.startswith(query_upper):
            score = 80
            match_reason = "name prefix"
        elif query_upper in cls_name_upper:
            score = 60
            match_reason = "name contains"
        # Class description matching
        elif query_upper in desc_upper:
            score = 50
            match_reason = "description contains"

        # Fuzzy match on description
        if score == 0 and cls.description:
            fuzzy_score = fuzz.WRatio(query, cls.description, score_cutoff=50)
            if fuzzy_score:
                score = 5.0 + (fuzzy_score - 50) * 9.0 / 50.0
                match_reason = "fuzzy description"

        if score > 0:
            results.append(ClassSearchResult(cls=cls, score=score, match_reason=match_reason))

    # Sort by score descending, then by class name alphabetically
    results.sort(key=lambda r: (-r.score, r.cls.name))

    return results[:limit]
