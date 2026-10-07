"""Shared helpers for reading SAP GUI desktop table controls (type 80).

Centralises the scroll-with-re-find logic that prevents COM
``RPC_E_SERVERCALL_RETRYLATER`` (0x80010105) errors on tab-hosted
``GuiTableControl`` widgets.  See #387.

The critical pattern (from SAP community best practice): after changing
``VerticalScrollbar.Position``, the table control must be **re-found** via
``findById`` because the COM cell references become stale when the scrollbar
position changes and SAP reloads the table contents.

Reference: https://simpleexcelvba.com/how-to-automate-scrolling-in-sap-table/
"""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from sapguimcp.backend.desktop._com_thread import _RPC_E_DISCONNECTED, _get_com_error_code

logger = logging.getLogger(__name__)


def _find_table_control_info(session: Any, flatten_fn: Any) -> tuple[str, list[str], int, int] | None:
    """Locate the first GuiTableControl (type 80) and return its metadata.

    Returns ``(element_id, column_titles, row_count, visible_row_count)``
    or ``None`` if no table control is found.
    """
    wnd = session.find_by_id("wnd[0]")
    tree = cast(Any, wnd).dump_tree()
    flat = flatten_fn(tree)

    for elem in flat:
        if elem.type_as_number != 80:
            continue
        tc = session.find_by_id(elem.id)
        raw: Any = getattr(tc, "com", getattr(tc, "_com", tc))
        col_titles = [raw.Columns(c).Title or raw.Columns(c).Name for c in range(raw.Columns.Count)]
        return elem.id, col_titles, raw.RowCount, raw.VisibleRowCount
    return None


def _get_raw_tc(session: Any, element_id: str) -> Any:
    """Re-find a table control by ID and return the raw COM object.

    This **must** be called after every scrollbar position change to get
    fresh cell references.
    """
    tc = session.find_by_id(element_id)
    return getattr(tc, "com", getattr(tc, "_com", tc))


_CELL_ID_SUFFIX = re.compile(r"\[(\d+),(\d+)\]$")  # table control cell ids end in [column,row] (page-relative)


def _read_visible_page_from_tree(
    session: Any, element_id: str, col_titles: list[str], count: int, flatten_fn: Any
) -> list[dict[str, str]] | None:
    """Read *count* visible rows with one ``dump_tree()`` call instead of two COM calls per cell (#928).

    Cells are recognised by their ``[column,row]`` id suffix. Returns ``None`` when the dump contains no cells or
    fewer than *count* rows (e.g. a page that was not repainted yet), or fails, so the caller can fall back to
    ``_read_visible_page``. As there, a missing cell within a row leaves its column out of that row. A lost COM
    connection is not swallowed.
    """
    try:
        tree = session.find_by_id(element_id).dump_tree()
        cells: dict[tuple[int, int], str] = {}
        for elem in flatten_fn(tree):
            match = _CELL_ID_SUFFIX.search(elem.id)
            if match:
                cells[(int(match.group(2)), int(match.group(1)))] = elem.text
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if _get_com_error_code(exc) == _RPC_E_DISCONNECTED:
            raise
        logger.warning("Table control tree dump failed, falling back to per-cell reads", exc_info=True)
        return None
    if len({row for row, _column in cells if row < count}) < count:
        logger.warning(
            "Table control dump has %d of %d expected rows, falling back to per-cell reads",
            len({row for row, _column in cells if row < count}),
            count,
        )
        return None
    return [{title: cells[(r, c)] for c, title in enumerate(col_titles) if (r, c) in cells} for r in range(count)]


def _read_visible_page(raw: Any, col_titles: list[str], count: int) -> list[dict[str, str]]:
    """Read *count* visible rows from a (freshly-found) table control."""
    rows: list[dict[str, str]] = []
    for r in range(count):
        row_data: dict[str, str] = {}
        for c, title in enumerate(col_titles):
            try:
                row_data[title] = raw.GetCell(r, c).Text
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        rows.append(row_data)
    return rows


def read_table_control(session: Any, flatten_fn: Any) -> list[dict[str, str]]:
    """Read the first GuiTableControl's visible page (no scrolling).

    For tables that fit on one page this returns all rows.  For larger
    tables only the currently visible rows are returned.
    """
    info = _find_table_control_info(session, flatten_fn)
    if info is None:
        return []
    element_id, col_titles, total, visible = info
    readable = min(total, visible)
    page = _read_visible_page_from_tree(session, element_id, col_titles, readable, flatten_fn)
    if page is not None:
        return page
    raw = _get_raw_tc(session, element_id)
    return _read_visible_page(raw, col_titles, readable)


def read_table_control_all_rows(session: Any, flatten_fn: Any) -> list[dict[str, str]]:
    """Read ALL rows from the first GuiTableControl, scrolling as needed.

    After each ``VerticalScrollbar.Position`` change the table control is
    **re-found** via ``findById`` so that the COM cell references are fresh.
    This is the SAP-recommended pattern and avoids the
    ``RPC_E_SERVERCALL_RETRYLATER`` (0x80010105) crash.  See #387.
    """
    info = _find_table_control_info(session, flatten_fn)
    if info is None:
        return []
    element_id, col_titles, total, visible = info

    if total <= visible:
        page = _read_visible_page_from_tree(session, element_id, col_titles, total, flatten_fn)
        if page is not None:
            return page
        raw = _get_raw_tc(session, element_id)
        return _read_visible_page(raw, col_titles, total)

    rows: list[dict[str, str]] = []
    scroll_pos = 0
    while len(rows) < total:
        # Re-find the table control to get fresh cell references
        raw = _get_raw_tc(session, element_id)
        readable = min(visible, total - len(rows))
        page = _read_visible_page_from_tree(session, element_id, col_titles, readable, flatten_fn)
        rows.extend(page if page is not None else _read_visible_page(raw, col_titles, readable))
        scroll_pos += visible
        if scroll_pos >= total:
            break
        try:
            raw.VerticalScrollbar.Position = scroll_pos
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Scrollbar position change failed", extra={"position": scroll_pos})
            break

    # Scroll back to top
    if scroll_pos > visible:
        try:
            raw = _get_raw_tc(session, element_id)
            raw.VerticalScrollbar.Position = 0
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    return rows
