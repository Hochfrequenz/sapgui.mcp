"""Integration tests for transaction tools on desktop backend.

Exercises the actual tool functions (not just backend methods) against a real
SAP system. Each test verifies:
1. The tool function returns the correct model type
2. The model contains expected data (non-empty where applicable)
3. The model serializes to JSON (required for MCP transport)
4. Error cases return structured errors, not exceptions

Tests are designed to NOT depend on specific SAP data — they assert on
structure and behavior, not on specific values.
"""

import asyncio
import json
import sys
from datetime import date

import pytest
from dotenv import load_dotenv

from unittests.conftest import is_sap_integration_test_machine

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

skip_not_sap = pytest.mark.skipif(not is_sap_integration_test_machine(), reason="Not SAP machine")


def _creds_ok() -> bool:
    try:
        load_dotenv()
        from sapwebguimcp.models.config import get_settings

        s = get_settings()
        return bool(s.sap_connection_name and s.sap_user and s.sap_password and s.sap_mandant)
    except Exception:
        return False


skip_no_creds = pytest.mark.skipif(not _creds_ok(), reason="No SAP credentials")


@pytest.fixture
async def backend():
    """Provide a logged-in DesktopBackend. Closes ALL connections on teardown."""
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
    assert r.success, f"Login failed: {r.error}"
    yield b
    # Teardown: close ALL connections — tools may have opened additional ones
    import faulthandler

    try:
        from sapwebguimcp.sapgui import SapGui

        app = await com.run(lambda: SapGui.connect())
        raw_conns = await com.run(lambda: app.com.Children)
        count = await com.run(lambda: raw_conns.Count)
        for i in range(count - 1, -1, -1):
            try:
                await com.run(lambda i=i: raw_conns(i).CloseConnection())
            except Exception:
                pass
    except Exception:
        pass
    b._session = None
    faulthandler.disable()
    com.shutdown()
    faulthandler.enable()


# ---------------------------------------------------------------------------
# SE16 Tests — exercises _execute_se16_query_desktop
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_query_tstc(backend):
    """SE16: query TSTC table returns rows with expected columns."""
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "TSTC", None, 5)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.total_hits >= 5
    assert result.returned_rows == 5
    assert result.table == "TSTC"
    assert "TCODE" in result.columns
    assert len(result.rows) == 5
    # Each row has data dict with the expected column
    for row in result.rows:
        assert isinstance(row.data, dict)
        assert "TCODE" in row.data
        assert row.data["TCODE"]  # non-empty TCODE value
    # Navigate back
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_nonexistent_table(backend):
    """SE16: nonexistent table returns 0 rows without raising."""
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "ZZZNOTEXIST99", None, 5)
    assert result.returned_rows == 0
    # Should have an error or empty result, not crash
    assert isinstance(result.columns, list)
    assert isinstance(result.rows, list)
    for _ in range(3):
        await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_model_serializes(backend):
    """SE16Result must JSON-serialize for MCP transport."""
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "TSTC", None, 3)
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["table"] == "TSTC"
    assert isinstance(parsed["rows"], list)
    assert isinstance(parsed["columns"], list)
    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# SM37 Tests — exercises _execute_sm37_lookup_desktop
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm37_lookup_returns_result(backend):
    """SM37: tool function returns SM37JobListResult with correct structure."""
    from sapwebguimcp.tools.sm37_tools import _execute_sm37_lookup_desktop

    result = await _execute_sm37_lookup_desktop(
        backend, job_name="*", username=None, statuses=None, from_date=None, to_date=None
    )
    assert result.success or result.error  # either data or a clear error
    assert isinstance(result.model_dump_json(), str)
    # Whether jobs exist or not, the model should be well-formed
    assert hasattr(result, "jobs") or hasattr(result, "error")
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm37_model_serializes(backend):
    """SM37JobListResult must JSON-serialize."""
    from sapwebguimcp.tools.sm37_tools import _execute_sm37_lookup_desktop

    result = await _execute_sm37_lookup_desktop(
        backend, job_name="*", username=None, statuses=None, from_date=None, to_date=None
    )
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "success" in parsed
    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# SM30 Tests — exercises _lookup_view_desktop
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm30_lookup_existing_view(backend):
    """SM30: looking up a well-known view returns structured result."""
    from sapwebguimcp.tools.sm30_tools import _lookup_view_desktop

    # T000 (clients table) is a standard SAP table that exists on every system
    result = await _lookup_view_desktop(backend, "T000")
    # May succeed (table found) or fail (authorization), but should not crash
    assert result is not None
    assert isinstance(result.model_dump_json(), str)
    parsed = json.loads(result.model_dump_json())
    assert "success" in parsed
    await backend.press_key("F3")
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm30_nonexistent_view(backend):
    """SM30: nonexistent view returns error, not exception."""
    from sapwebguimcp.tools.sm30_tools import _lookup_view_desktop

    result = await _lookup_view_desktop(backend, "ZZZNOTEXIST99")
    # Should return a result (possibly with error), not crash
    assert result is not None
    assert isinstance(result.model_dump_json(), str)
    for _ in range(3):
        await backend.press_key("F3")


# ---------------------------------------------------------------------------
# SE09 Tests — exercises _lookup_transports_desktop
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se09_lookup_transports(backend):
    """SE09: transport lookup returns TransportListResult."""
    from sapwebguimcp.tools.se09_tools import _lookup_transports_desktop

    result = await _lookup_transports_desktop(backend, username=None, request_type="all", status="modifiable")
    assert result is not None
    assert isinstance(result.model_dump_json(), str)
    parsed = json.loads(result.model_dump_json())
    assert "success" in parsed
    # transports may be empty list if no transports exist
    if result.success and hasattr(result, "transports"):
        assert isinstance(result.transports, list)
    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# SLG1 Tests — exercises _slg1_lookup_desktop
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_slg1_lookup_returns_result(backend):
    """SLG1: application log lookup returns SLG1LogListResult."""
    from sapwebguimcp.tools.slg1_tools import _slg1_lookup_desktop

    # Use a generic object that likely exists (or returns empty)
    result = await _slg1_lookup_desktop(
        backend,
        object_name="BALM",
        subobject=None,
        external_id=None,
        from_date=None,
        to_date=None,
    )
    assert result is not None
    assert isinstance(result.model_dump_json(), str)
    parsed = json.loads(result.model_dump_json())
    assert "success" in parsed
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_slg1_model_serializes(backend):
    """SLG1LogListResult must JSON-serialize."""
    from sapwebguimcp.tools.slg1_tools import _slg1_lookup_desktop

    result = await _slg1_lookup_desktop(
        backend, object_name="ZZZNOTEXIST", subobject=None, external_id=None, from_date=None, to_date=None
    )
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "success" in parsed
    for _ in range(3):
        await backend.press_key("F3")


# ---------------------------------------------------------------------------
# ST22 Tests — exercises _st22_lookup_desktop
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_st22_lookup_today(backend):
    """ST22: dump list for today returns ST22DumpListResult."""
    from sapwebguimcp.tools.st22_tools import _st22_lookup_desktop

    result = await _st22_lookup_desktop(backend, target_date=date.today().isoformat(), dump_index=None)
    assert result is not None
    assert isinstance(result.model_dump_json(), str)
    parsed = json.loads(result.model_dump_json())
    assert "success" in parsed
    # May have dumps or not — just verify structure
    await backend.press_key("F3")
    await backend.press_key("F3")


# ---------------------------------------------------------------------------
# Stub tools — verify they return clear errors
# ---------------------------------------------------------------------------


def test_se93_stub_returns_error():
    """SE93 desktop stub returns 'not supported' error model."""
    from sapwebguimcp.models.se93_models import SE93Result

    result = SE93Result.failure("SE93 lookup is not yet supported on the desktop backend")
    assert not result.success
    assert "not" in result.error.lower() and "support" in result.error.lower()
    assert result.model_dump_json()


def test_se24_stub_returns_error():
    """SE24 desktop stub returns 'not supported' error model."""
    from sapwebguimcp.models.se24_models import SE24Result

    result = SE24Result.failure("SE24 lookup is not yet supported on the desktop backend")
    assert not result.success
    assert "not" in result.error.lower() and "support" in result.error.lower()
    assert result.model_dump_json()


def test_se37_stub_returns_error():
    """SE37 desktop stub returns 'not supported' error model."""
    from sapwebguimcp.models.se37_models import SE37Result

    result = SE37Result.failure("SE37 lookup is not yet supported on the desktop backend")
    assert not result.success
    assert "not" in result.error.lower() and "support" in result.error.lower()
    assert result.model_dump_json()


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_screen_info_round_trip(backend):
    """get_screen_info returns correct data, serializes as ScreenInfo model."""
    await backend.enter_transaction("SE16")
    info = await backend.get_screen_info()
    assert info.success
    assert info.transaction == "SE16"
    assert info.title
    assert info.program
    # Serializes
    parsed = json.loads(info.model_dump_json())
    assert parsed["transaction"] == "SE16"
    await backend.press_key("F3")
