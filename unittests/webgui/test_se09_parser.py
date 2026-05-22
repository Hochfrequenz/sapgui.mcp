"""
Unit tests for SE09 (Transport Organizer) parser.

Tests parsing of YAML accessibility snapshots from SE09 transport list display.
"""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.se09_parser import parse_se09_transport_list
from sapguimcp.models.se09_models import TransportRequest
from sapguimcp.tools.se09_tools import _assign_tasks_from_expanded_text

# Path to captured YAML snapshots
SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se09_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run exploration tests first")
    return filepath.read_text(encoding="utf-8")


class TestTransportListParsing:
    """Tests for parsing transport list."""

    def test_parse_modifiable_transport_list(self) -> None:
        """Modifiable transport list should parse requests."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        assert result.success
        assert result.request_count > 0
        assert len(result.requests) == result.request_count

    def test_request_has_valid_transport_number(self) -> None:
        """Each request should have a valid transport number."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert len(req.request_number) == 10, f"Bad number: {req.request_number}"
            assert req.request_number[3] == "K", f"Missing K: {req.request_number}"

    def test_request_has_owner(self) -> None:
        """Each request should have an owner."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.owner != "", f"Empty owner for {req.request_number}"

    def test_request_has_description(self) -> None:
        """Each request should have a description."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.description != "", f"Empty description for {req.request_number}"

    def test_request_has_status(self) -> None:
        """Each request should have a status."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.status in ("Modifiable", "Released"), f"Bad status: {req.status}"

    def test_request_type_is_valid_if_set(self) -> None:
        """Request type, when detected, should be Workbench or Customizing."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            if req.request_type:
                assert req.request_type in ("Workbench", "Customizing"), f"Bad type: {req.request_type}"

    def test_request_has_target_system(self) -> None:
        """Each request should have a target system."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.target_system != "", f"Empty target for {req.request_number}"

    def test_transport_numbers_are_unique(self) -> None:
        """Transport numbers should be unique in the result."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        numbers = [r.request_number for r in result.requests]
        assert len(numbers) == len(set(numbers)), f"Duplicate transport numbers: {numbers}"


class TestNoTransportsParsing:
    """Tests for parsing when no transports are found."""

    def test_no_transports_returns_empty(self) -> None:
        """Initial screen (no results) should return empty list."""
        snapshot = _load_snapshot("se09_no_transports")
        result = parse_se09_transport_list(snapshot)

        assert result.success
        assert result.request_count == 0
        assert result.requests == []

    def test_empty_snapshot_returns_empty(self) -> None:
        """Empty snapshot should return empty list."""
        result = parse_se09_transport_list("")

        assert result.success
        assert result.request_count == 0

    def test_initial_screen_returns_empty(self) -> None:
        """Initial SE09 screen (before display) returns empty."""
        snapshot = _load_snapshot("se09_initial")
        result = parse_se09_transport_list(snapshot)

        assert result.success
        assert result.request_count == 0


class TestCustomizingWildcardParsing:
    """Tests for parsing customizing transports with wildcard user."""

    def test_parse_customizing_wildcard_snapshot(self) -> None:
        """Customizing snapshot with wildcard user should parse requests."""
        snapshot = _load_snapshot("se09_customizing_wildcard")
        result = parse_se09_transport_list(snapshot)

        assert result.success
        assert result.request_count > 0

    def test_customizing_transport_numbers_are_valid(self) -> None:
        """Transport numbers with client suffix should be parsed to 10 chars."""
        snapshot = _load_snapshot("se09_customizing_wildcard")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert len(req.request_number) == 10, f"Bad number: {req.request_number}"
            assert req.request_number[3] == "K", f"Missing K: {req.request_number}"

    def test_customizing_requests_have_owner(self) -> None:
        """Each customizing request should have an owner."""
        snapshot = _load_snapshot("se09_customizing_wildcard")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.owner != "", f"Empty owner for {req.request_number}"

    def test_customizing_requests_have_status(self) -> None:
        """Customizing requests should have Modifiable or Released status."""
        snapshot = _load_snapshot("se09_customizing_wildcard")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.status in ("Modifiable", "Released"), f"Bad status: {req.status} for {req.request_number}"

    def test_known_customizing_transport_present(self) -> None:
        """Known customizing transport S4UK901835 should be present."""
        snapshot = _load_snapshot("se09_customizing_wildcard")
        result = parse_se09_transport_list(snapshot)

        numbers = {r.request_number for r in result.requests}
        assert "S4UK901835" in numbers, f"S4UK901835 not in {numbers}"


class TestWorkbenchOnlyParsing:
    """Tests for parsing workbench-only transport list (se09_transport_list snapshot)."""

    def test_parse_workbench_snapshot(self) -> None:
        """Workbench snapshot should parse requests."""
        snapshot = _load_snapshot("se09_transport_list")
        result = parse_se09_transport_list(snapshot)

        assert result.success
        assert result.request_count > 0

    def test_workbench_requests_are_workbench_type(self) -> None:
        """All requests in workbench-only snapshot should be Workbench type."""
        snapshot = _load_snapshot("se09_transport_list")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            if req.request_type:
                assert (
                    req.request_type == "Workbench"
                ), f"Expected Workbench, got {req.request_type} for {req.request_number}"

    def test_workbench_requests_are_modifiable(self) -> None:
        """Workbench snapshot (KLEINK, modifiable) should have Modifiable status."""
        snapshot = _load_snapshot("se09_transport_list")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            if req.status:
                assert req.status == "Modifiable", f"Expected Modifiable, got {req.status} for {req.request_number}"


class TestRequestTypeConsistency:
    """Verify parser correctly identifies request types from different snapshots."""

    def test_customizing_snapshot_has_no_workbench(self) -> None:
        """Customizing-only snapshot should not contain Workbench requests."""
        snapshot = _load_snapshot("se09_customizing_wildcard")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            if req.request_type:
                assert req.request_type != "Workbench", (
                    f"Unexpected Workbench request {req.request_number} " "in customizing-only snapshot"
                )

    def test_workbench_snapshot_has_no_customizing(self) -> None:
        """Workbench-only snapshot should not contain Customizing requests."""
        snapshot = _load_snapshot("se09_transport_list")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            if req.request_type:
                assert req.request_type != "Customizing", (
                    f"Unexpected Customizing request {req.request_number} " "in workbench-only snapshot"
                )

    def test_modifiable_only_parses_successfully(self) -> None:
        """Modifiable-only snapshot should parse requests regardless of type."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        assert result.success
        assert result.request_count > 0
        # Request type may or may not be detected depending on section headers
        for req in result.requests:
            if req.request_type:
                assert req.request_type in ("Workbench", "Customizing")


class TestEdgeCases:
    """Tests for edge cases."""

    def test_include_objects_does_not_crash(self) -> None:
        """include_objects=True should not crash (not supported in v1)."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot, include_objects=True)

        assert result.success
        assert result.request_count > 0

    def test_retrieved_at_is_set(self) -> None:
        """retrieved_at should be set to current time."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        assert result.retrieved_at is not None


class TestExpandedTreeTaskAssignment:
    """Tests for _assign_tasks_from_expanded_text."""

    def test_tasks_assigned_to_correct_request(self) -> None:
        """Tasks should be assigned to their parent request."""
        requests = [
            TransportRequest(request_number="S4UK902153", owner="KLEINK", description="Test"),
            TransportRequest(request_number="S4UK902096", owner="KLEINK", description="Solver"),
        ]
        request_numbers = {"S4UK902153", "S4UK902096"}
        text_lines = [
            "S4UK902153",
            "KLEINK Test",
            "S4UK902154",
            "KLEINK Entwickl./Korrektur",
            "S4UK902096",
            "KLEINK Solver",
            "S4UK902097",
            "KLEINK Entwickl./Korrektur",
        ]

        _assign_tasks_from_expanded_text(requests, request_numbers, text_lines)

        assert len(requests[0].tasks) == 1
        assert requests[0].tasks[0].task_number == "S4UK902154"
        assert requests[0].tasks[0].owner == "KLEINK"
        assert requests[0].tasks[0].description == "Entwickl./Korrektur"

        assert len(requests[1].tasks) == 1
        assert requests[1].tasks[0].task_number == "S4UK902097"

    def test_multiple_tasks_per_request(self) -> None:
        """A request can have multiple tasks."""
        requests = [
            TransportRequest(request_number="S4UK901097", owner="KLEINK", description="WB"),
        ]
        request_numbers = {"S4UK901097"}
        text_lines = [
            "S4UK901097",
            "KLEINK WB",
            "S4UK901203",
            "HAFFML Entwickl./Korrektur",
            "S4UK901877",
            "BECKT Reparatur",
            "S4UK901098",
            "KLEINK Entwickl./Korrektur",
        ]

        _assign_tasks_from_expanded_text(requests, request_numbers, text_lines)

        assert len(requests[0].tasks) == 3
        assert requests[0].tasks[0].task_number == "S4UK901203"
        assert requests[0].tasks[0].owner == "HAFFML"
        assert requests[0].tasks[1].task_number == "S4UK901877"
        assert requests[0].tasks[1].owner == "BECKT"
        assert requests[0].tasks[2].task_number == "S4UK901098"
        assert requests[0].tasks[2].owner == "KLEINK"

    def test_no_tasks_when_no_expansion(self) -> None:
        """Requests should have no tasks if only requests are in the text."""
        requests = [
            TransportRequest(request_number="S4UK902153", owner="KLEINK", description="Test"),
        ]
        request_numbers = {"S4UK902153"}
        text_lines = [
            "S4UK902153",
            "KLEINK Test",
        ]

        _assign_tasks_from_expanded_text(requests, request_numbers, text_lines)

        assert len(requests[0].tasks) == 0

    def test_task_without_description(self) -> None:
        """Tasks with only a transport number (no following description) should work."""
        requests = [
            TransportRequest(request_number="S4UK902153", owner="KLEINK", description="Test"),
        ]
        request_numbers = {"S4UK902153"}
        text_lines = [
            "S4UK902153",
            "KLEINK Test",
            "S4UK902154",
        ]

        _assign_tasks_from_expanded_text(requests, request_numbers, text_lines)

        assert len(requests[0].tasks) == 1
        assert requests[0].tasks[0].task_number == "S4UK902154"
        assert requests[0].tasks[0].owner == ""

    def test_empty_text_lines(self) -> None:
        """Empty text lines should not crash."""
        requests = [
            TransportRequest(request_number="S4UK902153", owner="KLEINK", description="Test"),
        ]
        _assign_tasks_from_expanded_text(requests, {"S4UK902153"}, [])
        assert len(requests[0].tasks) == 0
