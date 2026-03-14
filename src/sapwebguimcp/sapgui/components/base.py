"""Base classes for the SAP GUI component hierarchy."""

from __future__ import annotations

from sapwebguimcp.sapgui._errors import ElementNotFoundError


class GuiComponent:
    """Wraps the COM GuiComponent interface — the root of the SAP GUI type tree."""

    def __init__(self, com_object) -> None:
        self._com = com_object

    @property
    def com(self):
        """Return the underlying COM dispatch object."""
        return self._com

    @property
    def id(self) -> str:
        return self._com.Id

    @property
    def name(self) -> str:
        return self._com.Name

    @property
    def type(self) -> str:
        return self._com.Type

    @property
    def type_as_number(self) -> int:
        return self._com.TypeAsNumber

    @property
    def container_type(self) -> bool:
        return self._com.ContainerType

    @property
    def parent(self):
        return self._com.Parent

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self._com.Type!r}, id={self._com.Id!r})"


class GuiVComponent(GuiComponent):
    """Wraps the COM GuiVComponent interface — visual component with layout properties."""

    @property
    def text(self) -> str:
        return self._com.Text

    @text.setter
    def text(self, value: str) -> None:
        self._com.Text = value

    @property
    def tooltip(self) -> str:
        return self._com.Tooltip

    @property
    def default_tooltip(self) -> str:
        return self._com.DefaultTooltip

    @property
    def changeable(self) -> bool:
        return self._com.Changeable

    @property
    def modified(self) -> bool:
        return self._com.Modified

    @property
    def height(self) -> int:
        return self._com.Height

    @property
    def width(self) -> int:
        return self._com.Width

    @property
    def left(self) -> int:
        return self._com.Left

    @property
    def top(self) -> int:
        return self._com.Top

    @property
    def screen_left(self) -> int:
        return self._com.ScreenLeft

    @property
    def screen_top(self) -> int:
        return self._com.ScreenTop

    @property
    def icon_name(self) -> str:
        return self._com.IconName

    @property
    def is_symbol_font(self) -> bool:
        return self._com.IsSymbolFont

    @property
    def acc_text(self) -> str:
        return self._com.AccText

    @property
    def acc_tooltip(self) -> str:
        return self._com.AccTooltip

    @property
    def acc_text_on_request(self) -> str:
        return self._com.AccTextOnRequest

    def set_focus(self) -> None:
        """Set keyboard focus to this element."""
        self._com.SetFocus()

    def visualize(self, on: bool) -> None:
        """Highlight or unhighlight this element."""
        self._com.Visualize(on)

    def dump_state(self, inner_object: str):
        """Return a collection of element state properties."""
        return self._com.DumpState(inner_object)


class GuiContainer(GuiComponent):
    """Wraps the COM GuiContainer interface — non-visual container with children."""

    @property
    def children(self):
        """Return the COM Children collection."""
        return self._com.Children

    def find_by_id(self, id: str, raise_error: bool = True):
        """Find a child element by its ID path. Returns raw COM object.

        This is a temporary implementation that returns raw COM objects.
        It will be updated in Task 6 to wrap results via the factory.
        """
        result = self._com.FindById(id, False)
        if result is None:
            if raise_error:
                raise ElementNotFoundError(f"Element not found: {id}")
            return None
        return result


class GuiVContainer(GuiContainer, GuiVComponent):
    """Wraps the COM GuiVContainer interface — visual container with children and layout."""

    def find_by_name(self, name: str, type_name: str):
        """Find a child element by name and type name string."""
        return self._com.FindByName(name, type_name)

    def find_by_name_ex(self, name: str, type_number: int):
        """Find a child element by name and type number."""
        return self._com.FindByNameEx(name, type_number)

    def find_all_by_name(self, name: str, type_name: str):
        """Find all child elements matching name and type name string."""
        return self._com.FindAllByName(name, type_name)

    def find_all_by_name_ex(self, name: str, type_number: int):
        """Find all child elements matching name and type number."""
        return self._com.FindAllByNameEx(name, type_number)
