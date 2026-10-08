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


# Pages overlap by this many lines: the page size also counts lines that are no data (the list header), so stepping by
# the full page size could skip lines. Lines are keyed by their absolute row, so the overlap costs nothing.
_PAGE_OVERLAP = 4


def _scroll_positions(maximum: int, page_size: int) -> list[int]:
    """The vertical scroll positions to read a list from: its top, then overlapping pages up to ``maximum``."""
    positions = [0]
    if maximum > 0 and page_size > 0:
        step = max(page_size - _PAGE_OVERLAP, 1)
        positions += [*range(step, maximum + 1, step), maximum]
    return positions


def _cells(usr: Any) -> tuple[dict[int, dict[int, str]], dict[int, str]]:
    """The labels of the screen by row and column, and the ids of the checkboxes by row (one ``dump_tree()``)."""
    labels: dict[int, dict[int, str]] = {}
    checkboxes: dict[int, str] = {}
    for elem in usr.dump_tree():
        match = _POSITIONED.search(elem.id)
        if not match:
            continue
        column, row = int(match.group(2)), int(match.group(3))
        if match.group(1) == "chk":
            checkboxes[row] = str(elem.id)
        else:
            labels.setdefault(row, {})[column] = str(elem.text)
    return labels, checkboxes


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
    positions = _scroll_positions(maximum, page_size)
    try:
        for wanted in dict.fromkeys(positions):
            if scrollbar is not None and maximum > 0:
                scrollbar.position = wanted  # always, so a list that starts scrolled is read from its top
            offset = int(scrollbar.position) if scrollbar is not None and maximum > 0 else 0  # SAP clamps: where it is
            labels, checkboxes = _cells(usr)
            checkbox_rows = set(checkboxes)
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


def select_first_classic_list_entry(session: Any, header_titles: tuple[str, ...]) -> bool:
    """Tick the checkbox of the first entry on the screen below the header line (COM thread). False if there is none.

    For actions that work on the selected entries, e.g. the job log of SM37 on SAP ERP 6.0. Only the entries that are
    on screen are considered; a list is shown from its top when it is opened.
    """
    usr = session.find_by_id("wnd[0]/usr")
    labels, checkboxes = _cells(usr)
    header = _header(labels, header_titles)
    if header is None:
        return False
    header_row, _titles = header
    for row in sorted(checkboxes):
        if row > header_row and row in labels:
            session.find_by_id(checkboxes[row]).selected = True
            return True
    return False


def read_classic_list_lines(session: Any, max_lines: int) -> list[str]:
    """Read the text of the classic list on screen line by line (COM thread): the cells of a line joined by a space.

    A list taller than the window is read page by page with the vertical scrollbar, which is reset afterwards.
    Lines without text are skipped. For lists that are plain text (e.g. the job log), not columns.
    """
    usr = session.find_by_id("wnd[0]/usr")
    scrollbar = getattr(usr, "vertical_scrollbar", None)
    maximum = max(int(scrollbar.maximum), 0) if scrollbar is not None else 0
    page_size = max(int(scrollbar.page_size), 1) if scrollbar is not None else 0
    positions = _scroll_positions(maximum, page_size)
    lines: dict[int, str] = {}
    try:
        for wanted in dict.fromkeys(positions):
            if scrollbar is not None and maximum > 0:
                scrollbar.position = wanted
            offset = int(scrollbar.position) if scrollbar is not None and maximum > 0 else 0
            labels, _checkboxes = _cells(usr)
            for row, cells in labels.items():
                text = " ".join(cells[column].strip() for column in sorted(cells) if cells[column].strip())
                if text and (offset + row) not in lines:
                    lines[offset + row] = text
            if len(lines) >= max_lines:
                break
    finally:
        if scrollbar is not None and maximum > 0:
            try:
                scrollbar.position = 0
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("Could not reset the scrollbar of the classic list", exc_info=True)
    return [lines[index] for index in sorted(lines)][:max_lines]
