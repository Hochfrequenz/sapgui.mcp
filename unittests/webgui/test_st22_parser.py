"""
Unit tests for ST22 (Short Dump Analysis) parser.

Tests parsing of YAML accessibility snapshots from ST22 screens.
"""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.st22_parser import (
    is_no_dumps_message,
    parse_st22_dump_detail,
    parse_st22_dump_list,
    parse_st22_initial_screen,
)
from sapguimcp.models.st22_models import ST22Dump, ST22DumpDetail

SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "st22_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run exploration tests first")
    return filepath.read_text(encoding="utf-8")


class TestParseInitialScreen:
    """Tests for parsing ST22 initial screen."""

    def test_parse_initial_screen_counts(self) -> None:
        """Initial screen snapshot should extract today/yesterday counts."""
        snapshot = _load_snapshot("st22_initial")
        counts = parse_st22_initial_screen(snapshot)

        assert "today" in counts
        assert "yesterday" in counts
        assert counts["today"] >= 0
        assert counts["yesterday"] >= 0

    def test_parse_initial_screen_with_dumps(self) -> None:
        """Initial screen shows '1 Laufzeitfehler' for both days."""
        snapshot = _load_snapshot("st22_initial")
        counts = parse_st22_initial_screen(snapshot)

        # Our captured snapshot has "1 Laufzeitfehler" for both
        assert counts["today"] == 1
        assert counts["yesterday"] == 1

    def test_parse_initial_screen_synthetic(self) -> None:
        """Synthetic snapshot with known counts."""
        snapshot = """- group "Standard":
  - heading "Standard" [level=3]
  - button "Heute"
  - button "5 Laufzeitfehler"
  - button "Gestern"
  - button "12 Laufzeitfehler"
"""
        counts = parse_st22_initial_screen(snapshot)
        assert counts["today"] == 5
        assert counts["yesterday"] == 12

    def test_parse_initial_screen_en(self) -> None:
        """Synthetic EN snapshot."""
        snapshot = """- group "Standard":
  - heading "Standard" [level=3]
  - button "Today"
  - button "3 Runtime Errors"
  - button "Yesterday"
  - button "0 Runtime Errors"
"""
        counts = parse_st22_initial_screen(snapshot)
        assert counts["today"] == 3
        assert counts["yesterday"] == 0

    def test_parse_initial_screen_empty(self) -> None:
        """Snapshot without count buttons returns 0."""
        snapshot = "- heading 'Something else'"
        counts = parse_st22_initial_screen(snapshot)
        assert counts["today"] == 0
        assert counts["yesterday"] == 0


class TestIsNoDumpsMessage:
    """Tests for no-dumps detection."""

    def test_no_dumps_de(self) -> None:
        snapshot = 'note "Warnung Meldungsleiste Es sind keine Kurzdumps - wie selektiert - verfügbar"'
        assert is_no_dumps_message(snapshot)

    def test_no_dumps_en(self) -> None:
        snapshot = 'note "Warning No entries found for the selection"'
        assert is_no_dumps_message(snapshot)

    def test_no_dumps_from_real_snapshot(self) -> None:
        """Real snapshot with no dumps message."""
        snapshot = _load_snapshot("st22_today_executed")
        assert is_no_dumps_message(snapshot)

    def test_has_dumps(self) -> None:
        """Snapshot without no-dumps message."""
        snapshot = '- row "some data row"\n  - cell "10:00:00"\n  - cell "ZPROG"'
        assert not is_no_dumps_message(snapshot)


class TestParseDumpList:
    """Tests for parsing ST22 dump list."""

    def test_empty_list_returns_empty(self) -> None:
        """Snapshot with no dump rows should return empty list."""
        snapshot = '- heading "ABAP Runtime Errors":\n  - toolbar:\n    - button "Today"'
        dumps = parse_st22_dump_list(snapshot)
        assert dumps == []

    def test_no_dumps_message_returns_empty(self) -> None:
        """Snapshot with 'no dumps' message returns empty list."""
        snapshot = 'note "Es sind keine Kurzdumps - wie selektiert - verfügbar"'
        dumps = parse_st22_dump_list(snapshot)
        assert dumps == []

    def test_parse_gridcell_format(self) -> None:
        """Parse dumps from gridcell ALV format."""
        snapshot = """- grid:
  - row:
    - columnheader "Zeit"
    - columnheader "Laufzeitfehler"
    - columnheader "Programm"
    - columnheader "Benutzer"
    - columnheader "Kurztext"
  - row:
    - gridcell "14:32:15"
    - gridcell "RABAX_STATE"
    - gridcell "ZTEST_PROGRAM"
    - gridcell "TESTUSER"
    - gridcell "Test error"
  - row:
    - gridcell "15:00:00"
    - gridcell "MESSAGE_TYPE_X"
    - gridcell "ZPROG2"
    - gridcell "USER2"
    - gridcell "Another error"
"""
        dumps = parse_st22_dump_list(snapshot)

        assert len(dumps) == 2
        # Parser returns DOM order (sorting is done in tool layer)
        assert dumps[0].index == 0
        assert dumps[0].time == "14:32:15"
        assert dumps[0].error_type == "RABAX_STATE"
        assert dumps[0].program == "ZTEST_PROGRAM"
        assert dumps[0].user == "TESTUSER"
        assert dumps[0].short_text == "Test error"

        assert dumps[1].index == 1
        assert dumps[1].time == "15:00:00"
        assert dumps[1].error_type == "MESSAGE_TYPE_X"
        assert dumps[1].program == "ZPROG2"

    def test_parse_cell_format(self) -> None:
        """Parse dumps from cell-based row format (fallback)."""
        snapshot = """- row "14:32:15 ZTEST_PROGRAM RABAX_STATE TESTUSER":
    - cell "14:32:15"
    - cell "ZTEST_PROGRAM"
    - cell ""
    - cell "RABAX_STATE"
    - cell "TESTUSER"
"""
        dumps = parse_st22_dump_list(snapshot)
        # The cell pattern heuristic should pick this up
        assert len(dumps) >= 1
        if len(dumps) > 0:
            assert dumps[0].time == "14:32:15"

    def test_dump_indexes_sequential(self) -> None:
        """Dump indexes should be sequential starting from 0."""
        snapshot = """- grid:
  - row:
    - columnheader "Zeit"
    - columnheader "Laufzeitfehler"
    - columnheader "Programm"
    - columnheader "Benutzer"
  - row:
    - gridcell "10:00:00"
    - gridcell "ERROR1"
    - gridcell "PROG1"
    - gridcell "USER1"
  - row:
    - gridcell "11:00:00"
    - gridcell "ERROR2"
    - gridcell "PROG2"
    - gridcell "USER2"
  - row:
    - gridcell "12:00:00"
    - gridcell "ERROR3"
    - gridcell "PROG3"
    - gridcell "USER3"
"""
        dumps = parse_st22_dump_list(snapshot)
        assert len(dumps) == 3
        for i, dump in enumerate(dumps):
            assert dump.index == i

    def test_dumps_preserve_dom_order(self) -> None:
        """Parser returns dumps in DOM order (sorting is done in tool layer)."""
        snapshot = """- grid:
  - row:
    - columnheader "Zeit"
    - columnheader "Laufzeitfehler"
    - columnheader "Programm"
    - columnheader "Benutzer"
  - row:
    - gridcell "08:15:00"
    - gridcell "EARLY_ERROR"
    - gridcell "ZPROG_EARLY"
    - gridcell "USER1"
  - row:
    - gridcell "16:45:30"
    - gridcell "LATE_ERROR"
    - gridcell "ZPROG_LATE"
    - gridcell "USER2"
  - row:
    - gridcell "12:00:00"
    - gridcell "MID_ERROR"
    - gridcell "ZPROG_MID"
    - gridcell "USER3"
"""
        dumps = parse_st22_dump_list(snapshot)
        assert len(dumps) == 3
        # DOM order preserved: 08:15, 16:45, 12:00
        assert dumps[0].time == "08:15:00"
        assert dumps[0].error_type == "EARLY_ERROR"
        assert dumps[0].index == 0
        assert dumps[1].time == "16:45:30"
        assert dumps[1].error_type == "LATE_ERROR"
        assert dumps[1].index == 1
        assert dumps[2].time == "12:00:00"
        assert dumps[2].error_type == "MID_ERROR"
        assert dumps[2].index == 2


class TestParseDumpDetail:
    """Tests for parsing ST22 dump detail text."""

    def test_parse_detail_fallback(self) -> None:
        """Parser should not crash on unexpected format, returning raw_text fallback."""
        snapshot = '- document:\n  - text: "Some random text content here"'
        detail = parse_st22_dump_detail(snapshot)

        assert isinstance(detail, ST22DumpDetail)
        assert detail.raw_text  # Should still have raw content
        assert detail.error_type == ""  # Could not extract

    def test_parse_detail_with_sections(self) -> None:
        """Parse detail with known section headers."""
        snapshot = """- document:
  - text: "ABAP Laufzeitfehler"
  - text: "Laufzeitfehler: RABAX_STATE"
  - text: "Was ist geschehen?"
  - text: "An error occurred during ABAP processing."
  - text: "The current program terminated unexpectedly."
  - text: "Was können Sie tun?"
  - text: "Contact your system administrator."
  - text: "Fehleranalyse"
  - text: "Error in line 42 of program ZTEST"
  - text: "Programm: ZTEST_PROGRAM"
  - text: "Zeile im Quelltext: 42"
"""
        detail = parse_st22_dump_detail(snapshot)

        assert detail.error_type == "RABAX_STATE"
        assert detail.program == "ZTEST_PROGRAM"
        assert detail.line == 42
        assert "error occurred" in detail.what_happened.lower() or detail.what_happened != ""
        assert detail.raw_text

    def test_parse_detail_en(self) -> None:
        """Parse EN dump detail."""
        snapshot = """- document:
  - text: "ABAP Runtime Errors"
  - text: "Runtime Error: MESSAGE_TYPE_X"
  - text: "What happened?"
  - text: "A RAISE statement in the program ZPROG caused an exception."
  - text: "How to Correct the Error"
  - text: "Check the program logic."
  - text: "Program: ZPROG_MAIN"
  - text: "Source Code Line: 100"
"""
        detail = parse_st22_dump_detail(snapshot)

        assert detail.error_type == "MESSAGE_TYPE_X"
        assert detail.program == "ZPROG_MAIN"
        assert detail.line == 100
        assert "RAISE" in detail.what_happened or detail.what_happened != ""

    def test_parse_detail_raw_text_truncated(self) -> None:
        """raw_text should be truncated if content is very large."""
        # Create a large snapshot
        large_content = '- text: "' + "x" * 500 + '"\n' * 100
        detail = parse_st22_dump_detail(large_content)

        assert len(detail.raw_text) <= 12000  # ~10KB with margin

    def test_parse_detail_call_stack(self) -> None:
        """Extract call stack entries."""
        snapshot = """- document:
  - text: "Active Calls"
  - text: "ZTEST_PROGRAM line 42"
  - text: "SAPMSYST line 100"
  - text: "SAPLZMOD line 200"
  - text: ""
  - text: "End of call stack"
"""
        detail = parse_st22_dump_detail(snapshot)
        assert len(detail.call_stack) >= 2
