"""
Class catalog search tool for SAP.

This module provides an MCP tool to search for SAP classes by keyword
or description. It helps Claude find relevant classes for IS-U/FI-CA workflows.
"""

import logging

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from sapguimcp.classcatalog.loader import get_catalog
from sapguimcp.classcatalog.search import search_classes as do_search

logger = logging.getLogger(__name__)

__all__ = ["register_class_tools"]


# =============================================================================
# Result Models
# =============================================================================


class ClassSearchResultItem(BaseModel):
    """A single class from search results."""

    name: str = Field(description="Class name (e.g., 'CL_ISU_CONTRACT')")
    description: str = Field(description="Class description")
    object_type: str = Field(description="Object type: 'class' or 'interface'")
    score: float = Field(description="Relevance score (0-100)")
    match_reason: str = Field(description="Why this class matched")


class ClassSearchResponse(BaseModel):
    """Response from class search."""

    success: bool = Field(default=True)
    query: str = Field(description="The search query used")
    total_results: int = Field(description="Number of results found")
    total_in_catalog: int = Field(description="Total classes in catalog")
    results: list[ClassSearchResultItem] = Field(description="Matching classes")
    hint: str | None = Field(default=None, description="Guidance when no results")


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_class_tools(mcp: FastMCP) -> None:
    """Register class catalog tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Search for SAP classes by name or description. "
            "Use this when the user asks things like:\n"
            "- 'What class handles installations?'\n"
            "- 'Find classes for IS-U contracts'\n"
            "- 'Which class works with devices?'\n"
            "- 'Show me FI-CA classes'\n\n"
            "The catalog contains IS-U and FI-CA classes. "
            "Returns matching classes with relevance scores."
        ),
    )
    async def search_classes(
        query: str,
        limit: int = 10,
    ) -> ClassSearchResponse:
        """
        Search for SAP classes by keyword.

        Args:
            query: Search query - can be a class name (e.g., 'CL_ISU_CONTRACT'),
                   partial name (e.g., 'CL_ISU_'), or description keywords
                   (e.g., 'installation', 'contract', 'device')
            limit: Maximum results to return (default 10, max 50)

        Returns:
            ClassSearchResponse with matching classes
        """
        limit = min(max(1, limit), 50)

        catalog = get_catalog()
        search_results = do_search(catalog, query, limit=limit)

        results = [
            ClassSearchResultItem(
                name=r.cls.name,
                description=r.cls.description,
                object_type=r.cls.object_type,
                score=r.score,
                match_reason=r.match_reason,
            )
            for r in search_results
        ]

        hint = None
        if not results:
            hint = f"No classes found for '{query}'. Try broader keywords or check spelling."

        return ClassSearchResponse(
            success=True,
            query=query,
            total_results=len(results),
            total_in_catalog=catalog.total_count,
            results=results,
            hint=hint,
        )
