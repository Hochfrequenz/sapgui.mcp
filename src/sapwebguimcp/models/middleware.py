"""Internal models for middleware functionality."""

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field


class SessionStats(BaseModel):
    """Accumulated statistics for a session."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    tool_calls: list[str] = Field(default_factory=list)
    total_duration: timedelta = Field(default_factory=timedelta)
    call_count: int = Field(default=0)
