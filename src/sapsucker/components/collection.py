"""Collection wrappers for SAP GUI COM collections."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

from typing import Any, Iterator

from sapsucker.components.base import GuiComponent

__all__ = ["GuiCollection", "GuiComponentCollection"]


class GuiComponentCollection:
    """Wraps a COM GuiComponentCollection (children of a container)."""

    def __init__(self, com_collection: Any) -> None:
        self._com = com_collection

    def __len__(self) -> int:
        """Number of items in the collection."""
        return int(self._com.Count)

    def __getitem__(self, index: int) -> GuiComponent:
        """Return the wrapped component at the given index."""
        from sapsucker._factory import wrap_com_object

        length = self._com.Count
        if index < 0:
            index += length
        if index < 0 or index >= length:
            raise IndexError(f"Index {index} out of range for collection of length {length}")
        return wrap_com_object(self._com.Item(index))

    def __iter__(self) -> Iterator[GuiComponent]:
        """Iterate over all wrapped components."""
        for i in range(self._com.Count):
            yield self[i]

    def __repr__(self) -> str:
        return f"GuiComponentCollection(count={self._com.Count})"


class GuiCollection:
    """Wraps a COM GuiCollection (e.g. DumpState results)."""

    def __init__(self, com_collection: Any) -> None:
        self._com = com_collection

    def __len__(self) -> int:
        """Number of items in the collection."""
        return int(self._com.Count)

    def __getitem__(self, index: int) -> Any:
        """Return the item at the given index."""
        length = self._com.Count
        if index < 0:
            index += length
        if index < 0 or index >= length:
            raise IndexError(f"Index {index} out of range for collection of length {length}")
        return self._com.Item(index)

    def __iter__(self) -> Iterator[Any]:
        """Iterate over all items."""
        for i in range(self._com.Count):
            yield self._com.Item(i)

    def __repr__(self) -> str:
        return f"GuiCollection(count={self._com.Count})"
