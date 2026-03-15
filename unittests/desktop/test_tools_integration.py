"""Integration tests for transaction tools on desktop backend.

Verify that tool functions produce valid return models with real SAP data.
"""

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
    import faulthandler

    try:
        if b._session:
            session = b._session
            await com.run(lambda: session.com.Parent.CloseConnection())
            b._session = None
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    faulthandler.disable()
    com.shutdown()
    faulthandler.enable()


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_query_returns_valid_result(backend):
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "TSTC", None, 5)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.total_hits > 0
    assert result.returned_rows > 0
    assert len(result.columns) > 0
    assert result.table == "TSTC"
    # Verify rows have data matching columns
    for row in result.rows:
        assert isinstance(row.data, dict)
        assert len(row.data) > 0
    # Verify model serializes
    json_str = result.model_dump_json()
    assert "TSTC" in json_str
    # Navigate back
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_nonexistent_table(backend):
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "ZZZNOTEXIST99", None, 5)
    # Should return error or 0 rows, not crash
    assert result.returned_rows == 0
    await backend.press_key("F3")
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm37_returns_valid_result(backend):
    """SM37 with default selection -- may return 0 jobs or some jobs."""
    await backend.enter_transaction("SM37")
    # Just verify we can read the screen
    fields = await backend.discover_fields()
    assert len(fields) > 0
    sbar = await backend.get_status_bar()
    # Navigate back
    await backend.press_key("F3")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se16_result_model_serializes(backend):
    """Verify SE16Result can be JSON-serialized (MCP tools return JSON)."""
    from sapwebguimcp.tools.se16_tools import _execute_se16_query

    result = await _execute_se16_query(backend, "TSTC", None, 3)
    # model_dump_json must not raise
    json_str = result.model_dump_json()
    assert isinstance(json_str, str)
    assert len(json_str) > 10
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
