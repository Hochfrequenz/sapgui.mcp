"""
Pydantic models for SM37 (Job Log Monitoring) lookup tool.

These models represent background job metadata and job logs retrieved from SM37.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "SM37Job",
    "SM37JobLog",
    "SM37JobListResult",
]


class SM37Job(BaseModel):
    """A background job entry from SM37 job list."""

    job_name: str = Field(description="Job name")
    status: str = Field(description="Job status: Scheduled/Released/Active/Finished/Canceled")
    start_time: str | None = Field(default=None, description="Job start date/time")
    duration: str | None = Field(default=None, description="Job duration in seconds")
    user: str = Field(description="User who scheduled the job")
    mandant: str = Field(default="", description="SAP client/mandant number")


class SM37JobLog(BaseModel):
    """Job log detail for a single background job."""

    job_name: str = Field(description="Job name")
    log_lines: list[str] = Field(default_factory=list, description="Job log message lines")


class SM37JobListResult(ToolResult):
    """Result of SM37 job list lookup."""

    jobs: list[SM37Job] = Field(default_factory=list, description="List of matching jobs")
    job_count: int = Field(default=0, description="Number of jobs returned")
    filters_applied: dict[str, str] = Field(
        default_factory=dict,
        description="Summary of filters that were applied",
    )
    job_log: SM37JobLog | None = Field(
        default=None,
        description="Job log (only populated when include_log=True and exactly one job matches)",
    )
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")
