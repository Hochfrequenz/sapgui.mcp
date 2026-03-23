"""Tests for GuiTextedit and GuiAbapEditor — issues #475, #516."""

from unittest.mock import MagicMock

from sapsucker.components.editor import GuiAbapEditor, GuiTextedit
from sapsucker.components.shell import GuiShell


def _make_textedit():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "TextEdit"
    return GuiTextedit(com)


def _make_abap_editor():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "AbapEditor"
    return GuiAbapEditor(com)


# ---------------------------------------------------------------------------
# GuiTextedit — pre-existing properties
# ---------------------------------------------------------------------------


class TestGuiTexteditPreExisting:
    def test_inherits_from_shell(self):
        te = _make_textedit()
        assert isinstance(te, GuiShell)

    def test_number_of_lines(self):
        te = _make_textedit()
        te._com.NumberOfLines = 42
        assert te.number_of_lines == 42

    def test_current_line(self):
        te = _make_textedit()
        te._com.CurrentLine = 10
        assert te.current_line == 10

    def test_current_column(self):
        te = _make_textedit()
        te._com.CurrentColumn = 5
        assert te.current_column == 5

    def test_selection_text(self):
        te = _make_textedit()
        te._com.SelectionText = "selected"
        assert te.selection_text == "selected"

    def test_is_read_only(self):
        te = _make_textedit()
        te._com.IsReadOnly = True
        assert te.is_read_only is True

    def test_get_line_text(self):
        te = _make_textedit()
        te._com.GetLineText.return_value = "REPORT z_test."
        assert te.get_line_text(0) == "REPORT z_test."
        te._com.GetLineText.assert_called_once_with(0)

    def test_set_selection_indexes(self):
        te = _make_textedit()
        te.set_selection_indexes(0, 10)
        te._com.SetSelectionIndexes.assert_called_once_with(0, 10)

    def test_press_f1(self):
        te = _make_textedit()
        te.press_f1()
        te._com.PressF1.assert_called_once()

    def test_press_f4(self):
        te = _make_textedit()
        te.press_f4()
        te._com.PressF4.assert_called_once()


# ---------------------------------------------------------------------------
# GuiTextedit — new methods from PR #521 (#475)
# ---------------------------------------------------------------------------


class TestGuiTexteditNewMethods:
    def test_first_visible_line_get(self):
        te = _make_textedit()
        te._com.FirstVisibleLine = 5
        assert te.first_visible_line == 5

    def test_first_visible_line_set(self):
        te = _make_textedit()
        te.first_visible_line = 10
        assert te._com.FirstVisibleLine == 10

    def test_last_visible_line(self):
        te = _make_textedit()
        te._com.LastVisibleLine = 25
        assert te.last_visible_line == 25

    def test_set_unprotected_text_part(self):
        te = _make_textedit()
        te._com.SetUnprotectedTextPart.return_value = True
        result = te.set_unprotected_text_part(0, "new text")
        te._com.SetUnprotectedTextPart.assert_called_once_with(0, "new text")
        assert result is True

    def test_set_unprotected_text_part_failure(self):
        te = _make_textedit()
        te._com.SetUnprotectedTextPart.return_value = False
        assert te.set_unprotected_text_part(0, "text") is False

    def test_get_unprotected_text_part(self):
        te = _make_textedit()
        te._com.GetUnprotectedTextPart.return_value = "text"
        assert te.get_unprotected_text_part(0) == "text"


# ---------------------------------------------------------------------------
# GuiAbapEditor — all methods
# ---------------------------------------------------------------------------


class TestGuiAbapEditor:
    def test_inherits_from_shell(self):
        ed = _make_abap_editor()
        assert isinstance(ed, GuiShell)

    def test_get_line_count(self):
        ed = _make_abap_editor()
        ed._com.GetLineCount.return_value = 100
        assert ed.get_line_count() == 100

    def test_get_line_text(self):
        ed = _make_abap_editor()
        ed._com.GetLineText.return_value = "DATA lv_test TYPE string."
        assert ed.get_line_text(1) == "DATA lv_test TYPE string."
        ed._com.GetLineText.assert_called_once_with(1)

    def test_set_selection_indexes(self):
        ed = _make_abap_editor()
        ed.set_selection_indexes(5, 20)
        ed._com.SetSelectionIndexes.assert_called_once_with(5, 20)

    def test_press_f1(self):
        ed = _make_abap_editor()
        ed.press_f1()
        ed._com.PressF1.assert_called_once()

    def test_first_visible_line_get(self):
        ed = _make_abap_editor()
        ed._com.FirstVisibleLine = 5
        assert ed.first_visible_line == 5

    def test_first_visible_line_set(self):
        ed = _make_abap_editor()
        ed.first_visible_line = 10
        assert ed._com.FirstVisibleLine == 10

    def test_last_visible_line(self):
        ed = _make_abap_editor()
        ed._com.LastVisibleLine = 25
        assert ed.last_visible_line == 25

    def test_is_read_only(self):
        ed = _make_abap_editor()
        ed._com.IsReadOnly = True
        assert ed.is_read_only is True
