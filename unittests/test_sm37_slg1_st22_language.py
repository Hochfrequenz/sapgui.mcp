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
from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.webgui.parsers.slg1_parser import is_slg1_no_results
from sapguimcp.backend.webgui.parsers.sm37_parser import is_no_jobs_found, normalize_job_status, parse_sm37_job_list
from sapguimcp.backend.webgui.parsers.st22_parser import is_no_dumps_message, parse_st22_dump_detail
from sapguimcp.backend.webgui.types import AriaSnapshot
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
    _st22_lookup_desktop,
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
# Bug: the desktop SM37 status was not normalised
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [
        ("DE", "Fertig", "Finished"),
        ("DE", "fertig", "Finished"),
        ("DE", "Abgebrochen", "Canceled"),
        ("EN", "Finished", "Finished"),
        ("EN", "Sched.", "Scheduled"),  # the checkbox text of the EN screen (D021T SAPLBTCH 2170)
        ("EN", "Scheduled", "Scheduled"),
        ("DE", "Finished", "Finished"),  # a German session also reads English texts
        ("EN", "unbekannt", "unbekannt"),
    ],
)
def test_the_job_status_is_the_canonical_one(language: str, text: str, expected: str) -> None:
    assert normalize_job_status(f" {text} ", lang.view_for(language)) == expected


@pytest.mark.anyio
async def test_the_desktop_status_is_normalised_like_the_webgui_status() -> None:
    backend = MagicMock()
    backend.backend_type = "desktop"
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    for name in ("wait_for_ready", "focus_and_type", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
    row = TableRow(row=1, data={"Jobname": "MYJOB", "Status": "Freigegeben", "Ersteller": "USER1", "Mandant": "100"})
    backend.read_table = AsyncMock(return_value=TableData(success=True, headers=["Jobname", "Status"], rows=[row]))
    result = await _execute_sm37_lookup_desktop(backend, lang.view_for("DE"), "*", None, None, None, None)
    assert [job.status for job in result.jobs] == ["Released"]

    webgui = parse_sm37_job_list(
        AriaSnapshot('- heading "Jobübersicht"\n- text: MYJOB USER1 freigegeben 0 0 100'), lang.view_for("DE")
    )
    assert [job.status for job in webgui] == ["Released"]


# ---------------------------------------------------------------------------
# Bug: tools and parsers used different "no entries" lists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_every_no_jobs_text_is_known_to_the_parser(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.sm37.no_jobs:
        assert is_no_jobs_found(AriaSnapshot(f'- status "{variant}"'), t), variant


@pytest.mark.anyio
@pytest.mark.parametrize("language", ["DE", "EN"])
async def test_every_no_jobs_text_is_known_to_the_desktop_tool(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.sm37.no_jobs:
        backend = MagicMock()
        backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
        for name in ("wait_for_ready", "press_key"):
            setattr(backend, name, AsyncMock())
        backend.focus_and_type = AsyncMock(return_value=True)
        backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=variant))
        backend.read_table = AsyncMock(side_effect=AssertionError("there is no list to read"))
        result = await _execute_sm37_lookup_desktop(backend, t, "*", None, None, None, None)
        assert result.success
        assert result.jobs == [], variant


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_every_no_dumps_text_is_known_to_the_parser(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.st22.no_dumps:
        assert is_no_dumps_message(AriaSnapshot(f'- status "{variant}"'), t), variant


@pytest.mark.anyio
@pytest.mark.parametrize("language", ["DE", "EN"])
async def test_every_no_dumps_text_is_known_to_the_desktop_tool(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.st22.no_dumps:
        backend = MagicMock(spec=DesktopBackend)
        backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
        backend.wait_for_ready = AsyncMock()
        backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=variant))
        backend.read_table = AsyncMock(side_effect=AssertionError("there is no list to read"))
        with patch("sapguimcp.tools.st22_tools._execute_search", AsyncMock(return_value=None)):
            result = await _st22_lookup_desktop(backend, t, "2026-10-08", None)
        assert result.success
        assert result.dump_count == 0, variant  # type: ignore[union-attr]


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_the_no_logs_text_is_sap_message_bl_208(language: str) -> None:
    """The text SAP shows for BL 208 (T100, both releases), with and without the trailing period of the German one."""
    bl_208 = {
        "DE": "Es konnte kein Protokoll auf der Datenbank gefunden werden.",
        "EN": "No log found in the database",
    }[language]
    t = lang.view_for(language)
    assert t.slg1.no_logs_found.contains(bl_208)
    assert is_slg1_no_results(AriaSnapshot(f'- status "{bl_208}"'), t)


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


# ---------------------------------------------------------------------------
# Bug: the WebGUI ST22 parser knew one heading per section and language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "what", "advice", "analysis"),
    [
        ("DE", "Was ist passiert", "Hinweise zur Fehlerbehebung", "Fehleranalyse"),
        ("DE", "Was ist geschehen?", "Was können Sie tun?", "Fehleranalyse"),
        ("EN", "What happened?", "What can you do?", "Error Analysis"),
        ("EN", "What happened?", "How to Correct the Error", "Error Analysis"),
    ],
)
def test_the_webgui_dump_detail_reads_every_heading_of_the_desktop(
    language: str, what: str, advice: str, analysis: str
) -> None:
    snapshot = AriaSnapshot(
        f'- text "{what}"\n- text "the cause"\n- text "{advice}"\n- text "the remedy"\n- text "{analysis}"\n- text "x"'
    )
    detail = parse_st22_dump_detail(snapshot, lang.view_for(language))
    assert detail.what_happened == "the cause"
    assert detail.how_to_correct == "the remedy"
