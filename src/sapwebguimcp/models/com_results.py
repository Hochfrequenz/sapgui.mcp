"""Pydantic models for COM evaluate tool results."""

from pydantic import Field

from sapwebguimcp.models.base import ToolResult


class ComOperation(ToolResult):
    """Result of a single COM operation."""

    element_id: str = Field(default="", description="SAP GUI element path")
    action: str = Field(default="", description="Action performed: get, set, or call")
    property_or_method: str = Field(default="", description="Property or method name")
    result: str | None = Field(default=None, description="JSON-serialized result value")


class ComEvaluateResult(ToolResult):
    """Result from sap_com_evaluate tool. Supports batch operations."""

    operations: list[ComOperation] = Field(default_factory=list, description="Results of each operation")
