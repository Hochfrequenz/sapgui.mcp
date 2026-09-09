"""Integration tests for SE38 (ABAP Editor) on desktop backend."""

import sys

import pytest

from sapguimcp.tools.se38_edit_tools import _edit_check_activate, _navigate_and_open_editor_desktop
from unittests.desktop.conftest import TEST_REPORT, go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_TEST_REPORT = TEST_REPORT


@skip_no_sap
@pytest.mark.anyio
async def test_se38_navigate_and_read_source(backend):
    """SE38: navigate to report and read source code via desktop backend."""
    nav_error = await _navigate_and_open_editor_desktop(backend, _TEST_REPORT)
    assert nav_error is None, f"Navigation failed: {nav_error}"

    source = await backend.read_editor_source()
    assert source is not None, "read_editor_source returned None"
    assert len(source) > 0, "Source should not be empty"
    assert _TEST_REPORT in source.upper(), f"Source should contain report name {_TEST_REPORT}"
    lines = [l.strip() for l in source.split("\n") if l.strip()]
    assert any("REPORT" in l.upper() for l in lines), "Should contain REPORT statement"
    assert any("WRITE" in l.upper() for l in lines), "Should contain WRITE statement"
    await go_home(backend)


def _trim(text: str) -> list[str]:
    """Split source into lines, ignoring trailing whitespace and blank lines.

    The editor pads its own buffer, so only these differences are tolerated —
    everything else is corruption (#859).
    """
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


@skip_no_sap
@pytest.mark.anyio
async def test_se38_replace_and_revert(backend):
    """SE38: replace source code, verify byte-for-byte, then revert to original."""
    nav_error = await _navigate_and_open_editor_desktop(backend, _TEST_REPORT)
    assert nav_error is None, f"Navigation failed: {nav_error}"

    # Read original source
    original = await backend.read_editor_source()
    assert original is not None, "Could not read original source"

    # Replace with modified source
    modified = f"REPORT {_TEST_REPORT}.\nWRITE: / 'DESKTOP EDIT TEST'."
    replaced = await backend.replace_editor_source(modified)
    assert replaced, "replace_editor_source failed"

    # The buffer must match exactly — the old code appended a stale line (#859)
    after_replace = await backend.read_editor_source()
    assert after_replace is not None
    assert _trim(after_replace) == _trim(modified), f"Editor buffer does not match what was written: {after_replace!r}"

    # Revert to original
    reverted = await backend.replace_editor_source(original)
    assert reverted, "Could not revert to original source"
    after_revert = await backend.read_editor_source()
    assert after_revert is not None
    assert _trim(after_revert) == _trim(original), "Revert did not restore the original source"

    # Check and activate the reverted source
    result = await backend.check_and_activate()
    assert result.success, f"Check/activate failed: {result.messages}"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se38_edit_source_ending_in_closing_statement(backend):
    """SE38: a source whose last line closes a block must not gain a stale copy (#859).

    The old code could not select the editor's last row, so it survived the
    clear and was appended after the new source — producing a duplicated
    ``ENDFORM.`` and a SYNTAX_ERROR at runtime.
    """
    nav_error = await _navigate_and_open_editor_desktop(backend, _TEST_REPORT)
    assert nav_error is None, f"Navigation failed: {nav_error}"
    original = await backend.read_editor_source()
    assert original, "Could not read original source"
    await go_home(backend)

    form_source = "\n".join(
        [
            f"REPORT {_TEST_REPORT}.",
            "",
            "PERFORM validate_and_save.",
            "",
            "FORM validate_and_save.",
            "  WRITE 'MCP test report'.",
            "ENDFORM.",
        ]
    )

    try:
        result = await _edit_check_activate(backend, _TEST_REPORT, form_source)
        assert result.success, f"Edit workflow failed: {result.error}"
        assert result.activated, f"Activation not confirmed: {result.check_messages}"
        assert _trim(result.backup_source) == _trim(original), "backup_source lost or gained a line"

        nav_error = await _navigate_and_open_editor_desktop(backend, _TEST_REPORT)
        assert nav_error is None, f"Navigation failed: {nav_error}"
        persisted = await backend.read_editor_source()
        assert persisted is not None
        assert _trim(persisted) == _trim(form_source), (
            f"Persisted source does not match what was written: {persisted!r}"
        )
        assert _trim(persisted).count("ENDFORM.") == 1, "ENDFORM. was duplicated (#859)"
    finally:
        # Always put the canonical test report back, whatever happened above.
        await go_home(backend)
        await _edit_check_activate(backend, _TEST_REPORT, original)
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se38_full_edit_check_activate(backend):
    """SE38: full _edit_check_activate workflow preserves working code."""
    # Read current source for reference
    nav_error = await _navigate_and_open_editor_desktop(backend, _TEST_REPORT)
    assert nav_error is None
    original = await backend.read_editor_source()
    assert original is not None
    await go_home(backend)

    # Run the full workflow with the SAME source (no-op edit)
    result = await _edit_check_activate(backend, _TEST_REPORT, original)
    assert result.success, f"Edit workflow failed: {result.error}"
    assert result.program_name == _TEST_REPORT
    assert result.backup_source, "Should have saved a backup"
    assert result.activated
    await go_home(backend)
