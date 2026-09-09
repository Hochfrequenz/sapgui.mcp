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
        assert _abap_editor.write_source(shell, ENDFORM_SOURCE) is True
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


class RaisingOneBasedEditor(FakeOneBasedEditor):
    """1-based control that raises on out-of-range indices, as real COM does."""

    def GetLineText(self, index: int) -> str:  # noqa: N802
        if 1 <= index <= len(self.lines):
            return self.lines[index - 1]
        raise RuntimeError(f"index out of range: {index}")


class RaisingZeroBasedEditor(FakeZeroBasedEditor):
    """0-based control that raises on out-of-range indices."""

    def GetLineText(self, index: int) -> str:  # noqa: N802
        if 0 <= index < len(self.lines):
            return self.lines[index]
        raise RuntimeError(f"index out of range: {index}")


class TruncatingTextEdit:
    """GuiTextedit that clips every line to a fixed width, as the control does."""

    def __init__(self, width: int = 72) -> None:
        self.width = width
        self.Text = ""

    def __setattr__(self, name: str, value: object) -> None:
        if name == "Text" and isinstance(value, str):
            normalized = value.replace("\r\n", "\n").replace("\r", "\n")
            clipped = "\r".join(line[: self.width] for line in normalized.split("\n"))
            object.__setattr__(self, "Text", clipped)
            return
        object.__setattr__(self, name, value)


class TestRowBaseWithRaisingControls:
    """An out-of-range index that raises is the most conclusive signal."""

    def test_one_based(self):
        shell = RaisingOneBasedEditor(["REPORT ztest.", "WRITE 'x'."])
        assert _abap_editor.detect_row_base(shell, shell.GetLineCount()) == 1
        assert _abap_editor.read_lines(shell) == ["REPORT ztest.", "WRITE 'x'."]

    def test_zero_based(self):
        shell = RaisingZeroBasedEditor(["REPORT ztest.", "WRITE 'x'."])
        assert _abap_editor.detect_row_base(shell, shell.GetLineCount()) == 0
        assert _abap_editor.read_lines(shell) == ["REPORT ztest.", "WRITE 'x'."]

    def test_zero_based_with_blank_first_line(self):
        """The ambiguous case: a raising control resolves it conclusively."""
        shell = RaisingZeroBasedEditor(["", "REPORT ztest."])
        assert _abap_editor.detect_row_base(shell, shell.GetLineCount()) == 0
        assert _abap_editor.read_lines(shell) == ["", "REPORT ztest."]


class TestWriteSurvivesRowBaseAmbiguity:
    def test_zero_based_blank_first_line_still_verifies(self):
        """A mis-probed base must not report corruption for a correct buffer."""
        shell = FakeZeroBasedEditor(["OLD."])
        source = "\nREPORT ztest.\nWRITE 'x'."
        assert _abap_editor.write_source(shell, source) is True
        assert shell.lines[:3] == ["", "REPORT ztest.", "WRITE 'x'."]

    def test_row_base_override_is_respected(self):
        shell = FakeZeroBasedEditor(["REPORT ztest.", "WRITE 'x'."])
        assert _abap_editor.read_lines(shell, row_base=0) == ["REPORT ztest.", "WRITE 'x'."]


class TestMatches:
    def test_detects_a_changed_middle_line(self):
        shell = FakeOneBasedEditor(["REPORT ztest.", "WRITE 'WRONG'.", "ENDFORM."])
        expected = ["REPORT ztest.", "WRITE 'right'.", "ENDFORM."]
        assert _abap_editor.matches(shell, expected) is False

    def test_detects_a_stale_trailing_line(self):
        """The #859 corruption, under either row base."""
        shell = FakeOneBasedEditor(["REPORT ztest.", "ENDFORM.", "* STALE"])
        assert _abap_editor.matches(shell, ["REPORT ztest.", "ENDFORM."]) is False


class TestWriteTextProperty:
    def test_writes_and_confirms(self):
        shell = TruncatingTextEdit()
        assert _abap_editor.write_text_property(shell, "REPORT ztest.\nWRITE 'x'.") is True
        assert shell.Text == "REPORT ztest.\rWRITE 'x'."

    def test_truncation_is_advisory_not_a_failure(self, caplog):
        """The control's line width is unmeasured, so a mismatch must not fail the write."""
        shell = TruncatingTextEdit(width=20)
        long_source = "REPORT ztest.\nWRITE '" + "A" * 100 + "'."
        assert _abap_editor.write_text_property(shell, long_source) is True
        assert "text_edit_write_mismatch" in caplog.text

    def test_control_name_readback_is_tolerated(self):
        class NameEcho:
            Text = ""

            def __setattr__(self, name, value):
                object.__setattr__(self, "Text", "SAPGUI.TextEdit.1")

        assert _abap_editor.write_text_property(NameEcho(), "REPORT ztest.") is True


class TestFirstDiff:
    def test_reports_the_first_differing_line(self):
        assert "line 2" in _abap_editor._first_diff(["a", "b"], ["a", "c"])

    def test_reports_a_missing_line(self):
        assert "<missing>" in _abap_editor._first_diff(["a", "b"], ["a"])

    def test_identical_input_has_no_diff(self):
        assert _abap_editor._first_diff(["a"], ["a"]) == ""
