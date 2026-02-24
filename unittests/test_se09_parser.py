"""
Unit tests for SE09 (Transport Organizer) parser.

Tests parsing of YAML accessibility snapshots from SE09 transport list display.
"""

from pathlib import Path

import pytest

from sapwebguimcp.parsers.se09_parser import parse_se09_transport_list

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

    def test_request_has_request_type(self) -> None:
        """Each request should have a request type."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.request_type in ("Workbench", "Customizing"), f"Bad type: {req.request_type}"

    def test_request_has_target_system(self) -> None:
        """Each request should have a target system."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        for req in result.requests:
            assert req.target_system != "", f"Empty target for {req.request_number}"

    def test_specific_transport_present(self) -> None:
        """Known transport S4UK902153 should be present."""
        snapshot = _load_snapshot("se09_modifiable_only")
        result = parse_se09_transport_list(snapshot)

        numbers = {r.request_number for r in result.requests}
        assert "S4UK902153" in numbers


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
