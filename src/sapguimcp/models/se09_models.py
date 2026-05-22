"""
Pydantic models for SE09 (Transport Organizer) lookup tool.

These models represent transport request metadata retrieved from SE09,
including requests, tasks, and optionally transported objects.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "TransportListResult",
    "TransportRequest",
    "TransportTask",
]


class TransportObject(BaseModel):
    """An object within a transport task."""

    pgmid: str = Field(description="Program ID (e.g., R3TR, LIMU)")
    object_type: str = Field(description="Object type (e.g., PROG, FUNC, TABL, CLAS)")
    object_name: str = Field(description="Object name")


class TransportTask(BaseModel):
    """A task within a transport request."""

    task_number: str = Field(description="Task number (e.g., DEVK900123)")
    description: str = Field(default="", description="Task description")
    owner: str = Field(default="", description="Task owner (username)")
    status: str = Field(default="", description="Status: Modifiable or Released")
    task_type: str = Field(default="", description="Task type (e.g., Development/Correction, Repair)")
    objects: list[TransportObject] = Field(
        default_factory=list,
        description="Objects in this task (empty unless include_objects=True)",
    )


class TransportRequest(BaseModel):
    """A transport request from SE09."""

    request_number: str = Field(description="Request number (e.g., DEVK900100)")
    description: str = Field(default="", description="Request description")
    owner: str = Field(default="", description="Request owner (username)")
    status: str = Field(default="", description="Status: Modifiable or Released")
    request_type: str = Field(default="", description="Request type (e.g., Workbench, Customizing)")
    target_system: str = Field(default="", description="Target system (e.g., QAS)")
    date: str | None = Field(default=None, description="Last changed date")
    tasks: list[TransportTask] = Field(default_factory=list, description="Tasks in this request")


class TransportListResult(ToolResult):
    """Result of SE09 transport lookup."""

    requests: list[TransportRequest] = Field(default_factory=list, description="Transport requests found")
    request_count: int = Field(default=0, description="Number of requests returned")
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")
