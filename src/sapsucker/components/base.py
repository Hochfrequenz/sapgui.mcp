"""Base classes for the SAP GUI component hierarchy."""

# pylint: disable=import-outside-toplevel,broad-exception-caught

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sapsucker._errors import ElementNotFoundError

if TYPE_CHECKING:
    from sapsucker.components.collection import GuiComponentCollection
    from sapsucker.models import ElementInfo

__all__ = ["GuiComponent", "GuiContainer", "GuiVComponent", "GuiVContainer"]


class GuiComponent:
    """Wraps the COM GuiComponent interface — the root of the SAP GUI type tree."""

    def __init__(self, com_object: Any) -> None:
        self._com = com_object

    @property
    def com(self) -> Any:
        """Return the underlying COM dispatch object."""
        return self._com

    @property
    def id(self) -> str:
        """Unique technical identifier of this element."""
        return str(self._com.Id)

    @property
    def name(self) -> str:
        """Short name of this element."""
        return str(self._com.Name)

    @property
    def type(self) -> str:
        """SAP GUI type name string."""
        return str(self._com.Type)

    @property
    def type_as_number(self) -> int:
        """Numeric type identifier."""
        return int(self._com.TypeAsNumber)

    @property
    def container_type(self) -> bool:
        """Whether this element can contain children."""
        return bool(self._com.ContainerType)

    @property
    def parent(self) -> Any:
        """Parent COM object in the element hierarchy."""
        return self._com.Parent

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self._com.Type!r}, id={self._com.Id!r})"


class GuiVComponent(GuiComponent):
    """Wraps the COM GuiVComponent interface — visual component with layout properties."""

    @property
    def text(self) -> str:
        """Display text of this element."""
        return str(self._com.Text)

    @text.setter
    def text(self, value: str) -> None:
        self._com.Text = value

    @property
    def tooltip(self) -> str:
        """Tooltip text."""
        return str(self._com.Tooltip)

    @property
    def default_tooltip(self) -> str:
        """Default tooltip text."""
        return str(self._com.DefaultTooltip)

    @property
    def changeable(self) -> bool:
        """Whether the element is currently editable."""
        return bool(self._com.Changeable)

    @property
    def modified(self) -> bool:
        """Whether the element value has been modified."""
        return bool(self._com.Modified)

    @property
    def height(self) -> int:
        """Height in pixels."""
        return int(self._com.Height)

    @property
    def width(self) -> int:
        """Width in pixels."""
        return int(self._com.Width)

    @property
    def left(self) -> int:
        """Left position in pixels."""
        return int(self._com.Left)

    @property
    def top(self) -> int:
        """Top position in pixels."""
        return int(self._com.Top)

    @property
    def screen_left(self) -> int:
        """Absolute screen left position in pixels."""
        return int(self._com.ScreenLeft)

    @property
    def screen_top(self) -> int:
        """Absolute screen top position in pixels."""
        return int(self._com.ScreenTop)

    @property
    def icon_name(self) -> str:
        """Name of the associated icon."""
        return str(self._com.IconName)

    @property
    def is_symbol_font(self) -> bool:
        """Whether the element uses symbol font."""
        return bool(self._com.IsSymbolFont)

    @property
    def acc_text(self) -> str:
        """Accessibility text."""
        return str(self._com.AccText)

    @property
    def acc_tooltip(self) -> str:
        """Accessibility tooltip."""
        return str(self._com.AccTooltip)

    @property
    def acc_text_on_request(self) -> str:
        """Accessibility text available on request."""
        return str(self._com.AccTextOnRequest)

    def set_focus(self) -> None:
        """Set keyboard focus to this element."""
        self._com.SetFocus()

    def visualize(self, on: bool) -> None:
        """Highlight or unhighlight this element."""
        self._com.Visualize(on)

    def dump_state(self, inner_object: str) -> Any:
        """Return a collection of element state properties."""
        return self._com.DumpState(inner_object)


class GuiContainer(GuiComponent):
    """Wraps the COM GuiContainer interface — non-visual container with children."""

    @property
    def children(self) -> GuiComponentCollection:
        """Return the children wrapped in a GuiComponentCollection."""
        from sapsucker.components.collection import GuiComponentCollection

        return GuiComponentCollection(self._com.Children)

    def find_by_id(self, id: str, raise_error: bool = True) -> GuiComponent | None:  # pylint: disable=redefined-builtin
        """Find a child element by its ID path, wrapped in the correct Python class.

        Args:
            id: The SAP GUI element ID path (e.g. 'usr/txtFIELD').
            raise_error: If True (default), raise ElementNotFoundError when not found.

        Returns:
            The wrapped component, or None if not found and raise_error is False.
        """
        from sapsucker._factory import wrap_com_object

        result = self._com.FindById(id, False)
        if result is None:
            if raise_error:
                raise ElementNotFoundError(f"Element not found: {id}")
            return None
        return wrap_com_object(result)


def _safe_com_attr(com_obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get a COM attribute, returning default on any error.

    Unlike getattr(), this catches COM errors (pywintypes.com_error)
    which are not AttributeError and thus bypass getattr's default.
    """
    try:
        return getattr(com_obj, attr)
    except Exception:
        return default


# SAP GUI type numbers for BDT field probe
_BDT_PROBE_TYPES = [
    31,  # GuiTextField
    32,  # GuiCTextField (context/search field)
    33,  # GuiPasswordField
    34,  # GuiComboBox
    42,  # GuiRadioButton
    43,  # GuiCheckBox
    46,  # GuiLabel
]


def _probe_bdt_fields(com_obj: Any) -> list[ElementInfo]:
    """Discover fields on BDT containers via FindAllByNameEx wildcard.

    BDT-based screens (e.g. BP) don't expose children via the standard
    Children collection. Fields ARE accessible via FindAllByNameEx("*", type_num).
    """
    from sapsucker.models import ElementInfo

    seen_ids: set[str] = set()
    result: list[ElementInfo] = []
    for type_num in _BDT_PROBE_TYPES:
        try:
            found = com_obj.FindAllByNameEx("*", type_num)
            for j in range(found.Count):
                child = found.Item(j)
                child_id = str(_safe_com_attr(child, "Id", ""))
                if child_id in seen_ids:
                    continue
                seen_ids.add(child_id)
                result.append(
                    ElementInfo(
                        id=child_id,
                        type=str(_safe_com_attr(child, "Type", "")),
                        type_as_number=int(_safe_com_attr(child, "TypeAsNumber", 0)),
                        name=str(_safe_com_attr(child, "Name", "")),
                        text=str(_safe_com_attr(child, "Text", "")),
                        changeable=bool(_safe_com_attr(child, "Changeable", False)),
                        children=[],
                    )
                )
        except Exception:
            pass
    return result


def _dump_tree_recursive(com_obj: Any, depth: int, max_depth: int) -> list[ElementInfo]:
    """Recursively walk COM children and build a list of ElementInfo."""
    from sapsucker.models import ElementInfo

    result: list[ElementInfo] = []
    try:
        children_com = com_obj.Children
        count = children_com.Count
    except Exception:
        count = 0  # BDT containers throw here — treat as empty

    if count > 0:
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
    elif _safe_com_attr(com_obj, "ContainerType", False):
        # BDT fallback: probe for hidden fields when container has no standard children
        obj_id = str(_safe_com_attr(com_obj, "Id", ""))
        if "/usr" in obj_id.lower():
            result.extend(_probe_bdt_fields(com_obj))

    return result


class GuiVContainer(GuiContainer, GuiVComponent):
    """Wraps the COM GuiVContainer interface — visual container with children and layout."""

    def dump_tree(self, max_depth: int = 20) -> list[ElementInfo]:
        """Return a recursive tree of ElementInfo for all children.

        Args:
            max_depth: Maximum recursion depth (default 20).

        Returns:
            A list of ElementInfo representing the child tree.
        """
        return _dump_tree_recursive(self._com, 0, max_depth)

    def find_by_name(self, name: str, type_name: str) -> GuiComponent | None:
        """Find the first child element matching name and type string. Returns None if not found."""
        from sapsucker._factory import wrap_com_object

        result = self._com.FindByName(name, type_name)
        return wrap_com_object(result) if result is not None else None

    def find_by_name_ex(self, name: str, type_number: int) -> GuiComponent | None:
        """Find the first child element matching name and type number. Returns None if not found."""
        from sapsucker._factory import wrap_com_object

        result = self._com.FindByNameEx(name, type_number)
        return wrap_com_object(result) if result is not None else None

    def find_all_by_name(self, name: str, type_name: str) -> GuiComponentCollection:
        """Find all child elements matching name and type string."""
        from sapsucker.components.collection import GuiComponentCollection

        return GuiComponentCollection(self._com.FindAllByName(name, type_name))

    def find_all_by_name_ex(self, name: str, type_number: int) -> GuiComponentCollection:
        """Find all child elements matching name and type number."""
        from sapsucker.components.collection import GuiComponentCollection

        return GuiComponentCollection(self._com.FindAllByNameEx(name, type_number))
