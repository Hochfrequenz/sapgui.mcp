"""Internal models for middleware functionality."""

from datetime import datetime, timedelta, timezone

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from sapguimcp.models.base import TCode


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


class SapIdentity(BaseModel):
    """SAP login identity for log correlation."""

    sap_user: str
    sap_host: str
    sap_mandant: str


class SessionStats(BaseModel):
    """Accumulated statistics for a session.

    Tracks tool call sequences, timing, and transaction round times.

    Transaction Round Tracking:
        For repetitive SAP tasks (e.g., processing multiple documents), calling
        the same transaction again indicates a new "round" or iteration. The
        `last_transaction_*` fields track when each transaction was last called,
        allowing measurement of round duration (time between consecutive calls
        to the same transaction). This helps identify:
        - How long each iteration takes
        - Performance patterns across repetitive tasks
        - Bottlenecks in multi-step workflows
    """

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    tool_calls: list[ToolCall] = Field(default_factory=list)
    total_duration: timedelta = Field(default_factory=timedelta)
    call_count: int = Field(default=0)

    # SAP identity (populated after login)
    sap_identity: SapIdentity | None = Field(
        default=None,
        description="SAP identity captured after login, injected into log extra by middleware",
    )

    # Transaction round tracking
    last_transaction: TCode | None = Field(
        default=None,
        description="Last transaction code called (always uppercase via TCode type)",
    )
    last_transaction_time: AwareDatetime | None = Field(
        default=None,
        description="UTC timestamp when last_transaction was called",
    )
    round_start_index: int | None = Field(
        default=None,
        description="Index into tool_calls where current round started, None if no round yet",
    )

    def format_sequence(self, last_n: int = 20, current_round_only: bool = False) -> str:
        """Format last N calls as a sequence diagram.

        Args:
            last_n: Maximum number of calls to show
            current_round_only: If True, only show calls since round_start_index
        """
        if not self.tool_calls:
            return ""

        if current_round_only and self.round_start_index is not None:
            # Only show calls within current round
            calls = self.tool_calls[self.round_start_index :]
            if not calls:
                return ""
            if len(calls) <= last_n:
                return " -> ".join(tc.format_short() for tc in calls)
            omitted = len(calls) - last_n
            return f"...({omitted} others) -> " + " -> ".join(tc.format_short() for tc in calls[-last_n:])

        # Show last N calls regardless of round
        total = len(self.tool_calls)
        if total <= last_n:
            return " -> ".join(tc.format_short() for tc in self.tool_calls)
        omitted = total - last_n
        calls = self.tool_calls[-last_n:]
        return f"...({omitted} others) -> " + " -> ".join(tc.format_short() for tc in calls)

    def record_transaction(self, tcode: str) -> timedelta | None:
        """Record a transaction call and return round duration if same transaction.

        Args:
            tcode: Transaction code (normalized to uppercase for comparison)

        Returns:
            Duration since last call to the same transaction (round time),
            or None if this is the first call or a different transaction.

        Side effects:
            When a new round starts (same transaction called again), resets
            round_start_index to current position for round-scoped sequence display.
        """
        tcode_upper = tcode.upper()
        now = datetime.now(timezone.utc)
        round_duration: timedelta | None = None

        if self.last_transaction == tcode_upper and self.last_transaction_time:
            # Same transaction called again - this completes a "round"
            round_duration = now - self.last_transaction_time
            # Reset round start to current position (before this call is appended)
            self.round_start_index = len(self.tool_calls)

        # Update tracking
        self.last_transaction = tcode_upper
        self.last_transaction_time = now

        return round_duration
