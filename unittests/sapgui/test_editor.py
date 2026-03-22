"""Tests for editor missing methods — issue #475."""

from unittest.mock import MagicMock

from sapwebguimcp.sapgui.components.editor import GuiAbapEditor, GuiTextedit


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


class TestGuiTexteditMissing:
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

    def test_get_unprotected_text_part(self):
        te = _make_textedit()
        te._com.GetUnprotectedTextPart.return_value = "text"
        assert te.get_unprotected_text_part(0) == "text"


class TestGuiAbapEditorMissing:
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
