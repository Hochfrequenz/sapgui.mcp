"""Tests for the desktop readiness predicates and wiring of SE37, SE93, ST22, SE09 and SPRO (#928, step A)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models import SE93Entry
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo
from sapguimcp.tools.desktop_wait_predicates import screen_changed, tab_table_control_loaded
from sapguimcp.tools.se37_tools import _click_tab_bilingual, _read_tab_rows, _se37_display_reached
from sapguimcp.tools.se93_tools import _lookup_tcode_desktop
from sapguimcp.tools.spro_tools import _SPRO_TREE_ID, _spro_img_tree_loaded
from sapguimcp.tools.st22_tools import _read_text_until_changed


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
    assert not _se37_display_reached("RFC_READ_TABLE", "")(session)


def test_se37_title_with_fm_name_is_ready() -> None:
    session = _session({"wnd[0]": _wnd("Function Builder: Display rfc_read_table")})
    assert _se37_display_reached("RFC_READ_TABLE", "")(session)


def test_se37_new_status_and_popup_are_ready_but_stale_status_is_not() -> None:
    initial = {"wnd[0]": _wnd("Function Builder: Initial Screen"), "wnd[0]/sbar": _sbar("Old")}
    assert not _se37_display_reached("ZNOPE", "Old")(_session(initial))
    assert _se37_display_reached("ZNOPE", "")(_session(initial))
    assert _se37_display_reached("ZNOPE", "Old")(_session({**initial, "wnd[1]": object()}))


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


# --- ST22 scroll polling -----------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_text_until_changed_returns_new_text_immediately() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.get_screen_text = AsyncMock(return_value=SimpleNamespace(full_text="page 2"))
    assert await _read_text_until_changed(backend, "page 1") == "page 2"
    assert backend.get_screen_text.await_count == 1


@pytest.mark.anyio
async def test_read_text_until_changed_polls_then_gives_up_at_bottom() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.get_screen_text = AsyncMock(return_value=SimpleNamespace(full_text="same"))
    assert await _read_text_until_changed(backend, "same", timeout_s=0.05, poll_s=0.01) == "same"
    assert backend.get_screen_text.await_count > 1


@pytest.mark.anyio
async def test_read_text_until_changed_waits_for_refresh() -> None:
    backend = MagicMock(spec=DesktopBackend)
    backend.get_screen_text = AsyncMock(
        side_effect=[SimpleNamespace(full_text="old"), SimpleNamespace(full_text="new")]
    )
    assert await _read_text_until_changed(backend, "old", timeout_s=1, poll_s=0.01) == "new"


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
