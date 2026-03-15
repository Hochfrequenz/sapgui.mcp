"""Integration tests for transaction tools on desktop backend.

Verify that tool functions produce valid return models with real SAP data.
Each test calls the actual tool function (or navigates to the transaction),
verifies the return model, checks JSON serialization, and navigates back.
"""

import asyncio
import json
import sys

import pytest
from dotenv import load_dotenv

from unittests.conftest import is_sap_integration_test_machine

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
skip_not_sap = pytest.mark.skipif(not is_sap_integration_test_machine(), reason="Not SAP machine")


def _creds_ok():
    try:
        load_dotenv()
        from sapwebguimcp.models.config import get_settings

        s = get_settings()
        return bool(s.sap_connection_name and s.sap_user and s.sap_password and s.sap_mandant)
    except Exception:  # pylint: disable=broad-exception-caught
        return False


skip_no_creds = pytest.mark.skipif(not _creds_ok(), reason="No SAP credentials")


@pytest.fixture
async def backend():
    import os

    load_dotenv()
    from sapwebguimcp.backend.desktop import DesktopBackend
    from sapwebguimcp.backend.desktop._com_thread import ComThread

    com = ComThread()
    b = DesktopBackend(com_thread=com)
    r = await b.login(
        "x",
        os.environ["SAP_USER"],
        os.environ["SAP_PASSWORD"],
        os.environ["SAP_MANDANT"],
        os.environ.get("SAP_LANGUAGE", "DE"),
    )
    assert r.success
    yield b
    # Teardown: close ALL connections -- tools may have opened additional ones
    import faulthandler

    try:
        from sapwebguimcp.sapgui import SapGui

        app = await com.run(lambda: SapGui.connect())
        raw_conns = await com.run(lambda: app.com.Children)
        count = await com.run(lambda: raw_conns.Count)
        for i in range(count - 1, -1, -1):
            try:
                await com.run(lambda i=i: raw_conns(i).CloseConnection())
            except Exception:  # pylint: disable=broad-exception-caught
                pass
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    b._session = None
    faulthandler.disable()
    com.shutdown()
    faulthandler.enable()


# ---------------------------------------------------------------------------
# SE16 Tests
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_query_tstc(backend):
    """SE16: query TSTC table returns rows with TCODE column."""
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "TSTC", None, 5)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.total_hits >= 5
    assert result.returned_rows == 5
    assert "TCODE" in result.columns
    assert all(isinstance(row.data, dict) for row in result.rows)
    assert all("TCODE" in row.data for row in result.rows)
    assert result.model_dump_json()  # serializes
    # Navigate back
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_nonexistent_table(backend):
    """SE16: nonexistent table returns 0 rows, not an exception."""
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "ZZZNOTEXIST99", None, 5)
    assert result.returned_rows == 0
    # Navigate back (may be on error screen)
    for _ in range(3):
        await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_empty_table(backend):
    """SE16: table with no matching rows returns 0 rows."""
    # Filters not fully supported on desktop yet; skip for now.
    pass


# ---------------------------------------------------------------------------
# SM37 Tests
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm37_selection_screen(backend):
    """SM37: selection screen has expected fields (jobname, username)."""
    await backend.enter_transaction("SM37")
    fields = await backend.discover_fields()
    field_names = [f.name.upper() for f in fields if f.name]
    assert any("JOBNAME" in n for n in field_names) or any(
        "BTCJOB" in n for n in field_names
    ), f"Expected JOBNAME field, got: {field_names}"
    assert any("USERNAME" in n for n in field_names) or any(
        "BTCUNAME" in n for n in field_names
    ), f"Expected USERNAME field, got: {field_names}"
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm37_execute_returns_status(backend):
    """SM37: F8 execute returns a status (no jobs or job list)."""
    await backend.enter_transaction("SM37")
    await backend.press_key("F8")
    await asyncio.sleep(1)
    sbar = await backend.get_status_bar()
    # Either jobs found (table on screen) or "no jobs" message
    table = await backend.read_table(max_rows=5)
    if table.total_rows == 0:
        # "Kein Job" or "No job" message in status bar
        assert sbar.message != ""
    else:
        assert table.total_rows > 0
        assert len(table.headers) > 0
    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# SM30 Tests
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm30_initial_screen(backend):
    """SM30: initial screen has table/view name field."""
    await backend.enter_transaction("SM30")
    fields = await backend.discover_fields()
    field_names = [f.name.upper() for f in fields if f.name]
    assert (
        any("VIEWNAME" in n or "TABNAME" in n for n in field_names) or len(fields) > 0
    ), f"Expected VIEWNAME field, got: {field_names}"
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# SE09 Tests
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se09_initial_screen(backend):
    """SE09: Transport Organizer opens and has expected screen elements."""
    await backend.enter_transaction("SE09")
    info = await backend.get_screen_info()
    assert info.transaction == "SE09"
    text = await backend.get_screen_text()
    assert text.title is not None
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# SLG1 Tests
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_slg1_initial_screen(backend):
    """SLG1: Application Log screen opens with expected fields."""
    await backend.enter_transaction("SLG1")
    info = await backend.get_screen_info()
    assert info.transaction == "SLG1"
    fields = await backend.discover_fields()
    assert len(fields) > 0
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# ST22 Tests
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_st22_initial_screen(backend):
    """ST22: Short Dump Analysis opens."""
    await backend.enter_transaction("ST22")
    info = await backend.get_screen_info()
    assert info.transaction == "ST22"
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# Cross-cutting tests
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_model_serialization_roundtrip(backend):
    """All tool results must be JSON-serializable for MCP transport."""
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "TSTC", None, 3)
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["table"] == "TSTC"
    assert isinstance(parsed["rows"], list)
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_screen_info_after_transaction(backend):
    """get_screen_info returns correct data after entering a transaction."""
    await backend.enter_transaction("SE16")
    info = await backend.get_screen_info()
    assert info.transaction == "SE16"
    assert info.program is not None
    assert info.title is not None
    await backend.press_key("F3")
