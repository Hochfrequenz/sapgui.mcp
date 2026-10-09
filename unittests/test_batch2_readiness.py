"""Tests for the desktop readiness predicates and wiring of SE37, SE93, ST22, SE09 and SPRO (#928, step A)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models import SE93Entry
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo
from sapguimcp.tools.desktop_wait_predicates import (
    popup_closed_and_screen_changed,
    screen_changed,
    tab_table_control_loaded,
)
from sapguimcp.tools.se09_tools import _lookup_transports_desktop
from sapguimcp.tools.se37_tools import (
    _click_tab_bilingual,
    _lookup_fm_desktop,
    _read_tab_rows,
    _se37_display_reached,
)
from sapguimcp.tools.se93_tools import _lookup_tcode_desktop
from sapguimcp.tools.spro_tools import _SPRO_TREE_ID, _search_img_desktop, _spro_img_tree_loaded


def _session(elements: dict[str, object]) -> MagicMock:
    session = MagicMock()
    session.find_by_id = lambda element_id, **_kwargs: elements.get(element_id)
    return session


def _wnd(title: str) -> SimpleNamespace:
    return SimpleNamespace(text=title)


def _sbar(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


# --- screen_changed (SE93, ST22, SE09) ---------------------------------------------------------------------------


def test_screen_changed_same_title_and_empty_status_is_not_ready() -> None:
    session = _session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("")})
    assert not screen_changed("Initial", "")(session)


def test_screen_changed_ignores_status_text_from_before_the_action() -> None:
    session = _session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar(" Old message ")})
    assert not screen_changed("Initial", "Old message")(session)
    assert screen_changed("Initial", "Different")(session)


def test_screen_changed_new_status_text_is_ready() -> None:
    session = _session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("Does not exist")})
    assert screen_changed("Initial", "")(session)


def test_screen_changed_title_change_is_ready_despite_stale_status() -> None:
    session = _session({"wnd[0]": _wnd("Display"), "wnd[0]/sbar": _sbar("Old")})
    assert screen_changed("Initial", "Old")(session)


def test_screen_changed_popup_is_ready() -> None:
    session = _session({"wnd[0]": _wnd("Initial"), "wnd[1]": object(), "wnd[0]/sbar": _sbar("Old")})
    assert screen_changed("Initial", "Old")(session)


def test_screen_changed_without_status_bar_is_not_ready() -> None:
    assert not screen_changed("Initial", "")(_session({"wnd[0]": _wnd("Initial")}))


# --- tab_table_control_loaded (SE37) -----------------------------------------------------------------------------


def _elem(type_no: int, elem_id: str, text: str = "", children: list[Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(type_as_number=type_no, id=elem_id, text=text, children=children or [])


def _tree_session(tree: list[Any]) -> MagicMock:
    return _session({"wnd[0]": SimpleNamespace(dump_tree=lambda: tree)})


TABS = "wnd[0]/usr/tabsTABS"


def test_tab_table_control_not_ready_while_tab_page_has_no_table() -> None:
    tree = [
        _elem(91, f"{TABS}/tabpIMP", "Import"),
        _elem(91, f"{TABS}/tabpEXP", "Export", [_elem(80, f"{TABS}/tabpEXP/ssub/tblEXP")]),
    ]
    # The Export tab's table exists, but we wait for Import (stale control of another tab must not count).
    assert not tab_table_control_loaded("Import")(_tree_session(tree))
    assert tab_table_control_loaded("Export")(_tree_session(tree))


def test_tab_table_control_ready_when_table_below_tab_page() -> None:
    tree = [_elem(91, f"{TABS}/tabpIMP", "Import", [_elem(80, f"{TABS}/tabpIMP/ssub/tblIMP")])]
    assert tab_table_control_loaded("import")(_tree_session(tree))


def test_tab_table_control_prefers_exact_label_match() -> None:
    tree = [
        _elem(91, f"{TABS}/tabpTBL", "Tabellen"),
        _elem(91, f"{TABS}/tabpTBLX", "Tabellen (Zusatz)", [_elem(80, f"{TABS}/tabpTBLX/tbl")]),
    ]
    assert not tab_table_control_loaded("Tabellen")(_tree_session(tree))


def test_tab_table_control_unknown_tab_is_not_ready() -> None:
    assert not tab_table_control_loaded("Nope")(_tree_session([_elem(91, f"{TABS}/tabpIMP", "Import")]))


# --- _se37_display_reached ---------------------------------------------------------------------------------------


def test_se37_initial_screen_without_new_status_is_not_ready() -> None:
    session = _session({"wnd[0]": _wnd("Function Builder: Initial Screen"), "wnd[0]/sbar": _sbar("")})
    assert not _se37_display_reached("RFC_READ_TABLE", "Function Builder: Initial Screen", "")(session)


def test_se37_new_title_with_fm_name_is_ready() -> None:
    session = _session({"wnd[0]": _wnd("Function Builder: Display rfc_read_table")})
    assert _se37_display_reached("RFC_READ_TABLE", "Function Builder: Initial Screen", "")(session)


def test_se37_unchanged_title_containing_fm_name_is_not_ready() -> None:
    # The pre-F7 title may already carry the name (e.g. a previous lookup of the same FM): it must not count.
    session = _session({"wnd[0]": _wnd("Function Builder: Display RFC_READ_TABLE")})
    assert not _se37_display_reached("RFC_READ_TABLE", "Function Builder: Display RFC_READ_TABLE", "")(session)


def test_se37_new_status_and_popup_are_ready_but_stale_status_is_not() -> None:
    initial = {"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("Old")}
    assert not _se37_display_reached("ZNOPE", "Initial", "Old")(_session(initial))
    assert _se37_display_reached("ZNOPE", "Initial", "")(_session(initial))
    assert _se37_display_reached("ZNOPE", "Initial", "Old")(_session({**initial, "wnd[1]": object()}))


# --- SPRO tree ---------------------------------------------------------------------------------------------------


def _tree(count: int) -> SimpleNamespace:
    keys = SimpleNamespace(Count=count)
    return SimpleNamespace(com=SimpleNamespace(GetAllNodeKeys=lambda: keys))


def test_spro_tree_missing_is_not_ready() -> None:
    assert not _spro_img_tree_loaded(_session({}))


def test_spro_tree_without_nodes_is_not_ready() -> None:
    assert not _spro_img_tree_loaded(_session({_SPRO_TREE_ID: _tree(0)}))


def test_spro_tree_with_nodes_is_ready() -> None:
    assert _spro_img_tree_loaded(_session({_SPRO_TREE_ID: _tree(5)}))


def test_spro_popup_is_ready() -> None:
    assert _spro_img_tree_loaded(_session({"wnd[1]": object()}))


# --- wiring ------------------------------------------------------------------------------------------------------


def _tab_backend(rows_by_read: list[list[dict[str, str]]]) -> MagicMock:
    backend = MagicMock(spec=DesktopBackend)
    backend.click_tab = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=rows_by_read)
    return backend


@pytest.mark.anyio
async def test_click_tab_bilingual_returns_label_and_only_waits_for_ready() -> None:
    backend = _tab_backend([])
    assert await _click_tab_bilingual(backend, "Tabellen", "Tables") == "Tabellen"
    backend.click_tab.assert_awaited_once_with("Tabellen")
    backend.wait_for_ready.assert_awaited_once()
    backend.wait_for_condition.assert_not_awaited()


@pytest.mark.anyio
async def test_click_tab_bilingual_falls_back_to_english_label_and_reports_missing() -> None:
    backend = _tab_backend([])
    backend.click_tab.side_effect = [ValueError("no"), None]
    assert await _click_tab_bilingual(backend, "Tabellen", "Tables") == "Tables"
    backend.click_tab.side_effect = ValueError("no")
    assert await _click_tab_bilingual(backend, "Tabellen", "Tables") is None


@pytest.mark.anyio
async def test_read_tab_rows_populated_tab_needs_no_extra_wait() -> None:
    backend = _tab_backend([[{"Parametername": "B"}]])
    rows = await _read_tab_rows(backend, "Export", "Export", [{"Parametername": "A"}])
    assert rows == [{"Parametername": "B"}]
    backend.wait_for_condition.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("first_read", [[], [{"Parametername": "A"}]], ids=["empty", "same_as_previous_tab"])
async def test_read_tab_rows_waits_for_tab_table_and_rereads(first_read: list[dict[str, str]]) -> None:
    backend = _tab_backend([first_read, [{"Parametername": "B"}]])
    rows = await _read_tab_rows(backend, "Export", "Export", [{"Parametername": "A"}])
    assert rows == [{"Parametername": "B"}]
    backend.wait_for_condition.assert_awaited_once()
    assert backend.wait_for_condition.await_args.args[0].__qualname__.startswith("tab_table_control_loaded.")
    assert backend.wait_for_condition.await_args.kwargs == {"timeout_ms": 3000, "poll_ms": 250}


@pytest.mark.anyio
async def test_lookup_tcode_desktop_snapshots_state_and_waits_after_f7() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.fill_field = AsyncMock()
    backend.get_screen_info = AsyncMock(return_value=ScreenInfo(title="Initial", url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=" Old "))
    backend.press_key = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.discover_fields = AsyncMock(
        return_value=[
            SimpleNamespace(name="TSTCT-TTEXT", value="Data Browser"),
            SimpleNamespace(name="TSTC-PGMNA", value="SAPLSE16N"),
        ]
    )
    events: list[str] = []
    backend.press_key.side_effect = lambda *_a, **_k: events.append("F7")
    backend.wait_for_ready.side_effect = lambda *_a, **_k: events.append("ready")
    backend.wait_for_condition.side_effect = lambda *_a, **_k: events.append("cond")
    with patch("sapguimcp.tools.se93_tools._read_checkbox", new=AsyncMock(return_value=True)):
        result = await _lookup_tcode_desktop(backend, "SE16")
    assert isinstance(result, SE93Entry)
    assert events == ["F7", "ready", "cond"]
    predicate = backend.wait_for_condition.await_args.args[0]
    assert predicate.__qualname__.startswith("screen_changed.")
    # The predicate was built from the snapshot taken before F7: stale text and unchanged title are not ready.
    assert not predicate(_session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("Old")}))
    assert predicate(_session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("New")}))


def _record(backend: MagicMock, events: list[str]) -> None:
    """Make the backend's action and wait methods append their names to ``events``."""
    for name in ("press_key", "click_button", "wait_for_ready", "wait_for_condition"):
        getattr(backend, name).side_effect = lambda *_a, _n=name, **_k: events.append(_n)


@pytest.mark.anyio
async def test_lookup_fm_desktop_snapshots_title_and_status_and_waits_after_f7() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.fill_field = AsyncMock()
    backend.press_key = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.get_screen_info = AsyncMock(
        side_effect=[ScreenInfo(title="Initial", url="sap://s"), ScreenInfo(title="Display ZFM", url="sap://s")]
    )
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=" Old "))
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.click_tab = AsyncMock()
    backend.com.run = AsyncMock(side_effect=[{}, *([[]] * 10)])  # the header of the attributes tab, then table rows
    backend.discover_fields = AsyncMock(return_value=[])
    events: list[str] = []
    _record(backend, events)
    with patch("sapguimcp.tools.se37_tools._read_tab_rows", new=AsyncMock(return_value=[])):
        await _lookup_fm_desktop(backend, "ZFM")
    # initial wait_for_ready, then F7 followed by a ready wait and the display predicate
    assert events[:4] == ["wait_for_ready", "press_key", "wait_for_ready", "wait_for_condition"]
    backend.press_key.assert_awaited_once_with("F7")
    predicate = backend.wait_for_condition.await_args_list[0].args[0]  # the wait after F7
    assert predicate.__qualname__.startswith("_se37_display_reached.")
    # Built from the pre-F7 snapshot: unchanged title and stale status are not ready, a new FM title is.
    assert not predicate(_session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("Old")}))
    assert predicate(_session({"wnd[0]": _wnd("Display ZFM"), "wnd[0]/sbar": _sbar("Old")}))


@pytest.mark.anyio
async def test_lookup_transports_desktop_snapshots_state_and_waits_after_display_click() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.click_button = AsyncMock()
    backend.get_screen_info = AsyncMock(return_value=ScreenInfo(title="Initial", url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=" Old "))
    backend.get_screen_text = AsyncMock(return_value=SimpleNamespace(labels=[]))
    events: list[str] = []
    _record(backend, events)
    with patch("sapguimcp.tools.se09_tools._set_se09_selection_screen", new=AsyncMock()):
        result = await _lookup_transports_desktop(backend, None, "all", "modifiable")
    assert result.request_count == 0
    assert events == ["wait_for_ready", "click_button", "wait_for_ready", "wait_for_condition"]
    assert backend.wait_for_condition.await_args.kwargs == {"timeout_ms": 5000}
    predicate = backend.wait_for_condition.await_args.args[0]
    assert predicate.__qualname__.startswith("screen_changed.")
    assert not predicate(_session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("Old")}))
    assert predicate(_session({"wnd[0]": _wnd("Request list"), "wnd[0]/sbar": _sbar("Old")}))


@pytest.mark.anyio
async def test_search_img_desktop_waits_for_tree_after_f5() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.press_key = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(return_value=[])
    events: list[str] = []
    _record(backend, events)
    result = await _search_img_desktop(backend, "x")
    assert result.activity_count == 0
    assert events == ["wait_for_ready", "press_key", "wait_for_ready", "wait_for_condition", "press_key", "press_key"]
    assert [c.args for c in backend.press_key.await_args_list] == [("F5",), ("F3",), ("F3",)]
    backend.wait_for_condition.assert_awaited_once_with(_spro_img_tree_loaded)


# --- popup_closed_and_screen_changed (SE24 after dismissing a popup) --------------------------------------------


def test_popup_closed_and_screen_changed_is_not_ready_while_the_popup_is_open() -> None:
    session = _session({"wnd[0]": _wnd("Display"), "wnd[0]/sbar": _sbar("New"), "wnd[1]": _wnd("Language")})
    assert not popup_closed_and_screen_changed("Initial", "")(session)


def test_popup_closed_and_screen_changed_title_change_without_popup_is_ready() -> None:
    session = _session({"wnd[0]": _wnd("Display"), "wnd[0]/sbar": _sbar("")})
    assert popup_closed_and_screen_changed("Initial", "")(session)


def test_popup_closed_and_screen_changed_new_status_without_popup_is_ready() -> None:
    session = _session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar("Does not exist")})
    assert popup_closed_and_screen_changed("Initial", "")(session)


def test_popup_closed_and_screen_changed_unchanged_screen_is_not_ready() -> None:
    session = _session({"wnd[0]": _wnd("Initial"), "wnd[0]/sbar": _sbar(" Old ")})
    assert not popup_closed_and_screen_changed("Initial", "Old")(session)


@pytest.mark.anyio
async def test_lookup_fm_desktop_opens_the_attributes_tab_first_and_returns_its_header_data() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.fill_field = AsyncMock()
    backend.press_key = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.get_screen_info = AsyncMock(
        side_effect=[ScreenInfo(title="Initial", url="sap://s"), ScreenInfo(title="Display ZFM", url="sap://s")]
    )
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=" Old "))
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    header = {"HEADER-AREA": "ZGROUP", "TFTIT-STEXT": "Short text", "TADIR-DEVCLASS": "ZPACKAGE", "RS38L-REMOTE": True}
    backend.com.run = AsyncMock(side_effect=[header, *([[]] * 10)])
    clicked: list[str] = []
    backend.click_tab = AsyncMock(side_effect=clicked.append)
    with patch("sapguimcp.tools.se37_tools._read_tab_rows", new=AsyncMock(return_value=[])):
        entry = await _lookup_fm_desktop(backend, "zfm")
    assert clicked[0] == "Eigenschaften"  # the attributes tab is opened before anything else is read
    # the last wait before the header is read is for the tab's own short text field, bounded
    predicate = backend.wait_for_condition.await_args_list[-1]
    assert predicate.args[0].__qualname__.startswith("named_text_field_present.")
    assert predicate.kwargs == {"timeout_ms": 3000, "poll_ms": 250}
    assert (entry.function_group, entry.description, entry.package, entry.is_rfc_enabled) == (
        "ZGROUP",
        "Short text",
        "ZPACKAGE",
        True,
    )


@pytest.mark.anyio
async def test_lookup_fm_desktop_without_header_data_leaves_the_header_fields_empty() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.fill_field = AsyncMock()
    backend.press_key = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.get_screen_info = AsyncMock(
        side_effect=[ScreenInfo(title="Initial", url="sap://s"), ScreenInfo(title="Display ZFM", url="sap://s")]
    )
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=" Old "))
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=[{}, *([[]] * 10)])
    backend.click_tab = AsyncMock(side_effect=ValueError("no such tab"))
    with patch("sapguimcp.tools.se37_tools._read_tab_rows", new=AsyncMock(return_value=[])):
        entry = await _lookup_fm_desktop(backend, "zfm")
    assert (entry.function_group, entry.description, entry.package, entry.is_rfc_enabled) == (None, "", None, False)
