"""SE11 (ABAP Dictionary) lookup result models."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

# Literal type for object types
SE11ObjectType = Literal["table", "structure"]


class SE11Field(BaseModel):
    """A single field/column in a table or structure."""

    name: str = Field(description="Field name (e.g., 'MATNR')")
    datatype: str = Field(description="ABAP data type (e.g., 'CHAR', 'NUMC', 'CLNT', 'DATS')")
    length: int = Field(description="Field length")
    decimals: int | None = Field(default=None, description="Decimal places (None for non-numeric)")
    description: str = Field(description="Short text / field description")
    is_key: bool = Field(default=False, description="True if this is a key field")


class SE11Entry(BaseModel):
    """Successful metadata lookup for a single table or structure."""

    name: str = Field(description="Table or structure name (e.g., 'MARA', 'BAPIRET2')")
    description: str = Field(description="Short description of the table/structure")
    object_type: SE11ObjectType = Field(description="Object type: 'table' or 'structure'")
    fields: list[SE11Field] = Field(description="All fields/columns with metadata")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp when this data was retrieved")


class SE11Error(BaseModel):
    """Failed metadata lookup for a single table or structure."""

    name: str = Field(description="Requested table/structure name")
    object_type: SE11ObjectType = Field(description="Requested object type")
    error: str = Field(description="Error message (e.g., 'Object not found in ABAP Dictionary')")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp of the failed lookup attempt")


class SE11Result(ToolResult):
    """Result of SE11 lookup - may contain both successes and failures.

    When looking up multiple objects, some may succeed while others fail.
    Check both `entries` and `errors` lists.

    The overall `success` field is True if at least one lookup succeeded,
    False only if ALL lookups failed.
    """

    entries: list[SE11Entry] = Field(default_factory=list, description="Successfully retrieved objects")
    errors: list[SE11Error] = Field(default_factory=list, description="Failed lookups with error details")

    @property
    def total_requested(self) -> int:
        """Total number of objects that were requested."""
        return len(self.entries) + len(self.errors)

    @property
    def all_succeeded(self) -> bool:
        """True if all requested objects were found."""
        return len(self.errors) == 0 and len(self.entries) > 0


class SE11FileSummary(ToolResult):
    """Summary result when SE11 output is written to file (for large result sets).

    When looking up many objects (>10), use the output_file parameter to write
    full results to a JSON file. This model is returned as a summary.
    """

    output_file: str = Field(description="Path to JSON file containing full SE11Result")
    total_requested: int = Field(description="Total number of objects requested")
    successful: int = Field(description="Number of successful lookups")
    failed: int = Field(description="Number of failed lookups")
    sample_entries: list[str] = Field(
        default_factory=list, description="Sample of successfully retrieved object names (first 5)"
    )
    sample_errors: list[str] = Field(default_factory=list, description="Sample of failed object names (first 5)")
