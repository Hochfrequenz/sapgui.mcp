"""Editor components — GuiTextedit and GuiAbapEditor."""

from __future__ import annotations

from sapsucker.components.shell import GuiShell

__all__ = ["GuiAbapEditor", "GuiTextedit"]


class GuiTextedit(GuiShell):
    """Wraps the COM GuiTextedit shell (SubType 'TextEdit').

    A multi-line text editor control.
    """

    @property
    def number_of_lines(self) -> int:
        """Total number of lines in the editor."""
        return int(self._com.NumberOfLines)

    @property
    def current_line(self) -> int:
        """Current cursor line number."""
        return int(self._com.CurrentLine)

    @property
    def current_column(self) -> int:
        """Current cursor column number."""
        return int(self._com.CurrentColumn)

    @property
    def selection_text(self) -> str:
        """Currently selected text."""
        return str(self._com.SelectionText)

    @property
    def is_read_only(self) -> bool:
        """Whether the editor is in read-only mode."""
        return bool(self._com.IsReadOnly)

    def get_line_text(self, line: int) -> str:
        """Return the text of a specific line (0-based)."""
        return str(self._com.GetLineText(line))

    def set_selection_indexes(self, start: int, end: int) -> None:
        """Set the text selection by character indexes."""
        self._com.SetSelectionIndexes(start, end)

    def press_f1(self) -> None:
        """Press F1 (help) in the editor."""
        self._com.PressF1()

    def press_f4(self) -> None:
        """Press F4 (value help) in the editor."""
        self._com.PressF4()

    @property
    def first_visible_line(self) -> int:
        """First visible line in the editor viewport."""
        return int(self._com.FirstVisibleLine)

    @first_visible_line.setter
    def first_visible_line(self, value: int) -> None:
        self._com.FirstVisibleLine = value

    @property
    def last_visible_line(self) -> int:
        """Last visible line in the editor viewport (read-only)."""
        return int(self._com.LastVisibleLine)

    def set_unprotected_text_part(self, part: int, text: str) -> bool:
        """Set the text of an unprotected text part by index.

        Returns True on success, False on failure.
        """
        return bool(self._com.SetUnprotectedTextPart(part, text))

    def get_unprotected_text_part(self, part: int) -> str:
        """Get the text of an unprotected text part by index."""
        return str(self._com.GetUnprotectedTextPart(part))


class GuiAbapEditor(GuiShell):
    """Wraps the COM GuiAbapEditor shell (SubType 'AbapEditor').

    The ABAP source code editor control used in SE38, SE80, etc.

    Note: Unlike ``GuiTextedit``, the AbapEditor COM control exposes
    ``GetLineCount()`` (method) rather than a ``NumberOfLines`` property,
    and does **not** have ``CurrentLine``, ``CurrentColumn``, or
    ``SelectionText`` properties.
    """

    def get_line_count(self) -> int:
        """Return the total number of lines in the editor."""
        return int(self._com.GetLineCount())

    def get_line_text(self, line: int) -> str:
        """Return the text of a specific line (0-based)."""
        return str(self._com.GetLineText(line))

    def set_selection_indexes(self, start: int, end: int) -> None:
        """Set the text selection by character indexes."""
        self._com.SetSelectionIndexes(start, end)

    def press_f1(self) -> None:
        """Press F1 (help) in the editor."""
        self._com.PressF1()

    @property
    def first_visible_line(self) -> int:
        """First visible line in the editor viewport."""
        return int(self._com.FirstVisibleLine)

    @first_visible_line.setter
    def first_visible_line(self, value: int) -> None:
        self._com.FirstVisibleLine = value

    @property
    def last_visible_line(self) -> int:
        """Last visible line in the editor viewport (read-only)."""
        return int(self._com.LastVisibleLine)

    @property
    def is_read_only(self) -> bool:
        """Whether the editor is in read-only mode."""
        return bool(self._com.IsReadOnly)
