"""Internal models for middleware functionality."""

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field


def _serialize_timedelta(td: timedelta) -> str:
    """Serialize timedelta to ISO 8601 duration format (e.g., PT1H30M45S)."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    microseconds = td.microseconds

    parts = ["PT"]
    if hours:
        parts.append(f"{hours}H")
    if minutes:
        parts.append(f"{minutes}M")
    if seconds or microseconds:
        if microseconds:
            parts.append(f"{seconds}.{microseconds:06d}S")
        else:
            parts.append(f"{seconds}S")

    return "".join(parts) if len(parts) > 1 else "PT0S"


class SessionStats(BaseModel):
    """Accumulated statistics for a session."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool_calls: list[str] = Field(default_factory=list)
    total_duration: timedelta = Field(default_factory=timedelta)
    call_count: int = Field(default=0)
