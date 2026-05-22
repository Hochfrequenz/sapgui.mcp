"""SE93 (Transaction Maintenance) lookup result models."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

# Transaction types supported by SE93
SE93TransactionType = Literal["dialog", "report"]


class SE93Entry(BaseModel):
    """Transaction metadata from SE93."""

    tcode: str = Field(description="Transaction code (e.g., 'VA01', 'SE38')")
    description: str = Field(description="Transaction text/description")
    transaction_type: SE93TransactionType = Field(description="Type: 'dialog' or 'report'")
    package: str = Field(description="Development package (e.g., 'VA', 'SEDT')")
    program: str = Field(description="Program/report name (e.g., 'SAPMV45A', 'RSABAPPROGRAM')")

    # Dialog transaction specific
    screen_number: str | None = Field(default=None, description="Dynpro/screen number (dialog transactions)")

    # Report transaction specific
    selection_screen: str | None = Field(default=None, description="Selection screen number (report transactions)")
    start_variant: str | None = Field(default=None, description="Start with variant (report transactions)")

    # Authorization
    authorization_object: str | None = Field(default=None, description="Authorization object (e.g., 'S_DEVELOP')")

    # GUI capabilities
    gui_html: bool = Field(default=False, description="Supports SAP GUI for HTML")
    gui_java: bool = Field(default=False, description="Supports SAP GUI for Java")
    gui_windows: bool = Field(default=False, description="Supports SAP GUI for Windows")

    retrieved_at: AwareDatetime = Field(description="UTC timestamp when this data was retrieved")


class SE93Error(BaseModel):
    """Failed transaction lookup."""

    tcode: str = Field(description="Requested transaction code")
    error: str = Field(description="Error message")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp of the failed lookup attempt")


class SE93Result(ToolResult):
    """Result of SE93 lookup - may contain both successes and failures.

    When looking up multiple transactions, some may succeed while others fail.
    Check both `entries` and `errors` lists.
    """

    entries: list[SE93Entry] = Field(default_factory=list, description="Successfully retrieved transactions")
    errors: list[SE93Error] = Field(default_factory=list, description="Failed lookups with error details")

    @property
    def total_requested(self) -> int:
        """Total number of transactions that were requested."""
        return len(self.entries) + len(self.errors)

    @property
    def all_succeeded(self) -> bool:
        """True if all requested transactions were found."""
        return len(self.errors) == 0 and len(self.entries) > 0


class SE93FileSummary(ToolResult):
    """Summary result when SE93 output is written to file."""

    output_file: str = Field(description="Path to JSON file containing full SE93Result")
    total_requested: int = Field(description="Total number of transactions requested")
    successful: int = Field(description="Number of successful lookups")
    failed: int = Field(description="Number of failed lookups")
    sample_entries: list[str] = Field(
        default_factory=list, description="Sample of successfully retrieved tcodes (first 5)"
    )
    sample_errors: list[str] = Field(default_factory=list, description="Sample of failed tcodes (first 5)")
