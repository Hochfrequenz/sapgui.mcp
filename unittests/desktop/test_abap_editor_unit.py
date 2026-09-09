"""Unit tests for the source-code editor line handling (issue #859).

The fakes reproduce the row semantics measured on a real ``GuiAbapEditor``
(SAP GUI 8.0, HF R3 / ECC, "Quellcode-basierter Editor"):

* rows are 1-based — ``GetLineText(0)`` is an empty phantom row and the last
  real line sits at index ``GetLineCount()``;
* ``Delete()`` removes the selected rows and never leaves the buffer with
  fewer than one (empty) row;
* ``InsertText`` drops the segment after the final newline and inserts at the
  top of the buffer.
"""

from __future__ import annotations

import pytest

from sapguimcp.backend.desktop import _abap_editor

ENDFORM_SOURCE = "\n".join(
    [
        "REPORT ztest.",
        "",
        "FORM validate_and_save.",
        "  WRITE 'hello'.",
        "ENDFORM.",
    ]
)


class FakeOneBasedEditor:
    """GuiAbapEditor as it actually behaves: 1-based rows."""

    def __init__(self, lines: list[str] | None = None) -> None:
        self.lines: list[str] = list(lines) if lines else [""]
        self._selection: tuple[int, int] | None = None

    # -- COM surface (PascalCase on purpose) --------------------------------

    def GetLineCount(self) -> int:  # noqa: N802
        return len(self.lines)

    def GetLineText(self, index: int) -> str:  # noqa: N802
        if 1 <= index <= len(self.lines):
            return self.lines[index - 1]
        return ""

    def SelectRange(self, start_row: int, _start_col: int, end_row: int, _end_col: int) -> None:  # noqa: N802
        self._selection = (start_row, end_row)

    def Delete(self) -> None:  # noqa: N802
        if self._selection is None:
            return
        start, end = self._selection
        start = max(start, 1)
        end = min(end, len(self.lines))
        if start <= end:
            del self.lines[start - 1 : end]
        if not self.lines:
            self.lines = [""]
        self._selection = None

    def InsertText(self, text: str, _line: int, _col: int) -> None:  # noqa: N802
        new_lines = text.split("\n")
        if new_lines and new_lines[-1] == "":
            new_lines.pop()  # InsertText drops the segment after the last \n
        self.lines[0:0] = new_lines


class FakeZeroBasedEditor(FakeOneBasedEditor):
    """Hypothetical 0-based control, to prove the row base is probed."""

    def GetLineText(self, index: int) -> str:  # noqa: N802
        if 0 <= index < len(self.lines):
            return self.lines[index]
        return ""

    def Delete(self) -> None:  # noqa: N802
        if self._selection is None:
            return
        start, end = self._selection
        start = max(start, 0)
        end = min(end, len(self.lines) - 1)
        if start <= end:
            del self.lines[start : end + 1]
        if not self.lines:
            self.lines = [""]
        self._selection = None


class StubbornEditor(FakeOneBasedEditor):
    """Refuses to delete its last line — stands in for a control we cannot clear."""

    def Delete(self) -> None:  # noqa: N802
        keep = self.lines[-1]
        super().Delete()
        self.lines.append(keep)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Keep the COM pacing sleeps out of the unit tests."""
    monkeypatch.setattr(_abap_editor.time, "sleep", lambda _seconds: None)


class TestDetectRowBase:
    def test_one_based_control_detected(self):
        shell = FakeOneBasedEditor(["REPORT ztest.", "WRITE 'x'."])
        assert _abap_editor.detect_row_base(shell, shell.GetLineCount()) == 1

    def test_zero_based_control_detected(self):
        shell = FakeZeroBasedEditor(["REPORT ztest.", "WRITE 'x'."])
        assert _abap_editor.detect_row_base(shell, shell.GetLineCount()) == 0

    def test_empty_buffer(self):
        assert _abap_editor.detect_row_base(FakeOneBasedEditor([]), 0) == 0


class TestReadLines:
    def test_reads_every_line_including_the_last(self):
        """The 0-based read dropped the last line and prepended a blank (#859)."""
        source = ENDFORM_SOURCE.split("\n")
        shell = FakeOneBasedEditor(source)
        assert _abap_editor.read_lines(shell) == source

    def test_reads_zero_based_control(self):
        source = ENDFORM_SOURCE.split("\n")
        assert _abap_editor.read_lines(FakeZeroBasedEditor(source)) == source

    def test_empty_buffer_reads_as_single_blank(self):
        assert _abap_editor.read_lines(FakeOneBasedEditor()) == [""]


class TestClear:
    def test_clears_the_last_line_too(self):
        """SelectRange(…, count - 1, …) left the last row behind (#859)."""
        shell = FakeOneBasedEditor(ENDFORM_SOURCE.split("\n"))
        assert _abap_editor.clear(shell) is True
        assert _abap_editor.is_empty(shell)

    def test_already_empty_is_a_noop(self):
        shell = FakeOneBasedEditor()
        assert _abap_editor.clear(shell) is True

    def test_reports_failure_when_buffer_cannot_be_emptied(self):
        assert _abap_editor.clear(StubbornEditor(["ENDFORM."])) is False


class TestWriteSource:
    def test_round_trips_source_ending_in_endform(self):
        """The #859 shape: no stale line may survive at the bottom."""
        shell = FakeOneBasedEditor(["REPORT ztest.", "ENDFORM."])
        assert _abap_editor.write_source(shell, ENDFORM_SOURCE) is True
        assert _abap_editor.normalize(_abap_editor.read_lines(shell)) == ENDFORM_SOURCE.split("\n")

    def test_does_not_duplicate_the_previous_last_line(self):
        shell = FakeOneBasedEditor(["REPORT ztest.", "* PREVIOUS LAST LINE"])
        _abap_editor.write_source(shell, ENDFORM_SOURCE)
        assert "* PREVIOUS LAST LINE" not in shell.lines

    def test_accepts_source_with_trailing_newline(self):
        shell = FakeOneBasedEditor()
        assert _abap_editor.write_source(shell, ENDFORM_SOURCE + "\n") is True
        assert _abap_editor.normalize(_abap_editor.read_lines(shell)) == ENDFORM_SOURCE.split("\n")

    def test_reports_failure_instead_of_silently_corrupting(self):
        """A buffer we cannot clear must surface as False, not as a bad write."""
        assert _abap_editor.write_source(StubbornEditor(["ENDFORM."]), ENDFORM_SOURCE) is False

    def test_writes_into_a_zero_based_control(self):
        shell = FakeZeroBasedEditor(["REPORT ztest.", "* PREVIOUS LAST LINE"])
        assert _abap_editor.write_source(shell, ENDFORM_SOURCE) is True
        assert _abap_editor.normalize(_abap_editor.read_lines(shell)) == ENDFORM_SOURCE.split("\n")


class TestNormalize:
    def test_strips_trailing_blank_lines_and_padding(self):
        assert _abap_editor.normalize(["a  ", "b", "", "  "]) == ["a", "b"]

    def test_keeps_interior_blank_lines(self):
        assert _abap_editor.normalize(["a", "", "b"]) == ["a", "", "b"]

    def test_empty_input(self):
        assert _abap_editor.normalize([]) == []
