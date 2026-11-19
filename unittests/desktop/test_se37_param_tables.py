"""SE37 signature tabs: checkbox columns, the default-value column title and scrolling past the visible rows (#1148).

The row data is recorded from the function builder of a German logon (BAPI_USER_GET_DETAIL), see the issue.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sapguimcp import lang
from sapguimcp.backend.desktop._element_finder import _flatten
from sapguimcp.tools.se37_tools import _parse_se37_params, _read_se37_table_control

# Column titles of the signature table controls on a German logon (Columns(c).Title)
_TITLES = [
    "Parametername",
    "Typisierung",
    "Bezugstyp",
    "Vorschlagswert",
    "Optional",
    "Wertübergabe",
    "Kurztext",
    "Langtext",
]

# (name, typing, type, default, optional, pass by value, short text) as recorded for the import tab
_IMPORT = [
    ("USERNAME", "LIKE", "BAPIBNAME-BAPIBNAME", "", False, True, "Benutzername"),
    ("CACHE_RESULTS", "TYPE", "FLAG_X", "'X'", True, True, "Ergebnisse sollen im Workprozess zwischengepuffert werden"),
    ("EXTUID_GET", "TYPE", "BAPIEXTUIDGET", "", True, True, "Leseflags für Externe UserID"),
]

# the tables tab: 22 rows shown by a control with 20 visible rows; only RETURN is mandatory
_TABLES = [
    "PARAMETER", "PROFILES", "ACTIVITYGROUPS", "RETURN", "ADDTEL", "ADDFAX", "ADDTTX", "ADDTLX", "ADDSMTP", "ADDRML",
    "ADDX400", "ADDRFC", "ADDPRT", "ADDSSF", "ADDURI", "ADDPAG", "ADDCOMREM", "PARAMETER1", "GROUPS", "UCLASSSYS",
    "EXTIDHEAD", "EXTIDPART",
]  # fmt: skip


class _Table:
    """Fake signature table control: checkbox cells have no text, ``visible`` rows are shown from ``position``."""

    def __init__(self, rows: list[tuple[Any, ...]], visible: int = 20) -> None:
        self.rows = rows
        self.visible = visible
        self.position = 0

    def dump_tree(self) -> list[Any]:
        return []  # forces the per-cell fallback

    @property
    def com(self) -> Any:
        table = self

        class _Scrollbar:
            @property
            def Position(self) -> int:  # noqa: N802
                return table.position

            @Position.setter
            def Position(self, value: int) -> None:  # noqa: N802
                table.position = min(value, max(len(table.rows) - table.visible, 0))

        def _cell(r: int, c: int) -> Any:
            value = table.rows[table.position + r][c]
            if isinstance(value, bool):
                return SimpleNamespace(Type="GuiCheckBox", Selected=value, Text="")
            return SimpleNamespace(Type="GuiTextField", Text=value)

        class _Columns:
            Count = len(_TITLES)

            def __call__(self, c: int) -> Any:
                return SimpleNamespace(Title=_TITLES[c], Name=f"RSFBPARA-{c}")

        return SimpleNamespace(
            RowCount=len(table.rows),
            VisibleRowCount=table.visible,
            Columns=_Columns(),
            GetCell=_cell,
            VerticalScrollbar=_Scrollbar(),
        )


def _session(table: _Table) -> Any:
    element = SimpleNamespace(type_as_number=80, id="wnd[0]/usr/tblSIG", text="", children=[])
    wnd = SimpleNamespace(dump_tree=lambda: [element])
    return SimpleNamespace(find_by_id=lambda path: wnd if path == "wnd[0]" else table)


def test_import_tab_reads_checkboxes_and_the_default_column_of_a_german_session() -> None:
    rows = _read_se37_table_control(_session(_Table(list(_IMPORT))), _flatten)
    with lang.use("DE"):
        params = _parse_se37_params(rows, "import", lang.current("test"))

    got = [(p.name, p.default_value, p.optional, p.pass_by_value) for p in params]
    assert got == [
        ("USERNAME", None, False, True),
        ("CACHE_RESULTS", "'X'", True, True),
        ("EXTUID_GET", None, True, True),
    ]


def test_tables_tab_is_scrolled_past_the_visible_rows() -> None:
    table_rows = [(n, "LIKE", "BAPI", "", n != "RETURN", False, "") for n in _TABLES]
    rows = _read_se37_table_control(_session(_Table(table_rows)), _flatten)
    with lang.use("DE"):
        params = _parse_se37_params(rows, "tables", lang.current("test"))

    assert [p.name for p in params] == _TABLES
    assert [p.name for p in params if not p.optional] == ["RETURN"]
