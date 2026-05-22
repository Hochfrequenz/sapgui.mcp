"""
Pydantic models for SE37 (Function Builder) lookup tool.

These models represent function module metadata retrieved from SE37,
including import/export/tables parameters and exceptions.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "SE37Parameter",
    "SE37Exception",
    "SE37Entry",
    "SE37Error",
    "SE37Result",
    "SE37FileSummary",
]

# Parameter direction/category
SE37ParameterCategory = Literal["import", "export", "changing", "tables"]

# Typing method (how the type is defined)
SE37TypingMethod = Literal["LIKE", "TYPE"]


class SE37Parameter(BaseModel):
    """A function module parameter (import, export, changing, or tables)."""

    name: str = Field(description="Parameter name")
    category: SE37ParameterCategory = Field(description="Parameter category")
    typing: SE37TypingMethod = Field(description="Typing method (LIKE or TYPE)")
    reference_type: str = Field(description="Reference type (data element, structure, etc.)")
    default_value: str | None = Field(default=None, description="Default value (import parameters)")
    optional: bool = Field(default=False, description="Whether parameter is optional")
    pass_by_value: bool = Field(default=False, description="Whether passed by value (VALUE)")
    description: str = Field(default="", description="Short text description")


class SE37Exception(BaseModel):
    """A function module exception."""

    name: str = Field(description="Exception name")
    description: str = Field(default="", description="Short text description")


class SE37Entry(BaseModel):
    """Function module metadata from SE37."""

    function_module: str = Field(description="Function module name")
    function_group: str | None = Field(default=None, description="Function group name")
    description: str = Field(default="", description="Short text description")
    package: str | None = Field(default=None, description="Development package")
    import_parameters: list[SE37Parameter] = Field(default_factory=list, description="Import parameters")
    export_parameters: list[SE37Parameter] = Field(default_factory=list, description="Export parameters")
    changing_parameters: list[SE37Parameter] = Field(default_factory=list, description="Changing parameters")
    tables_parameters: list[SE37Parameter] = Field(default_factory=list, description="Tables parameters")
    exceptions: list[SE37Exception] = Field(default_factory=list, description="Exceptions")
    is_rfc_enabled: bool = Field(default=False, description="Whether function module is RFC-enabled")
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")


class SE37Error(BaseModel):
    """Error response when function module lookup fails."""

    function_module: str = Field(description="Function module name that was looked up")
    error: str = Field(description="Error message")
    retrieved_at: AwareDatetime = Field(description="When the lookup was attempted")


class SE37Result(ToolResult):
    """Result of SE37 function module lookup."""

    entries: list[SE37Entry] = Field(default_factory=list, description="Successfully retrieved entries")
    errors: list[SE37Error] = Field(default_factory=list, description="Failed lookups")


class SE37FileSummary(ToolResult):
    """Summary returned when results are written to file."""

    output_file: str = Field(description="Path to the output file")
    total_requested: int = Field(description="Number of function modules requested")
    successful: int = Field(description="Number of successful lookups")
    failed: int = Field(description="Number of failed lookups")
    sample_entries: list[str] = Field(default_factory=list, description="Sample of successful FM names")
    sample_errors: list[str] = Field(default_factory=list, description="Sample of failed FM names")
