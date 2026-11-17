"""SM37, SLG1 and ST22 read every text from the language packs (#1044, phase 3).

Covers the single-language bugs the migration fixed (desktop job status, the different "no entries" lists,
``language == "DE"`` branches, the WebGUI headings of ST22) and the behaviour change: a session whose language has no
pack (or is unknown) fails the tool call with ``UnsupportedLanguageError``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from sapguimcp import lang
from sapguimcp.lang import UnsupportedLanguageError, _register_for_tests
from sapguimcp.lang.schema import JobStatus
from sapguimcp.models import TableData, TableRow
from sapguimcp.models.slg1_models import SLG1LogEntry
from sapguimcp.tools.slg1_tools import _slg1_lookup_desktop, register_slg1_tools
from sapguimcp.tools.sm37_tools import (
    _execute_sm37_lookup_desktop,
    _fetch_job_log,
    _fill_selection_screen,
    register_sm37_tools,
)
from sapguimcp.tools.st22_tools import (
    _try_quick_button,
    register_st22_tools,
)
from unittests.lang.synthetic_pack import CODE, MARK, synthetic_pack

# ---------------------------------------------------------------------------
# UnsupportedLanguageError instead of a silent fallback
# ---------------------------------------------------------------------------

_TOOLS = [
    ("sap_sm37_lookup", register_sm37_tools, "sapguimcp.tools.sm37_tools", {}),
    ("sap_slg1_lookup", register_slg1_tools, "sapguimcp.tools.slg1_tools", {"object": "*"}),
    ("sap_st22_lookup", register_st22_tools, "sapguimcp.tools.st22_tools", {}),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("name", "register", "module", "kwargs"), _TOOLS)
@pytest.mark.parametrize("language", ["XX", None])
async def test_a_session_without_a_pack_fails_the_call(
    name: str, register: Any, module: str, kwargs: dict[str, Any], language: str | None
) -> None:
    """An unknown or pack-less session language is an error, not a fallback to the default system's language.

    SLG1 and ST22 wrap their lookup in a broad ``except Exception``: the error must not end up in a failure result.
    """
    mcp = FastMCP("test")
    register(mcp)
    tool = await mcp.get_tool(name)
    with (
        patch(f"{module}.get_backend", AsyncMock(return_value=MagicMock())),
        lang.use(language),
        pytest.raises(UnsupportedLanguageError, match=name),
    ):
        await tool.fn(**kwargs)


# ---------------------------------------------------------------------------
# A language that is neither German nor English: no German or English literal is left in the call sites
# ---------------------------------------------------------------------------


def _marked(texts: Any) -> list[str]:
    return [variant for variant in texts if variant.startswith(MARK)]


@pytest.mark.anyio
async def test_slg1_fills_the_labels_of_the_synthetic_language_first() -> None:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.fill_form = AsyncMock(
        side_effect=lambda fields: SimpleNamespace(
            not_found=[label for label in fields if not label.startswith(MARK)], errors=[]
        )
    )
    for name in ("wait_for_ready", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
    backend.read_table = AsyncMock(return_value=TableData(success=True, headers=[], rows=[]))
    backend.require_session = MagicMock()
    backend.com = MagicMock()
    entry = SLG1LogEntry(log_number="1", object="OBJ", date="07.10.2026", time="10:00:00")
    backend.com.run = AsyncMock(return_value=([entry], False))  # a log tree: the lookup ends there
    with _register_for_tests(synthetic_pack()), lang.use(CODE):
        t = lang.current("test")
        await _slg1_lookup_desktop(backend, t, "OBJ", "SUB", "EXT")
    labels = [next(iter(call.args[0])) for call in backend.fill_form.await_args_list]
    assert labels == [
        t.slg1.log_object.variants[0],
        t.slg1.log_subobject.variants[0],
        t.slg1.external_id.variants[0],
    ]
    assert all(label.startswith(MARK) for label in labels)  # not one German or English label was tried


@pytest.mark.anyio
async def test_sm37_selection_screen_targets_the_labels_of_the_synthetic_language() -> None:
    state: dict[str, Any] = {}

    async def _ensure(_backend: Any, target: Any) -> Any:
        state["target"] = target
        return SimpleNamespace(success=True, error=None, warnings=[])

    with (
        _register_for_tests(synthetic_pack()),
        lang.use(CODE),
        patch("sapguimcp.tools.sm37_tools.ensure_screen_state", _ensure),
    ):
        t = lang.current("test")
        await _fill_selection_screen(MagicMock(), t, "JOB*", "ME", ["finished"], None, None)
    target = state["target"]
    assert target.fields[t.sm37.job_name.variants[0]] == "JOB*"
    assert target.fields[t.sm37.user_name.variants[0]] == "ME"
    finished = t.sm37.status[JobStatus.FINISHED]
    assert {label: target.checkboxes[label] for label in finished} == dict.fromkeys(finished, True)
    assert target.checkboxes[t.sm37.status[JobStatus.ACTIVE].variants[0]] is False


@pytest.mark.anyio
async def test_st22_clicks_the_quick_button_of_the_synthetic_language() -> None:
    backend = MagicMock()
    backend.click_button = AsyncMock(side_effect=lambda label: None if label.startswith(MARK) else 1 / 0)
    backend.wait_for_ready = AsyncMock()
    with _register_for_tests(synthetic_pack()), lang.use(CODE):
        t = lang.current("test")
        assert await _try_quick_button(backend, t, None)
    backend.click_button.assert_awaited_once_with(t.st22.today.variants[0])


# ---------------------------------------------------------------------------
# Bug: `if language == "DE"` picked one label, the other language's screen was never tried
# ---------------------------------------------------------------------------


def _refuse(refused: set[str]) -> Any:
    def _click(label: str) -> None:
        if label in refused:
            raise ValueError(label)

    return _click


def _log_backend(*, refuse: set[str]) -> Any:
    backend = MagicMock()
    backend.click_table_cell = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.press_key = AsyncMock()
    backend.click_button = AsyncMock(side_effect=_refuse(refuse))
    backend.get_snapshot = AsyncMock(
        return_value='- heading "Job Log Entries"\n- text: 08.10.2026 00:49:27 Job started'
    )
    return backend


@pytest.mark.anyio
async def test_the_job_log_button_of_the_other_language_is_tried_after_the_own_one() -> None:
    backend = _log_backend(refuse={"Job-Log"})  # a German session on a screen that shows the English button
    log = await _fetch_job_log(backend, lang.view_for("DE"))
    assert log is not None
    assert [call.args[0] for call in backend.click_button.await_args_list] == ["Job-Log", "Job Log"]


@pytest.mark.anyio
async def test_the_job_log_button_of_an_english_session_is_the_english_one() -> None:
    backend = _log_backend(refuse=set())
    await _fetch_job_log(backend, lang.view_for("EN"))
    assert [call.args[0] for call in backend.click_button.await_args_list] == ["Job Log"]


@pytest.mark.anyio
async def test_no_job_log_when_the_screen_has_none_of_the_buttons() -> None:
    backend = _log_backend(refuse={"Job-Log", "Job Log"})
    assert await _fetch_job_log(backend, lang.view_for("DE")) is None


@pytest.mark.anyio
async def test_the_status_column_title_comes_from_the_pack() -> None:
    t = lang.view_for("DE")
    assert t.sm37.col_status.first_key({"Status": "x"}) == "x"
    with _register_for_tests(synthetic_pack()), lang.use(CODE):
        tx = lang.current("test")
        assert tx.sm37.col_status.variants[0].startswith(MARK)
        backend = MagicMock()
        backend.backend_type = "desktop"
        backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
        for name in ("wait_for_ready", "press_key"):
            setattr(backend, name, AsyncMock())
        backend.focus_and_type = AsyncMock(return_value=True)
        backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
        title = tx.sm37.col_status.variants[0]
        row = TableRow(
            row=1, data={tx.sm37.job_name.variants[0]: "J", title: tx.sm37.status[JobStatus.FINISHED].variants[0]}
        )
        backend.read_table = AsyncMock(return_value=TableData(success=True, headers=[title], rows=[row]))
        result = await _execute_sm37_lookup_desktop(backend, tx, "*", None, None, None, None)
    assert [job.status for job in result.jobs] == ["Finished"]
