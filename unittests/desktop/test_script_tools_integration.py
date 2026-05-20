"""Integration tests for sap_run_script against a live SAP GUI session."""

import sys

import pytest

from sapwebguimcp.tools.script_tools import _run_in_sandbox
from unittests.desktop.conftest import skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_script_reads_window_title(backend):
    """Script reads the main window title and outputs it."""
    script = 'output(session.find_by_id("wnd[0]").text)'
    session = backend.require_session()
    result = await backend.com.run(lambda: _run_in_sandbox(script, session))
    assert result.success, f"Failed: {result.error}"
    assert isinstance(result.output, list)
    assert len(result.output) == 1
    assert isinstance(result.output[0], str)
    assert len(result.output[0]) > 0


@skip_no_sap
@pytest.mark.anyio
async def test_script_loop_collects_multiple_outputs(backend):
    """Script calls output(i) for i in range(3) — collects [0, 1, 2]."""
    script = "for i in range(3):\n    output(i)"
    session = backend.require_session()
    result = await backend.com.run(lambda: _run_in_sandbox(script, session))
    assert result.success, f"Failed: {result.error}"
    assert result.output == [0, 1, 2]


@skip_no_sap
@pytest.mark.anyio
async def test_script_conditional_branching(backend):
    """Script branches on window title length and outputs the correct branch."""
    script = (
        'title = session.find_by_id("wnd[0]").text\n'
        "if len(title) > 0:\n"
        '    output("has_title")\n'
        "else:\n"
        '    output("no_title")\n'
    )
    session = backend.require_session()
    result = await backend.com.run(lambda: _run_in_sandbox(script, session))
    assert result.success, f"Failed: {result.error}"
    assert result.output == ["has_title"]


@skip_no_sap
@pytest.mark.anyio
async def test_script_runtime_error_preserves_partial_output(backend):
    """Partial output collected before an error is preserved in the result."""
    script = 'output("before")\nraise ValueError("intentional")'
    session = backend.require_session()
    result = await backend.com.run(lambda: _run_in_sandbox(script, session))
    assert not result.success
    assert result.error is not None
    assert "ValueError" in result.error
    assert result.output == ["before"]


@skip_no_sap
@pytest.mark.anyio
async def test_script_import_raises_name_error_not_import_error(backend):
    """import is blocked and must surface as NameError (core security contract)."""
    script = "import os"
    session = backend.require_session()
    result = await backend.com.run(lambda: _run_in_sandbox(script, session))
    assert not result.success
    assert result.error is not None
    assert result.error.startswith("NameError"), f"Expected NameError, got: {result.error}"


@skip_no_sap
@pytest.mark.anyio
async def test_script_empty_output_succeeds(backend):
    """An empty script completes successfully with an empty output list."""
    script = ""
    session = backend.require_session()
    result = await backend.com.run(lambda: _run_in_sandbox(script, session))
    assert result.success, f"Failed: {result.error}"
    assert result.output == []
