"""SLG1 on the desktop: the logs are listed in a tree next to a grid, and the selection fields must be applied."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sapsucker.components.tree import GuiTree

from sapguimcp.models import TableData
from sapguimcp.models.slg1_models import SLG1LogEntry
from sapguimcp.tools.slg1_tools import _read_log_tree, _slg1_lookup_desktop

_COLUMNS = ["001", "100", "101", "102", "103", "107"]


def _tree(nodes: dict[str, tuple[str, list[str]]]) -> Any:
    """A log tree: key -> (node text, items of the columns 100..103)."""
    tree = MagicMock(spec=GuiTree)
    tree.get_column_names.return_value = _COLUMNS
    tree.get_all_node_keys.return_value = list(nodes)
    tree.get_node_text_by_key.side_effect = lambda key: nodes[key][0]
    tree.get_item_text.side_effect = lambda key, column: nodes[key][1][_COLUMNS.index(column) - 1]
    return tree


def _session(tree: Any) -> Any:
    shell = SimpleNamespace(id="/wnd[0]/usr/shell", type_as_number=122, children=[])
    window = SimpleNamespace(dump_tree=lambda: [shell])
    return SimpleNamespace(find_by_id=lambda element_id, **_: window if element_id == "wnd[0]" else tree)


_NODES = {
    "1": ("07.10.2026  10:00:00  USER1", ["3", "EXT1", "Object text 1", "Sub text 1", "00000000000000000001"]),
    "2": ("07.10.2026  11:00:00  USER2", ["15", "", "Object text 2", "", "00000000000000000002"]),
    "3": ("Mehr ...", ["", "", "", "", ""]),
}


def test_the_log_tree_is_read_newest_first_and_the_more_node_is_no_log() -> None:
    logs, more = _read_log_tree(_session(_tree(_NODES)), 50)
    assert [(log.date, log.time, log.user) for log in logs] == [
        ("07.10.2026", "11:00:00", "USER2"),
        ("07.10.2026", "10:00:00", "USER1"),
    ]
    assert logs[1].external_id == "EXT1"
    assert logs[1].log_number == "00000000000000000001"
    assert (logs[1].object, logs[1].subobject, logs[1].message_count) == ("Object text 1", "Sub text 1", 3)
    assert more  # the 'More ...' node says that the selection holds more logs than the tree


def test_only_the_newest_logs_up_to_the_limit_are_read() -> None:
    nodes = {str(i): (f"07.10.2026  10:00:{i:02d}  USER1", ["1", "", "", "", "0000000000000000000x"]) for i in range(5)}
    logs, more = _read_log_tree(_session(_tree(nodes)), 2)
    assert [log.time for log in logs] == ["10:00:04", "10:00:03"]
    assert more


def test_a_complete_tree_is_not_truncated() -> None:
    logs, more = _read_log_tree(_session(_tree({"1": _NODES["1"]})), 50)
    assert len(logs) == 1
    assert not more


def test_a_screen_without_a_tree_has_no_logs() -> None:
    assert _read_log_tree(_session(MagicMock()), 50) == ([], False)  # the shell is not a GuiTree


def _backend(*, tree_logs: list[SLG1LogEntry] | None = None, not_found: list[str] | None = None) -> Any:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.fill_form = AsyncMock(return_value=SimpleNamespace(not_found=not_found or []))
    for name in ("wait_for_ready", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
    backend.read_table = AsyncMock(return_value=TableData(success=True, headers=[], rows=[]))
    backend.require_session = MagicMock()
    backend.com = MagicMock()
    backend.com.run = AsyncMock(return_value=(tree_logs or [], bool(tree_logs)))
    return backend


async def _lookup(backend: Any, *args: Any) -> Any:
    config = MagicMock()
    config.get_default.return_value = SimpleNamespace(language="DE")
    with patch("sapguimcp.tools.slg1_tools.get_sap_config", return_value=config):
        return await _slg1_lookup_desktop(backend, *args)


@pytest.mark.anyio
async def test_the_logs_of_the_tree_are_the_result() -> None:
    entry = SLG1LogEntry(log_number="", object="Object", date="07.10.2026", time="10:00:00", user="USER1")
    backend = _backend(tree_logs=[entry])
    result = await _lookup(backend, "*")
    assert result.success
    assert result.logs == [entry]
    assert result.logs_truncated
    backend.read_table.assert_not_called()


@pytest.mark.anyio
async def test_the_date_range_is_filled_by_the_technical_field_names() -> None:
    backend = _backend()
    await _lookup(backend, "*", None, None, "2026-10-01", "2026-10-08")
    typed = {call.args[0]: call.args[1] for call in backend.focus_and_type.await_args_list}
    assert typed == {"BALHDR-ALDATE": "01.10.2026", "*BALHDR-ALDATE": "08.10.2026"}


@pytest.mark.anyio
@pytest.mark.parametrize("missing", [["Objekt"], ["Unterobjekt"]])
async def test_a_filter_field_that_is_not_found_fails_the_lookup(missing: list[str]) -> None:
    backend = _backend(not_found=missing)
    result = await _lookup(backend, "OBJ", "SUB")
    assert not result.success
    assert missing[0] in str(result.error)
    backend.press_key.assert_not_awaited()  # the query was not run with the default selection


@pytest.mark.anyio
async def test_a_date_that_cannot_be_filled_fails_the_lookup() -> None:
    backend = _backend()
    backend.focus_and_type = AsyncMock(return_value=False)
    result = await _lookup(backend, "*", None, None, "2026-10-01", None)
    assert not result.success
    assert "from_date" in str(result.error)
    backend.press_key.assert_not_awaited()


def test_a_log_without_a_user_and_a_time_with_am_pm_are_logs_not_the_more_node() -> None:
    nodes = {
        "1": ("10/07/2026  10:00:00 AM  USER1", ["1", "", "", "", "0000000000000000000a"]),
        "2": ("10/07/2026  11:00:00", ["2", "", "", "", "0000000000000000000b"]),
    }
    logs, more = _read_log_tree(_session(_tree(nodes)), 50)
    assert [(log.date, log.time, log.user) for log in logs] == [
        ("10/07/2026", "11:00:00", ""),
        ("10/07/2026", "10:00:00 AM", "USER1"),
    ]
    assert not more


def test_the_text_of_only_the_last_nodes_is_read() -> None:
    nodes = {
        str(i): (f"07.10.2026  10:00:{i % 60:02d}  USER1", ["1", "", "", "", "0000000000000000000x"]) for i in range(40)
    }
    tree = _tree(nodes)
    _read_log_tree(_session(tree), 5)
    assert tree.get_node_text_by_key.call_count == 6  # the newest five and one more, to see whether the last is 'More'
