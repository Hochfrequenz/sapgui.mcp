"""Unit tests for Pydantic result models."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from sapguimcp.backend.webgui.models.browser_results import ClickResult, WaitResult
from sapguimcp.models import (
    CapabilitiesResult,
    DiscoveredFields,
    FieldInfo,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    SessionStatus,
    TableData,
    ToolInfo,
    ToolResult,
    TransactionResult,
)


class TestToolResultBase:
    """Tests for ToolResult base class validation."""

    def test_success_default(self) -> None:
        """Test that success defaults to True with no error."""
        result = ToolResult()
        assert result.success is True
        assert result.error is None
        assert result.is_error is False

    def test_success_with_error_fails(self) -> None:
        """Test that success=True with error raises ValidationError."""
        with pytest.raises(ValidationError, match="success=True requires error=None"):
            ToolResult(success=True, error="Some error")

    def test_failure_without_error_fails(self) -> None:
        """Test that success=False without error raises ValidationError."""
        with pytest.raises(ValidationError, match="success=False requires non-empty error"):
            ToolResult(success=False)

    def test_failure_with_empty_error_fails(self) -> None:
        """Test that success=False with empty error raises ValidationError."""
        with pytest.raises(ValidationError, match="success=False requires non-empty error"):
            ToolResult(success=False, error="")

    def test_failure_factory_method(self) -> None:
        """Test the failure() class method."""
        result = ToolResult.failure("Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.is_error is True

    def test_extra_fields_allowed(self) -> None:
        """Test that extra fields are allowed by ConfigDict."""
        result = ToolResult(extra_field="extra_value", another=123)
        assert result.success is True
        assert result.extra_field == "extra_value"  # type: ignore[attr-defined]
        assert result.another == 123  # type: ignore[attr-defined]


class TestTimedeltaSerialization:
    """Tests for ISO 8601 timedelta serialization."""

    def test_timedelta_seconds(self) -> None:
        """Test timedelta serializes to ISO 8601 format (seconds)."""
        result = WaitResult(timeout=timedelta(seconds=30))
        json_data = result.model_dump_json()
        assert '"timeout":"PT30S"' in json_data

    def test_timedelta_minutes(self) -> None:
        """Test timedelta serializes to ISO 8601 format (minutes)."""
        result = WaitResult(timeout=timedelta(minutes=2))
        json_data = result.model_dump_json()
        assert '"timeout":"PT2M"' in json_data or '"timeout":"PT120S"' in json_data

    def test_timedelta_complex(self) -> None:
        """Test timedelta serializes complex durations."""
        result = WaitResult(timeout=timedelta(minutes=2, seconds=30))
        json_data = result.model_dump_json()
        # Could be PT2M30S or PT150S depending on implementation
        assert "PT" in json_data
        assert "timeout" in json_data

    def test_timedelta_milliseconds(self) -> None:
        """Test timedelta with milliseconds."""
        result = WaitResult(timeout=timedelta(milliseconds=500))
        json_data = result.model_dump_json()
        assert "PT" in json_data


class TestTransactionCodeValidation:
    """Tests for transaction code pattern validation."""

    def test_valid_tcode_uppercase(self) -> None:
        """Test valid uppercase transaction code."""
        result = TransactionResult(tcode="SE16")
        assert result.tcode == "SE16"

    def test_valid_tcode_with_numbers(self) -> None:
        """Test valid transaction code with numbers."""
        result = TransactionResult(tcode="VA01")
        assert result.tcode == "VA01"

    def test_valid_tcode_with_underscore(self) -> None:
        """Test valid transaction code with underscore."""
        result = TransactionResult(tcode="SM_WORKCENTER")
        assert result.tcode == "SM_WORKCENTER"

    def test_valid_tcode_with_slash(self) -> None:
        """Test valid transaction code with slash (namespace)."""
        result = TransactionResult(tcode="/IWFND/GW_CLIENT")
        assert result.tcode == "/IWFND/GW_CLIENT"

    def test_tcode_normalized_to_uppercase(self) -> None:
        """Test transaction code is normalized to uppercase."""
        result = TransactionResult(tcode="se16")
        assert result.tcode == "SE16"

    def test_invalid_tcode_with_spaces(self) -> None:
        """Test invalid transaction code with spaces."""
        with pytest.raises(ValidationError):
            TransactionResult(tcode="SE 16")

    def test_invalid_tcode_with_special_chars(self) -> None:
        """Test invalid transaction code with special characters."""
        with pytest.raises(ValidationError):
            TransactionResult(tcode="SE16#")

    def test_invalid_tcode_empty_string(self) -> None:
        """Test that empty string fails TCode validation (GH-555)."""
        with pytest.raises(ValidationError):
            TransactionResult(tcode="")

    def test_valid_tcode_navigation_command(self) -> None:
        """Test that navigation commands like /n are valid TCode values (GH-555)."""
        result = TransactionResult(tcode="/n")
        assert result.tcode == "/N"

    def test_valid_tcode_navigation_nex(self) -> None:
        """Test /nex (exit all sessions) is a valid TCode value."""
        result = TransactionResult(tcode="/nex")
        assert result.tcode == "/NEX"


class TestIntegerConstraints:
    """Tests for integer field constraints (ge=0, ge=1)."""

    def test_keepalive_interval_positive(self) -> None:
        """Test interval_seconds must be >= 1."""
        result = KeepaliveResult(running=True, interval_seconds=1)
        assert result.interval_seconds == 1

    def test_keepalive_interval_zero_fails(self) -> None:
        """Test interval_seconds=0 fails validation."""
        with pytest.raises(ValidationError):
            KeepaliveResult(running=True, interval_seconds=0)

    def test_table_total_rows_zero(self) -> None:
        """Test total_rows can be 0."""
        result = TableData(total_rows=0)
        assert result.total_rows == 0

    def test_table_total_rows_negative_fails(self) -> None:
        """Test total_rows cannot be negative."""
        with pytest.raises(ValidationError):
            TableData(total_rows=-1)

    def test_table_start_row_minimum(self) -> None:
        """Test start_row must be >= 1."""
        result = TableData(start_row=1)
        assert result.start_row == 1

    def test_table_start_row_zero_fails(self) -> None:
        """Test start_row=0 fails validation."""
        with pytest.raises(ValidationError):
            TableData(start_row=0)

    def test_discovered_fields_count_zero(self) -> None:
        """Test field_count can be 0."""
        result = DiscoveredFields(field_count=0)
        assert result.field_count == 0


class TestSubclassFailureMethod:
    """Tests for failure() factory method on subclasses."""

    def test_login_result_failure(self) -> None:
        """Test LoginResult.failure() preserves additional fields."""
        result = LoginResult.failure("Login failed", url="https://sap.example.com")
        assert result.success is False
        assert result.error == "Login failed"
        assert result.url == "https://sap.example.com"

    def test_transaction_result_failure(self) -> None:
        """Test TransactionResult.failure() preserves tcode."""
        result = TransactionResult.failure("Transaction failed", tcode="SE16")
        assert result.success is False
        assert result.error == "Transaction failed"
        assert result.tcode == "SE16"

    def test_click_result_failure(self) -> None:
        """Test ClickResult.failure() preserves selector."""
        result = ClickResult.failure("Element not found", selector="#button1")
        assert result.success is False
        assert result.error == "Element not found"
        assert result.selector == "#button1"


class TestModelSerialization:
    """Tests for JSON serialization of models."""

    def test_session_status_json(self) -> None:
        """Test SessionStatus serializes correctly."""
        result = SessionStatus(status="active", message="Session is alive")
        json_str = result.model_dump_json()
        assert '"status":"active"' in json_str
        assert '"message":"Session is alive"' in json_str
        assert '"success":true' in json_str

    def test_screen_info_json(self) -> None:
        """Test ScreenInfo with optional fields serializes correctly."""
        result = ScreenInfo(
            transaction="SE16",
            title="Data Browser",
            url="https://sap.example.com/sap/bc/gui",
            program="SAPLSETB",
            dynpro="0100",
        )
        data = result.model_dump()
        assert data["transaction"] == "SE16"
        assert data["title"] == "Data Browser"
        assert data["program"] == "SAPLSETB"
        assert data["dynpro"] == "0100"
        # New fields default to None when not provided
        assert data["system_name"] is None
        assert data["client"] is None
        assert data["user"] is None

    def test_screen_info_with_system_info(self) -> None:
        """Test ScreenInfo with system_name, client, user (#593)."""
        result = ScreenInfo(
            transaction="SE38",
            title="ABAP Editor",
            url="desktop://sap",
            system_name="S4U",
            client="100",
            user="KLEINK",
        )
        data = result.model_dump()
        assert data["system_name"] == "S4U"
        assert data["client"] == "100"
        assert data["user"] == "KLEINK"

    def test_field_info_json(self) -> None:
        """Test FieldInfo serializes correctly."""
        field = FieldInfo(
            id="field1",
            name="TABLENAME",
            label="Table Name",
            type="text",
            selector='input[lsdata*="TABLENAME"]',
            value="T000",
        )
        data = field.model_dump()
        assert data["id"] == "field1"
        assert data["selector"] == 'input[lsdata*="TABLENAME"]'
        assert data["value"] == "T000"


class TestKeyboardResultStatusBarValidation:
    """Tests for KeyboardResult status bar consistency validation."""

    def test_no_status_bar_read(self) -> None:
        """Test KeyboardResult with status_bar_read=False (default)."""
        result = KeyboardResult(key="Enter", page_title="SAP")
        assert result.status_bar_read is False
        assert result.status_bar_type is None
        assert result.status_bar_message is None

    def test_status_bar_read_with_message(self) -> None:
        """Test KeyboardResult with status bar successfully read."""
        result = KeyboardResult(
            key="Ctrl+S",
            page_title="SAP",
            status_bar_read=True,
            status_bar_type="S",
            status_bar_message="Document saved",
        )
        assert result.status_bar_read is True
        assert result.status_bar_type == "S"
        assert result.status_bar_message == "Document saved"

    def test_status_bar_read_empty_message(self) -> None:
        """Test KeyboardResult with status bar read but empty message."""
        result = KeyboardResult(
            key="F8",
            page_title="SAP",
            status_bar_read=True,
            status_bar_type="none",
            status_bar_message="",
        )
        assert result.status_bar_read is True
        assert result.status_bar_type == "none"
        assert result.status_bar_message == ""

    def test_status_bar_read_missing_message_fails(self) -> None:
        """Test that status_bar_read=True without message fails."""
        with pytest.raises(ValidationError, match="status_bar_message must be set"):
            KeyboardResult(
                key="F8",
                page_title="SAP",
                status_bar_read=True,
                status_bar_type="S",
                # status_bar_message is None
            )

    def test_status_bar_read_missing_type_fails(self) -> None:
        """Test that status_bar_read=True without type fails."""
        with pytest.raises(ValidationError, match="status_bar_type must be set"):
            KeyboardResult(
                key="F8",
                page_title="SAP",
                status_bar_read=True,
                # status_bar_type is None
                status_bar_message="Some message",
            )

    def test_status_bar_not_read_with_message_fails(self) -> None:
        """Test that status_bar_read=False with message fails."""
        with pytest.raises(ValidationError, match="status_bar_message must be None"):
            KeyboardResult(
                key="Enter",
                page_title="SAP",
                status_bar_read=False,
                status_bar_message="Should not be here",
            )

    def test_status_bar_not_read_with_type_fails(self) -> None:
        """Test that status_bar_read=False with type fails."""
        with pytest.raises(ValidationError, match="status_bar_type must be None"):
            KeyboardResult(
                key="Enter",
                page_title="SAP",
                status_bar_read=False,
                status_bar_type="S",
            )


class TestCapabilitiesResult:
    """Tests for CapabilitiesResult and ToolInfo models."""

    def test_tool_info_creation(self) -> None:
        """Test ToolInfo can be created with name and description."""
        tool = ToolInfo(name="sap_login", description="Log into SAP Web GUI")
        assert tool.name == "sap_login"
        assert tool.description == "Log into SAP Web GUI"

    def test_capabilities_result_empty(self) -> None:
        """Test CapabilitiesResult with no tools."""
        result = CapabilitiesResult(tools=[])
        assert result.success is True
        assert result.tools == []
        assert result.tool_count == 0

    def test_capabilities_result_with_tools(self) -> None:
        """Test CapabilitiesResult with multiple tools."""
        tools = [
            ToolInfo(name="sap_login", description="Login tool"),
            ToolInfo(name="sap_transaction", description="Transaction tool"),
            ToolInfo(name="browser_click", description="Click tool"),
        ]
        result = CapabilitiesResult(tools=tools)
        assert result.success is True
        assert len(result.tools) == 3
        assert result.tool_count == 3
        assert result.tools[0].name == "sap_login"

    def test_capabilities_result_failure(self) -> None:
        """Test CapabilitiesResult.failure() factory method."""
        result = CapabilitiesResult.failure("Could not get capabilities")
        assert result.success is False
        assert result.error == "Could not get capabilities"
        assert result.tools == []

    def test_capabilities_result_json(self) -> None:
        """Test CapabilitiesResult serializes correctly to JSON."""
        tools = [ToolInfo(name="test_tool", description="A test tool")]
        result = CapabilitiesResult(tools=tools)
        json_str = result.model_dump_json()
        assert '"name":"test_tool"' in json_str
        assert '"description":"A test tool"' in json_str
        assert '"success":true' in json_str


class TestLoginResultGuidance:
    """Tests for LoginResult guidance field."""

    def test_login_result_with_guidance(self) -> None:
        """Test LoginResult can include guidance."""
        result = LoginResult(
            url="https://sap.example.com",
            user="testuser",
            guidance="Call sap_get_capabilities() first",
        )
        assert result.success is True
        assert result.guidance == "Call sap_get_capabilities() first"

    def test_login_result_without_guidance(self) -> None:
        """Test LoginResult guidance defaults to None."""
        result = LoginResult(url="https://sap.example.com")
        assert result.guidance is None

    def test_login_result_failure_no_guidance(self) -> None:
        """Test LoginResult.failure() has no guidance."""
        result = LoginResult.failure("Login failed", url="https://sap.example.com")
        assert result.success is False
        assert result.guidance is None


class TestSessionIdValidation:
    """Tests for SessionId type validation."""

    def test_valid_session_id(self) -> None:
        """Test valid session ID format."""
        from pydantic import TypeAdapter

        from sapguimcp.models import SessionId

        adapter = TypeAdapter(SessionId)
        assert adapter.validate_python("s1") == "s1"
        assert adapter.validate_python("s123") == "s123"

    def test_session_id_normalized_to_lowercase(self) -> None:
        """Test that session IDs are normalized to lowercase."""
        from pydantic import TypeAdapter

        from sapguimcp.models import SessionId

        adapter = TypeAdapter(SessionId)
        assert adapter.validate_python("S1") == "s1"
        assert adapter.validate_python("S99") == "s99"

    def test_invalid_session_id_rejected(self) -> None:
        """Test that invalid session IDs raise ValidationError."""
        from pydantic import TypeAdapter, ValidationError

        from sapguimcp.models import SessionId

        adapter = TypeAdapter(SessionId)
        with pytest.raises(ValidationError):
            adapter.validate_python("invalid")
        with pytest.raises(ValidationError):
            adapter.validate_python("1")  # Must start with 's'
        with pytest.raises(ValidationError):
            adapter.validate_python("session1")  # Must be 's' + digits only


class TestSessionModels:
    """Tests for session management result models."""

    def test_session_info_creation(self) -> None:
        """Test SessionInfo model creation."""
        from sapguimcp.models import SessionInfo

        info = SessionInfo(session_id="s1", tcode="VA01", title="Create Sales Order", is_primary=True)
        assert info.session_id == "s1"
        assert info.tcode == "VA01"
        assert info.is_primary is True
        # New fields default to None
        assert info.system_name is None
        assert info.client is None
        assert info.user is None

    def test_session_info_with_system_info(self) -> None:
        """Test SessionInfo with system_name, client, user (#593)."""
        from sapguimcp.models import SessionInfo

        info = SessionInfo(
            session_id="s1",
            tcode="SE38",
            title="ABAP Editor",
            is_primary=True,
            system_name="S4U",
            client="100",
            user="KLEINK",
        )
        assert info.system_name == "S4U"
        assert info.client == "100"
        assert info.user == "KLEINK"

    def test_session_list_result(self) -> None:
        """Test SessionListResult with multiple sessions."""
        from sapguimcp.models import SessionInfo, SessionListResult

        result = SessionListResult(
            sessions=[
                SessionInfo(session_id="s1", is_primary=True),
                SessionInfo(session_id="s2", tcode="VA01"),
            ]
        )
        assert result.session_count == 2
        assert result.sessions[0].is_primary is True

    def test_session_close_result(self) -> None:
        """Test SessionCloseResult model."""
        from sapguimcp.models import SessionCloseResult

        result = SessionCloseResult(session_id="s2", remaining_sessions=1)
        assert result.success is True
        assert result.session_id == "s2"
        assert result.remaining_sessions == 1
