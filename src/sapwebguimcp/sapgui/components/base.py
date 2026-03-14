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

    def find_by_id(self, id: str, raise_error: bool = True) -> GuiComponent | None:
        """Find a child element by its ID path, wrapped in the correct Python class.

        Args:
            id: The SAP GUI element ID path (e.g. 'usr/txtFIELD').
            raise_error: If True (default), raise ElementNotFoundError when not found.

        Returns:
            The wrapped component, or None if not found and raise_error is False.
        """
        from sapwebguimcp.sapgui._factory import wrap_com_object

        result = self._com.FindById(id, False)
        if result is None:
            if raise_error:
                raise ElementNotFoundError(f"Element not found: {id}")
            return None
        return wrap_com_object(result)


def _safe_com_attr(com_obj, attr: str, default=None):
    """Safely get a COM attribute, returning default on any error.

    Unlike getattr(), this catches COM errors (pywintypes.com_error)
    which are not AttributeError and thus bypass getattr's default.
    """
    try:
        return getattr(com_obj, attr)
    except Exception:
        return default


def _dump_tree_recursive(com_obj, depth: int, max_depth: int):
    """Recursively walk COM children and build a list of ElementInfo."""
    from sapwebguimcp.sapgui.models import ElementInfo

    result = []
    try:
        children_com = com_obj.Children
        count = children_com.Count
    except Exception:
        return result
    for i in range(count):
        try:
            child = children_com.Item(i)
        except Exception:
            continue
        child_info = ElementInfo(
            id=str(_safe_com_attr(child, "Id", "")),
            type=str(_safe_com_attr(child, "Type", "")),
            type_as_number=int(_safe_com_attr(child, "TypeAsNumber", 0)),
            name=str(_safe_com_attr(child, "Name", "")),
            text=str(_safe_com_attr(child, "Text", "")),
            changeable=bool(_safe_com_attr(child, "Changeable", False)),
            children=(
                _dump_tree_recursive(child, depth + 1, max_depth)
                if depth + 1 < max_depth and _safe_com_attr(child, "ContainerType", False)
                else []
            ),
        )
        result.append(child_info)
    return result


class GuiVContainer(GuiContainer, GuiVComponent):
    """Wraps the COM GuiVContainer interface — visual container with children and layout."""

    def dump_tree(self, max_depth: int = 10):
        """Return a recursive tree of ElementInfo for all children.

        Args:
            max_depth: Maximum recursion depth (default 10).

        Returns:
            A list of ElementInfo representing the child tree.
        """
        return _dump_tree_recursive(self._com, 0, max_depth)

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
