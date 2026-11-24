"""Integration tests for sap_quick_report on the desktop backend (needs a real SAP system)."""

import sys

import pytest

from sapguimcp.models.quick_report_models import ScreenClassification
from sapguimcp.tools.quick_report_tools import _execute_quick_report
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_quick_report_runs_the_lock_entry_overview(backend):
    """SM12 (display of lock entries, read-only) exists on every system and has a selection screen.

    Whatever the system holds, the call must end on a result: a list, a grid or "no data".
    """
    result = await _execute_quick_report(backend, tcode="SM12", max_rows=5)
    try:
        assert result.success, result.error
        assert result.screen_type in (
            ScreenClassification.TABLE,
            ScreenClassification.LIST,
            ScreenClassification.EMPTY,
        ), result.model_dump_json(indent=2)
        if result.screen_type == ScreenClassification.TABLE:
            assert result.table is not None
            assert len(result.table.rows) <= 5
        if result.screen_type == ScreenClassification.LIST:
            assert result.list_lines
            assert len(result.list_lines) <= 5
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_quick_report_fails_for_a_transaction_that_does_not_exist(backend):
    result = await _execute_quick_report(backend, tcode="ZZNOSUCHTCODE")
    try:
        assert not result.success
        assert result.error
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_quick_report_does_not_press_f8_when_a_field_is_missing(backend):
    result = await _execute_quick_report(backend, tcode="SM12", fields={"NoSuchFieldLabelXyz": "1"})
    try:
        assert not result.success
        assert "NoSuchFieldLabelXyz" in (result.error or "")
        assert "F8 was not pressed" in (result.error or "")
    finally:
        await go_home(backend)
