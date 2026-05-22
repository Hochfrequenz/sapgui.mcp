"""Function module catalog search - RUNTIME USE.

SCORING ALGORITHM:
- FM name exact match: 100
- FM name prefix match: 80
- FM name contains: 60
- FM description contains: 50
- Parameter name contains: 40
- Parameter description contains: 30
- Parameter reference_type contains: 20
- Fuzzy match on description (>= 50): 5-14
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

from sapguimcp.fmcatalog.models import FMCatalog, FunctionModuleEntry


@dataclass
class FMSearchResult:
    """A single search result with relevance score."""

    fm: FunctionModuleEntry
    score: float
    match_reason: str


def search_function_modules(  # pylint: disable=too-many-locals,too-many-branches
    catalog: FMCatalog,
    query: str,
    include_params: bool = True,
    limit: int = 10,
) -> list[FMSearchResult]:
    """Search for function modules matching a query.

    Args:
        catalog: The FM catalog to search
        query: Search query (FM name, description, or parameter info)
        include_params: Also search parameter names and descriptions
        limit: Maximum results to return

    Returns:
        List of FMSearchResult sorted by score (highest first)
    """
    if not query or not query.strip():
        return []

    query_upper = query.strip().upper()
    results: list[FMSearchResult] = []

    for fm in catalog.function_modules.values():
        score = 0.0
        match_reason = ""

        fm_name_upper = fm.name.upper()
        desc_upper = fm.description.upper()

        # FM name matching
        if fm_name_upper == query_upper:
            score = 100
            match_reason = "name exact"
        elif fm_name_upper.startswith(query_upper):
            score = 80
            match_reason = "name prefix"
        elif query_upper in fm_name_upper:
            score = 60
            match_reason = "name contains"
        # FM description matching
        elif query_upper in desc_upper:
            score = 50
            match_reason = "description contains"

        # Parameter matching (only if include_params and no FM-level match yet)
        if include_params and score == 0:
            for param in fm.all_params():
                param_name_upper = param.name.upper()
                param_desc_upper = param.description.upper()
                param_ref_upper = param.reference_type.upper()

                if query_upper in param_name_upper:
                    score = 40
                    match_reason = f"param {param.name} name"
                    break
                if query_upper in param_desc_upper:
                    score = 30
                    match_reason = f"param {param.name} description"
                    break
                if query_upper in param_ref_upper:
                    score = 20
                    match_reason = f"param {param.name} reference_type"
                    break

        # Fuzzy match on description
        if score == 0 and fm.description:
            fuzzy_score = fuzz.WRatio(query, fm.description, score_cutoff=50)
            if fuzzy_score:
                score = 5.0 + (fuzzy_score - 50) * 9.0 / 50.0
                match_reason = "fuzzy description"

        if score > 0:
            results.append(FMSearchResult(fm=fm, score=score, match_reason=match_reason))

    # Sort by score descending, then by FM name alphabetically
    results.sort(key=lambda r: (-r.score, r.fm.name))

    return results[:limit]
