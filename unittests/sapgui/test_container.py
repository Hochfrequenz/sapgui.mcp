"""Tests for GuiScrollbar — issue #478."""

from unittest.mock import MagicMock

from sapsucker.components.container import GuiScrollbar, GuiUserArea


def _make_scrollbar():
    com = MagicMock()
    return GuiScrollbar(com)


def _make_user_area():
    com = MagicMock()
    com.TypeAsNumber = 74
    return GuiUserArea(com)


class TestGuiScrollbar:
    def test_minimum(self):
        sb = _make_scrollbar()
        sb._com.Minimum = 0
        assert sb.minimum == 0

    def test_maximum(self):
        sb = _make_scrollbar()
        sb._com.Maximum = 100
        assert sb.maximum == 100

    def test_position_get(self):
        sb = _make_scrollbar()
        sb._com.Position = 42
        assert sb.position == 42

    def test_position_set(self):
        sb = _make_scrollbar()
        sb.position = 10
        assert sb._com.Position == 10

    def test_page_size(self):
        sb = _make_scrollbar()
        sb._com.PageSize = 20
        assert sb.page_size == 20

    def test_repr(self):
        sb = _make_scrollbar()
        sb._com.Position = 5
        sb._com.Minimum = 0
        sb._com.Maximum = 100
        assert "pos=5" in repr(sb)


class TestGuiUserAreaScrollbars:
    def test_vertical_scrollbar_returns_typed(self):
        ua = _make_user_area()
        ua._com.VerticalScrollbar = MagicMock()
        result = ua.vertical_scrollbar
        assert isinstance(result, GuiScrollbar)

    def test_horizontal_scrollbar_returns_typed(self):
        ua = _make_user_area()
        ua._com.HorizontalScrollbar = MagicMock()
        result = ua.horizontal_scrollbar
        assert isinstance(result, GuiScrollbar)
