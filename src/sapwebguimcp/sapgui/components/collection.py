"""Collection wrappers for SAP GUI COM collections."""

from __future__ import annotations


class GuiComponentCollection:
    """Wraps a COM GuiComponentCollection (children of a container)."""

    def __init__(self, com_collection) -> None:
        self._com = com_collection

    def __len__(self) -> int:
        return self._com.Count

    def __getitem__(self, index: int):
        length = self._com.Count
        if index < 0:
            index += length
        if index < 0 or index >= length:
            raise IndexError(f"Index {index} out of range for collection of length {length}")
        return self._com.Item(index)

    def __iter__(self):
        for i in range(self._com.Count):
            yield self._com.Item(i)

    def __repr__(self) -> str:
        return f"GuiComponentCollection(count={self._com.Count})"


class GuiCollection:
    """Wraps a COM GuiCollection (e.g. DumpState results)."""

    def __init__(self, com_collection) -> None:
        self._com = com_collection

    def __len__(self) -> int:
        return self._com.Count

    def __getitem__(self, index: int):
        length = self._com.Count
        if index < 0:
            index += length
        if index < 0 or index >= length:
            raise IndexError(f"Index {index} out of range for collection of length {length}")
        return self._com.Item(index)

    def __iter__(self):
        for i in range(self._com.Count):
            yield self._com.Item(i)

    def __repr__(self) -> str:
        return f"GuiCollection(count={self._com.Count})"
