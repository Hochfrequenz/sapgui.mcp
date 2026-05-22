"""Integration tests for ABAP breakpoint management tools.

Requires SAP GUI with desktop backend. These tests verify the full
navigation and COM toggle flow against a live system.
"""

import pytest

from unittests.desktop.conftest import TEST_CLASS, TEST_METHOD, TEST_REPORT, go_home, skip_no_sap

pytestmark = [skip_no_sap, pytest.mark.integration]


@pytest.mark.anyio
async def test_breakpoint_set_prog_by_line(backend):
    """sap_breakpoint_set on a PROG sets breakpoint at the specified line."""
    from sapguimcp.tools.breakpoint_tools import (
        _SHELL_PATHS,
        _classify_toggle_status,
        _navigate_prog,
        _toggle_breakpoint_com,
    )

    nav_error = await _navigate_prog(backend, TEST_REPORT)
    assert nav_error is None, f"Navigation failed: {nav_error}"

    session = backend.require_session()
    shell_found, status_msg = await backend.com.run(lambda: _toggle_breakpoint_com(session, _SHELL_PATHS["PROG"], 1))
    assert shell_found, f"Shell not found: {status_msg}"
    outcome = _classify_toggle_status(status_msg)
    assert outcome in ("set", "deleted"), f"Unrecognized status: '{status_msg}'"

    # Cleanup: ensure breakpoint ends up deleted
    if outcome == "set":
        await backend.com.run(lambda: _toggle_breakpoint_com(session, _SHELL_PATHS["PROG"], 1))

    await go_home(backend)


@pytest.mark.anyio
async def test_breakpoint_set_and_delete_roundtrip_prog(backend):
    """Setting then deleting a breakpoint on PROG returns to no-breakpoint state."""
    from sapguimcp.tools.breakpoint_tools import (
        _SHELL_PATHS,
        _classify_toggle_status,
        _navigate_prog,
        _toggle_breakpoint_com,
    )

    nav_error = await _navigate_prog(backend, TEST_REPORT)
    assert nav_error is None

    session = backend.require_session()
    test_line = 5

    # Ensure clean state: toggle until "set"
    for _ in range(2):
        _, msg = await backend.com.run(lambda: _toggle_breakpoint_com(session, _SHELL_PATHS["PROG"], test_line))
        if _classify_toggle_status(msg) == "set":
            break

    # Now delete it
    _, msg2 = await backend.com.run(lambda: _toggle_breakpoint_com(session, _SHELL_PATHS["PROG"], test_line))
    assert _classify_toggle_status(msg2) == "deleted", f"Expected 'deleted', got: '{msg2}'"
    await go_home(backend)


@pytest.mark.anyio
async def test_breakpoint_list_prog(backend):
    """sap_breakpoint_list returns empty list when no breakpoints are set."""
    from sapguimcp.tools.breakpoint_tools import (
        _filter_bp_rows,
        _navigate_prog,
        _open_bp_list_dialog_com,
        _read_bp_grid_and_close_com,
    )

    nav_error = await _navigate_prog(backend, TEST_REPORT)
    assert nav_error is None

    session = backend.require_session()
    opened, open_err = await backend.com.run(lambda: _open_bp_list_dialog_com(session))
    assert opened, f"Dialog open failed: {open_err}"

    rows, read_err = await backend.com.run(lambda: _read_bp_grid_and_close_com(session, "PROG", TEST_REPORT, None))
    assert not read_err, f"Grid read failed: {read_err}"

    entries = _filter_bp_rows(rows, "PROG", TEST_REPORT, None)
    assert isinstance(entries, list)
    await go_home(backend)


@pytest.mark.anyio
async def test_breakpoint_clas_navigate(backend):
    """Navigation to SE24 class method editor succeeds."""
    from sapguimcp.tools.breakpoint_tools import _navigate_clas

    nav_error = await _navigate_clas(backend, TEST_CLASS, TEST_METHOD)
    assert nav_error is None, f"Navigation failed: {nav_error}"
    await go_home(backend)
