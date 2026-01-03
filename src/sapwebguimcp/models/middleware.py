"""Internal models for middleware functionality."""

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    """A single tool call with arguments."""

    name: str = Field(description="Tool name")
    args: dict[str, str] = Field(default_factory=dict, description="Formatted arguments")
    success: bool = Field(default=True)

    def format_short(self, max_arg_len: int = 30) -> str:
        """Format as tool(arg1=val1, arg2=val2)."""
        if not self.args:
            return f"{self.name}()"

        formatted_args = []
        for k, v in self.args.items():  # pylint:disable=no-member
            v_str = str(v)
            if len(v_str) > max_arg_len:
                v_str = v_str[: max_arg_len - 3] + "..."
            formatted_args.append(f"{k}={v_str}")

        suffix = "" if self.success else "[FAIL]"
        return f"{self.name}({', '.join(formatted_args)}){suffix}"


class SessionStats(BaseModel):
    """Accumulated statistics for a session."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    tool_calls: list[ToolCall] = Field(default_factory=list)
    total_duration: timedelta = Field(default_factory=timedelta)
    call_count: int = Field(default=0)

    def format_sequence(self, last_n: int = 5) -> str:
        """Format last N calls as a sequence diagram."""
        if not self.tool_calls:
            return ""
        calls = self.tool_calls[-last_n:]
        return " -> ".join(tc.format_short() for tc in calls)
