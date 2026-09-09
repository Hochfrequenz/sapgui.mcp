"""Line access for the SAP GUI source-code editor controls (issue #859).

The ``GuiAbapEditor`` control ("Quellcode-basierter Editor" / source-code-based
editor) numbers its rows **1-based**: ``GetLineText(0)`` returns an empty
phantom row and the last real line sits at index ``GetLineCount()``.  Treating
the rows as 0-based — as this backend originally did — has two consequences:

* reading walks ``0 .. count-1``, so it prepends a blank line and silently
  **drops the last line** of the source;
* ``SelectRange(0, 0, count - 1, ...)`` never covers the last row, so that row
  survives ``Delete()`` and, because ``InsertText`` writes at the top of the
  buffer, ends up appended *after* the newly written source.

That second effect is issue #859: every ``sap_se38_edit`` call left a stale
copy of the previous source's last line at the end of the program.

Other kernels / control versions may well be 0-based, so the row base is
probed at runtime rather than hard-coded.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

#: Column passed to ``SelectRange`` to mean "end of line" — SAP clamps it.
MAX_COL = 9999

#: How many clear passes to attempt before giving up on emptying the buffer.
MAX_CLEAR_PASSES = 5

#: How many full clear+insert attempts before reporting failure.
MAX_WRITE_ATTEMPTS = 2


def _line_text(shell: Any, index: int) -> str | None:
    """Return ``GetLineText(index)``, or ``None`` when the call raises.

    ``None`` means "this index is not addressable" and is deliberately kept
    distinct from ``""`` ("this row exists and is empty") — the row base is
    probed from exactly that difference.
    """
    try:
        return str(shell.GetLineText(index))
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def detect_row_base(shell: Any, count: int) -> int:
    """Return the index of the editor's first row: ``1`` (1-based) or ``0``.

    Decided in order of how conclusive the signal is:

    1. an index that raises is out of range — if index ``0`` raises the rows
       are 1-based, if index ``count`` raises they are 0-based;
    2. a non-empty row at index ``count`` can only exist on a 1-based control,
       because on a 0-based one that index is already past the end;
    3. otherwise the phantom row at index ``0`` decides: it is always empty on
       a 1-based control.

    One case stays ambiguous: a 0-based control whose first line is blank.
    Reads then drop that blank and pick up a trailing one; writes are immune
    because :func:`matches` accepts either interpretation.
    """
    if count <= 0:
        return 0
    if _line_text(shell, 0) is None:
        return 1
    if _line_text(shell, count) is None:
        return 0
    if _line_text(shell, count):
        return 1
    return 1 if _line_text(shell, 0) == "" else 0


def read_lines(shell: Any, row_base: int | None = None) -> list[str]:
    """Read every line of a source-code editor buffer, in order.

    ``row_base`` overrides the probe — pass ``0`` for controls that are known
    to be 0-based (``GuiTextedit``) so they never go through the heuristic.
    """
    count = int(shell.GetLineCount())
    if count <= 0:
        return []
    base = detect_row_base(shell, count) if row_base is None else row_base
    # Nothing may exist past the last line.  If something does, the base is
    # wrong and this read is dropping a line — loud, because `backup_source`
    # is built from it and auto-revert would write the truncated result back.
    beyond = _line_text(shell, base + count)
    if beyond:
        logger.warning(
            "abap_editor_row_base_suspect",
            extra={"row_base": base, "count": count, "beyond_last_line": beyond},
        )
    return [_line_text(shell, i) or "" for i in range(base, base + count)]


def matches(shell: Any, expected: list[str]) -> bool:
    """True when the buffer equals ``expected`` under *any* plausible row base.

    Verification must not fail merely because the row base was probed wrongly:
    a mis-probe would report corruption for a buffer that is in fact correct.
    Accepting either base costs nothing in detection power — the stale trailing
    line of #859 does not match under either reading.
    """
    count = int(shell.GetLineCount())
    if count <= 0:
        return not expected
    bases = {detect_row_base(shell, count), 0, 1}
    return any(normalize(read_lines(shell, row_base=base)) == expected for base in bases)


def normalize(lines: list[str]) -> list[str]:
    """Strip trailing whitespace per line and drop trailing blank lines.

    The editor pads and trims its own buffer, so these differences are not
    corruption and must not fail the write verification.
    """
    stripped = [line.rstrip() for line in lines]
    while stripped and not stripped[-1]:
        stripped.pop()
    return stripped


def is_empty(shell: Any) -> bool:
    """True when the editor buffer holds no non-whitespace content.

    Deliberately cheap: a full :func:`read_lines` costs one cross-process COM
    round trip per line, and this runs on every clear pass.
    """
    if int(shell.GetLineCount()) > 1:
        return False
    # A buffer of at most one row — check both candidate row bases.
    return not (_line_text(shell, 0) or "").strip() and not (_line_text(shell, 1) or "").strip()


def clear(shell: Any, pause: float = 0.1) -> bool:
    """Delete the whole buffer.  Returns True when it ends up empty.

    The end row is ``GetLineCount()`` rather than ``count - 1`` so the
    selection also covers the last row on a 1-based control.
    """
    for _ in range(MAX_CLEAR_PASSES):
        if is_empty(shell):
            return True
        count = int(shell.GetLineCount())
        shell.SelectRange(0, 0, count, MAX_COL)
        time.sleep(pause)
        shell.Delete()
        time.sleep(pause)
    return is_empty(shell)


def write_source(shell: Any, code: str, pause: float = 0.1) -> bool:
    """Replace the buffer with ``code`` and verify the result.

    Returns ``False`` when the buffer does not match ``code`` afterwards, so a
    partial write surfaces as a failure instead of silently corrupting the
    source (issue #859).
    """
    expected = normalize(code.split("\n"))
    # InsertText drops the segment after the final newline, so always end with one.
    insert_code = code if code.endswith("\n") else code + "\n"

    for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
        if not clear(shell, pause=pause):
            logger.warning("abap_editor_clear_incomplete", extra={"attempt": attempt})
            continue
        shell.InsertText(insert_code, 0, 0)
        time.sleep(pause * 2)
        if matches(shell, expected):
            return True
        actual = normalize(read_lines(shell))
        logger.warning(
            "abap_editor_write_mismatch",
            extra={
                "attempt": attempt,
                "expected_lines": len(expected),
                "actual_lines": len(actual),
                "first_diff": _first_diff(expected, actual),
            },
        )
    return False


def write_text_property(shell: Any, code: str) -> bool:
    """Replace a ``GuiTextedit`` buffer via its ``Text`` property.

    ``GuiTextedit`` separates lines with ``\\r``.  Some controls answer ``Text``
    with their own control name instead of the content.

    The read-back is **advisory only** and never fails the write: unlike the
    ``GuiAbapEditor`` path, this control's normalisation (line-width padding
    and truncation) has not been measured, so treating a mismatch as an error
    would risk rejecting sources that write perfectly well today.  A mismatch
    is logged so it can be investigated before this is tightened.
    """
    shell.Text = code
    written = str(shell.Text)
    if written.startswith("SAPGUI."):
        return True
    expected = normalize(code.split("\n"))
    actual = normalize(written.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    if actual != expected:
        logger.warning(
            "text_edit_write_mismatch",
            extra={
                "expected_lines": len(expected),
                "actual_lines": len(actual),
                "first_diff": _first_diff(expected, actual),
            },
        )
    return True


def _first_diff(expected: list[str], actual: list[str]) -> str:
    """Describe the first differing line, for logging."""
    for i in range(max(len(expected), len(actual))):
        exp = expected[i] if i < len(expected) else "<missing>"
        act = actual[i] if i < len(actual) else "<missing>"
        if exp != act:
            return f"line {i + 1}: expected {exp!r}, got {act!r}"
    return ""
