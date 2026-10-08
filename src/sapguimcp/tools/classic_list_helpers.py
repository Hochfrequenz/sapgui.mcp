"""Read a columnar classic list (``WRITE`` output) from the desktop session as a table.

Some transactions show their result as a classic list instead of an ALV grid, e.g. the SM37 job overview on SAP ERP
6.0: a header line, then one line per entry that starts with a selection checkbox, then a summary line. SAP GUI shows
such a list as ``GuiLabel`` / ``GuiCheckBox`` elements whose ids carry their position, ``lbl[column,row]`` and
``chk[column,row]``, so the columns of the header line can be matched to the cells of the entries by position.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sapguimcp.models import TableData
from sapguimcp.models.sap_results import TableRow

logger = logging.getLogger(__name__)

__all__ = ["read_classic_list_table"]

_POSITIONED = re.compile(r"/(lbl|chk)\[(\d+),(\d+)\]$")


def _cells(usr: Any) -> tuple[dict[int, dict[int, str]], set[int]]:
    """The labels of the screen by row and column, and the rows that start with a checkbox (one ``dump_tree()``)."""
    labels: dict[int, dict[int, str]] = {}
    checkbox_rows: set[int] = set()
    for elem in usr.dump_tree():
        match = _POSITIONED.search(elem.id)
        if not match:
            continue
        column, row = int(match.group(2)), int(match.group(3))
        if match.group(1) == "chk":
            checkbox_rows.add(row)
        else:
            labels.setdefault(row, {})[column] = str(elem.text)
    return labels, checkbox_rows


def _header(labels: dict[int, dict[int, str]], header_titles: tuple[str, ...]) -> tuple[int, dict[int, str]] | None:
    """The row of the column titles and its titles by column: the first row that has one of ``header_titles``."""
    wanted = {title.lower() for title in header_titles}
    for row in sorted(labels):
        titles = {column: text.strip() for column, text in labels[row].items() if text.strip()}
        if any(text.lower() in wanted for text in titles.values()):
            seen: dict[str, int] = {}
            for column in sorted(titles):  # two columns with the same title must not collide in an entry
                seen[titles[column]] = seen.get(titles[column], 0) + 1
                if seen[titles[column]] > 1:
                    titles[column] = f"{titles[column]} ({seen[titles[column]]})"
            return row, titles
    return None


def _entry(cells: dict[int, str], titles: dict[int, str]) -> dict[str, str]:
    """One entry by column title: each cell belongs to the last title that starts at or before its column."""
    starts = sorted(titles)
    entry = {titles[start]: "" for start in starts}
    for column in sorted(cells):
        owner = [start for start in starts if start <= column]
        if owner:
            title = titles[owner[-1]]
            entry[title] = (
                (entry[title] + " " + cells[column].strip()).strip() if entry[title] else cells[column].strip()
            )
    return entry


def read_classic_list_table(session: Any, header_titles: tuple[str, ...], max_rows: int) -> TableData:
    """Read the classic list on screen as a table (run on the COM thread). Empty if the screen has no such list.

    ``header_titles`` are titles the header line is recognised by (compared ignoring case). Entries are the lines
    below the header that start with a checkbox. A list taller than the window is read page by page with the vertical
    scrollbar (a line's absolute row is the scroll position plus its screen row); the scrollbar is reset afterwards.
    """
    usr = session.find_by_id("wnd[0]/usr")
    scrollbar = getattr(usr, "vertical_scrollbar", None)
    maximum = max(int(scrollbar.maximum), 0) if scrollbar is not None else 0
    page_size = max(int(scrollbar.page_size), 1) if scrollbar is not None else 0

    titles: dict[int, str] | None = None
    header_line = -1  # absolute row of the header line
    entries: dict[int, dict[str, str]] = {}
    positions = [0]
    if maximum > 0 and page_size > 0:
        positions += [*range(page_size, maximum + 1, page_size), maximum]
    try:
        for wanted in dict.fromkeys(positions):
            if scrollbar is not None and maximum > 0:
                scrollbar.position = wanted  # always, so a list that starts scrolled is read from its top
            offset = int(scrollbar.position) if scrollbar is not None and maximum > 0 else 0  # SAP clamps: where it is
            labels, checkbox_rows = _cells(usr)
            if titles is None:
                header = _header(labels, header_titles)
                if header is None:
                    continue
                header_row, titles = header
                header_line = offset + header_row
                logger.debug("Classic list header at row %d: %s", header_row, titles)
            for row in sorted(checkbox_rows):
                # only the lines below the header are entries (the selection above it has checkboxes as well)
                if row in labels and offset + row > header_line and (offset + row) not in entries:
                    entries[offset + row] = _entry(labels[row], titles)
            if len(entries) >= max_rows:
                break
    finally:
        if scrollbar is not None and maximum > 0:
            try:
                scrollbar.position = 0
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("Could not reset the scrollbar of the classic list", exc_info=True)

    if titles is None:
        return TableData(success=True, headers=[], rows=[])
    ordered = [entries[row] for row in sorted(entries)][:max_rows]
    headers = [titles[column] for column in sorted(titles)]
    rows = [TableRow(row=index, data=entry) for index, entry in enumerate(ordered, start=1)]
    return TableData(success=True, headers=headers, rows=rows, total_rows=len(rows))
