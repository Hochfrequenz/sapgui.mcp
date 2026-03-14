"""Shared fixtures for sapgui unit tests."""

from unittest.mock import MagicMock, PropertyMock

import pytest


def make_mock_com(
    type_as_number: int = 1,
    type_name: str = "GuiVComponent",
    id: str = "/app/con[0]/ses[0]/wnd[0]/usr/txtFIELD",
    name: str = "txtFIELD",
    container_type: bool = False,
    text: str = "",
    tooltip: str = "",
    changeable: bool = True,
    parent: MagicMock | None = None,
    height: int = 20,
    width: int = 100,
    left: int = 0,
    top: int = 0,
    screen_left: int = 0,
    screen_top: int = 0,
    modified: bool = False,
    icon_name: str = "",
    is_symbol_font: bool = False,
    acc_text: str = "",
    acc_tooltip: str = "",
    acc_text_on_request: str = "",
    default_tooltip: str = "",
    children: list[MagicMock] | None = None,
    **extra_props,
) -> MagicMock:
    """Create a MagicMock simulating a SAP GUI COM dispatch object.

    Args:
        type_as_number: The SAP GUI component type number.
        type_name: The SAP GUI component type name string.
        id: Full SAP GUI element ID path.
        name: Short element name.
        container_type: Whether this element is a container.
        text: Element text content.
        tooltip: Element tooltip.
        changeable: Whether the element is editable.
        parent: Parent mock COM object.
        height: Element height in pixels.
        width: Element width in pixels.
        left: Left position relative to parent.
        top: Top position relative to parent.
        screen_left: Absolute left position on screen.
        screen_top: Absolute top position on screen.
        modified: Whether the element has been modified.
        icon_name: Icon name string.
        is_symbol_font: Whether element uses symbol font.
        acc_text: Accessibility text.
        acc_tooltip: Accessibility tooltip.
        acc_text_on_request: Accessibility text on request.
        default_tooltip: Default tooltip text.
        children: List of child mock COM objects for containers.
        **extra_props: Additional properties to set on the mock.

    Returns:
        A MagicMock configured with SAP GUI COM properties.
    """
    mock = MagicMock()
    mock.TypeAsNumber = type_as_number
    mock.Type = type_name
    mock.Id = id
    mock.Name = name
    mock.ContainerType = container_type
    mock.Text = text
    mock.Tooltip = tooltip
    mock.Changeable = changeable
    mock.Parent = parent
    mock.Height = height
    mock.Width = width
    mock.Left = left
    mock.Top = top
    mock.ScreenLeft = screen_left
    mock.ScreenTop = screen_top
    mock.Modified = modified
    mock.IconName = icon_name
    mock.IsSymbolFont = is_symbol_font
    mock.AccText = acc_text
    mock.AccTooltip = acc_tooltip
    mock.AccTextOnRequest = acc_text_on_request
    mock.DefaultTooltip = default_tooltip

    if children is not None:
        mock.Children = MagicMock()
        mock.Children.Count = len(children)
        mock.Children.Item = lambda i: children[i]
        mock.Children.__iter__ = lambda self: iter(children)
        mock.Children.__len__ = lambda self: len(children)
    else:
        mock.Children = None

    for key, value in extra_props.items():
        setattr(mock, key, value)

    return mock


@pytest.fixture
def mock_com():
    """Return a default mock COM object."""
    return make_mock_com()
