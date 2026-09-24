"""
Function module catalog search tool for SAP.

This module provides an MCP tool to search for SAP function modules by keyword,
description, or parameter information. It helps Claude find relevant FMs
for user tasks like IS-U/FI-CA workflows.
"""

import logging

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from sapguimcp.fmcatalog.loader import get_catalog
from sapguimcp.fmcatalog.models import FMParameter
from sapguimcp.fmcatalog.search import search_function_modules as do_search

logger = logging.getLogger(__name__)

__all__ = ["register_fm_tools"]


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_params(params: list[FMParameter]) -> list["FMParameterResult"]:
    """Convert FMParameter list to FMParameterResult list for MCP response."""
    return [
        FMParameterResult(
            name=p.name,
            typing=p.typing,
            reference_type=p.reference_type,
            optional=p.optional,
            description=p.description,
        )
        for p in params
    ]


# =============================================================================
# Result Models
# =============================================================================


class FMParameterResult(BaseModel):
    """A parameter in the search result."""

    name: str = Field(description="Parameter name")
    typing: str = Field(description="Typing method (LIKE/TYPE)")
    reference_type: str = Field(description="Reference type/structure")
    optional: bool = Field(description="Whether parameter is optional")
    description: str = Field(description="Parameter description")


class FMSearchResultItem(BaseModel):
    """A single function module from search results."""

    name: str = Field(description="Function module name (e.g., 'BAPI_USER_GET_DETAIL')")
    description: str = Field(description="Function module description")
    area: str | None = Field(default=None, description="Functional area (e.g., 'ISU', 'FICA')")
    function_group: str | None = Field(default=None, description="Function group")
    is_rfc_enabled: bool = Field(default=False, description="RFC-enabled flag")
    import_params: list[FMParameterResult] = Field(description="Import parameters")
    export_params: list[FMParameterResult] = Field(description="Export parameters")
    score: float = Field(description="Relevance score (0-100)")
    match_reason: str = Field(description="Why this FM matched")


class FMSearchResponse(BaseModel):
    """Response from function module search."""

    success: bool = Field(default=True)
    query: str = Field(description="The search query used")
    total_results: int = Field(description="Number of results found")
    total_in_catalog: int = Field(description="Total FMs in catalog")
    results: list[FMSearchResultItem] = Field(description="Matching function modules")
    hint: str | None = Field(default=None, description="Guidance when no results")


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_fm_tools(mcp: FastMCP) -> None:
    """Register function module catalog tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Search for SAP function modules by name, description, or parameter. "
            "Use this when the user asks things like:\n"
            "- 'What FM reads installation data?'\n"
            "- 'Find function modules for Anlage'\n"
            "- 'Which FMs work with business partners?'\n"
            "- 'Show me FKK function modules'\n\n"
            "The catalog contains IS-U and FI-CA function modules. "
            "Returns matching FMs with relevance scores."
        ),
    )
    async def search_function_modules(
        query: str,
        include_params: bool = True,
        limit: int = 10,
    ) -> FMSearchResponse:
        """
        Search for SAP function modules by keyword or parameter.

        Args:
            query: Search query - can be a FM name (e.g., 'BAPI_USER_GET_DETAIL'),
                   partial name (e.g., 'FKK_'), description keywords
                   (e.g., 'installation', 'Anlage'), or parameter name/type
                   (e.g., 'VKONT', 'partner')
            include_params: Also search within parameter names, descriptions,
                           and reference types (default True)
            limit: Maximum results to return (default 10, max 50)

        Returns:
            FMSearchResponse with matching function modules
        """
        limit = min(max(1, limit), 50)

        catalog = get_catalog()
        search_results = do_search(catalog, query, include_params=include_params, limit=limit)

        results = [
            FMSearchResultItem(
                name=r.fm.name,
                description=r.fm.description,
                area=r.fm.area,
                function_group=r.fm.function_group,
                is_rfc_enabled=r.fm.is_rfc_enabled,
                import_params=_convert_params(r.fm.import_params),
                export_params=_convert_params(r.fm.export_params),
                score=r.score,
                match_reason=r.match_reason,
            )
            for r in search_results
        ]

        hint = None
        if not results:
            hint = f"No function modules found for '{query}'. Try broader keywords or check spelling."

        return FMSearchResponse(
            success=True,
            query=query,
            total_results=len(results),
            total_in_catalog=catalog.total_count,
            results=results,
            hint=hint,
        )
