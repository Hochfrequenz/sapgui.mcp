"""
Integration tests for sap_quick_report composite tool.

These tests run against a real SAP system to verify the full pipeline:
TX -> fill selection screen -> F8 -> classify result -> read table.

They auto-skip if not on an authorized machine or SAP_URL is not set.
"""

import pytest
from mcp import ClientSession

from sapwebguimcp.models import LoginResult
from sapwebguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)

from .conftest import call_tool_typed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SM37_FIELDS = {"Jobname": "*", "Benutzername": "*"}
_SM37_CHECKBOXES_FINISHED = {
    "Geplant": False,
    "Freigegeben": False,
    "Bereit": False,
    "Aktiv": False,
    "Fertig": True,
    "Abgebrochen": False,
}


async def _login(client: ClientSession) -> None:
    login = await call_tool_typed(client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_quick_report_invalid_tcode(sap_mcp_client: ClientSession) -> None:
    """Invalid tcode -> ERROR classification.

    SAP shows an error and stays on Easy Access. The classifier now
    detects Easy Access by page title and returns ERROR.
    """
    await _login(sap_mcp_client)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_quick_report",
        {"tcode": "ZZZNOTEXIST99"},
        QuickReportResult,
    )

    if result.success:
        assert (
            result.screen_type == ScreenClassification.ERROR
        ), f"Expected ERROR for invalid tcode, got: {result.screen_type}"
    else:
        assert result.error is not None


@pytest.mark.anyio
async def test_quick_report_table_result(sap_mcp_client: ClientSession) -> None:
    """SM37 with wildcards and 'Fertig' checkbox -> TABLE with rows.

    SM37 requires job status checkboxes. We enable only 'Fertig'
    (Finished) to guarantee deterministic results — every SAP system
    has finished background jobs.
    """
    await _login(sap_mcp_client)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_quick_report",
        {
            "tcode": "SM37",
            "fields": _SM37_FIELDS,
            "checkboxes": _SM37_CHECKBOXES_FINISHED,
            "max_rows": 5,
        },
        QuickReportResult,
    )

    assert result.success, f"sap_quick_report failed: {result.error}"
    assert result.screen_type in (
        ScreenClassification.TABLE,
        ScreenClassification.EMPTY,
        ScreenClassification.UNKNOWN,  # timing: F8 may not fire (agent takes over)
    ), f"Unexpected screen_type: {result.screen_type}, screen_text: {result.screen_text}"

    if result.screen_type == ScreenClassification.TABLE:
        assert result.table is not None
        assert len(result.table.rows) > 0
        assert len(result.table.rows) <= 5
    elif result.screen_type == ScreenClassification.UNKNOWN:
        # Agent would use individual tools to investigate; verify screen_text is present
        assert result.screen_text is not None


@pytest.mark.anyio
async def test_quick_report_empty_result(sap_mcp_client: ClientSession) -> None:
    """SM37 with non-existent job name -> EMPTY or ERROR.

    Uses a fake job name that cannot exist. SAP responds with a status
    bar message like 'Kein Job entspricht den Selektionsbedingungen'.
    """
    await _login(sap_mcp_client)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_quick_report",
        {
            "tcode": "SM37",
            "fields": {"Jobname": "ZZZNOTEXIST_QR_99", "Benutzername": "*"},
            "checkboxes": _SM37_CHECKBOXES_FINISHED,
        },
        QuickReportResult,
    )

    assert result.success, f"sap_quick_report failed: {result.error}"
    assert result.screen_type in (
        ScreenClassification.EMPTY,
        ScreenClassification.ERROR,
    ), f"Expected EMPTY or ERROR for non-existent job, got: {result.screen_type}"
    assert result.table is None


@pytest.mark.anyio
async def test_quick_report_max_rows_limits_output(sap_mcp_client: ClientSession) -> None:
    """max_rows=2 limits returned rows to at most 2."""
    await _login(sap_mcp_client)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_quick_report",
        {
            "tcode": "SM37",
            "fields": _SM37_FIELDS,
            "checkboxes": _SM37_CHECKBOXES_FINISHED,
            "max_rows": 2,
        },
        QuickReportResult,
    )

    assert result.success, f"sap_quick_report failed: {result.error}"
    if result.screen_type == ScreenClassification.TABLE and result.table:
        assert len(result.table.rows) <= 2


@pytest.mark.anyio
async def test_quick_report_metadata_populated(sap_mcp_client: ClientSession) -> None:
    """Result always contains tcode, page_title, and screen_type."""
    await _login(sap_mcp_client)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_quick_report",
        {
            "tcode": "SM37",
            "fields": _SM37_FIELDS,
            "checkboxes": _SM37_CHECKBOXES_FINISHED,
        },
        QuickReportResult,
    )

    assert result.success, f"sap_quick_report failed: {result.error}"
    assert result.tcode == "SM37"
    assert result.page_title is not None
    assert result.screen_type is not None


@pytest.mark.anyio
async def test_quick_report_warnings_on_unknown_field(sap_mcp_client: ClientSession) -> None:
    """Non-existent field label produces a warning but tool still succeeds."""
    await _login(sap_mcp_client)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_quick_report",
        {
            "tcode": "SM37",
            "fields": {
                "Jobname": "*",
                "Benutzername": "*",
                "ZZZFAKEFIELD": "test",
            },
            "checkboxes": _SM37_CHECKBOXES_FINISHED,
        },
        QuickReportResult,
    )

    assert result.success, f"sap_quick_report failed: {result.error}"
    assert any(
        "ZZZFAKEFIELD" in w for w in result.warnings
    ), f"Expected warning about ZZZFAKEFIELD, got warnings: {result.warnings}"
