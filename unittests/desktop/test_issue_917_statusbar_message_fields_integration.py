"""Live desktop tests for status bar message class/number/parameters (#917).

Assertions use class, number and parameters only, never the text, so the tests
pass in any logon language.
"""

import sys

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only")


@skip_no_sap
@pytest.mark.anyio
async def test_nonexistent_transaction_message_fields(backend):
    """A nonexistent transaction reports S# 343 with the tcode as &1."""
    try:
        await backend.enter_transaction("/nZZNOSUCHTX")
        sbar = await backend.get_status_bar()
        assert sbar.success
        assert sbar.message_id == "S#"
        assert sbar.message_number == "343"
        assert sbar.message_parameters == ["ZZNOSUCHTX"]
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se38_nonexistent_program_message_fields(backend):
    """SE38 display of a nonexistent program reports DS 017 with the name as &1."""
    try:
        await backend.enter_transaction("SE38")
        session = backend.require_session()

        def _fill() -> None:
            session.find_by_id("wnd[0]/usr/ctxtRS38M-PROGRAMM").text = "ZZNOSUCHPROG"  # type: ignore[union-attr]

        await backend.com.run(_fill)
        await backend.press_key("F7")
        sbar = await backend.get_status_bar()
        assert sbar.success
        assert sbar.message_id == "DS"
        assert sbar.message_number == "017"
        assert sbar.message_parameters == ["ZZNOSUCHPROG"]
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_empty_status_bar_has_no_message_fields(backend):
    """After /n the bar is empty and the new fields are None / []."""
    try:
        await backend.enter_transaction("/n")
        sbar = await backend.get_status_bar()
        assert sbar.success
        assert sbar.message_id is None
        assert sbar.message_number is None
        assert sbar.message_parameters == []
    finally:
        await go_home(backend)
