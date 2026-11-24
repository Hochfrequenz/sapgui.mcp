"""Integration tests for the SE37 (Function Builder) edit tool on the desktop backend."""

import sys

import pytest

from sapguimcp.tools.se37_edit_tools import (
    _edit_check_activate_fm,
    _open_fm_in_change_mode_desktop,
    _open_source_tab_desktop,
)
from unittests.desktop.conftest import TEST_FUNCTION_MODULE, go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def _trim(text: str) -> list[str]:
    """Split source into lines, ignoring trailing whitespace and blank lines (the editor pads its own buffer)."""
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


async def _open_source(pack, backend) -> None:
    nav_error = await _open_fm_in_change_mode_desktop(backend, TEST_FUNCTION_MODULE, pack)
    assert nav_error is None, f"Navigation failed: {nav_error}"
    tab_error = await _open_source_tab_desktop(backend, TEST_FUNCTION_MODULE, pack)
    assert tab_error is None, f"Source tab failed: {tab_error}"


@skip_no_sap
@pytest.mark.anyio
async def test_se37_navigate_and_read_source(pack, backend):
    """SE37: open the function module in change mode and read its source."""
    await _open_source(pack, backend)
    source = await backend.read_editor_source()
    await go_home(backend)
    assert source, "Source should not be empty"
    assert any(line.strip().upper().startswith("FUNCTION") for line in source.split("\n")), source


@skip_no_sap
@pytest.mark.anyio
async def test_se37_nonexistent_function_module_is_reported(pack, backend):
    """SE37: a function module that does not exist is an error, not a change mode switch."""
    error = await _open_fm_in_change_mode_desktop(backend, "Z_MCP_NO_SUCH_FM", pack)
    await go_home(backend)
    assert error, "A missing function module must be reported"


@skip_no_sap
@pytest.mark.anyio
async def test_se37_full_edit_check_activate(pack, backend):
    """SE37: the whole workflow with the unchanged source (no-op edit) activates."""
    await _open_source(pack, backend)
    original = await backend.read_editor_source()
    assert original
    await go_home(backend)

    result = await _edit_check_activate_fm(backend, TEST_FUNCTION_MODULE, original, pack)
    await go_home(backend)
    assert result.success, f"Edit workflow failed: {result.error}"
    assert result.function_module == TEST_FUNCTION_MODULE
    assert _trim(result.backup_source) == _trim(original)
    assert result.activated


@skip_no_sap
@pytest.mark.anyio
async def test_se37_edit_persists_and_is_reverted(pack, backend):
    """SE37: edit the function module, verify the persisted source, and always restore the original."""
    await _open_source(pack, backend)
    original = await backend.read_editor_source()
    assert original
    await go_home(backend)

    modified = (
        original.rstrip().removesuffix("ENDFUNCTION.").rstrip() + "\n  WRITE 'DESKTOP SE37 EDIT TEST'.\nENDFUNCTION."
    )
    try:
        result = await _edit_check_activate_fm(backend, TEST_FUNCTION_MODULE, modified, pack)
        assert result.success, f"Edit workflow failed: {result.error}"
        assert result.activated, f"Activation not confirmed: {result.check_messages}"
        await go_home(backend)

        await _open_source(pack, backend)
        persisted = await backend.read_editor_source()
        assert persisted is not None
        assert _trim(persisted) == _trim(modified), f"Persisted source does not match: {persisted!r}"
    finally:
        # Always put the test function module back. A failed restore fails the test, but never masks an earlier error.
        test_failed = sys.exc_info()[0] is not None
        try:
            await go_home(backend)
            restored = await _edit_check_activate_fm(backend, TEST_FUNCTION_MODULE, original, pack)
            await go_home(backend)
            cleanup_error = None if restored.success and restored.activated else f"restore failed: {restored.error}"
        except Exception as exc:  # pylint: disable=broad-except
            cleanup_error = f"restore raised: {exc!r}"
        if cleanup_error:
            print(f"WARNING: could not restore {TEST_FUNCTION_MODULE}: {cleanup_error}")
            if not test_failed:
                pytest.fail(
                    f"Cleanup of {TEST_FUNCTION_MODULE} failed, the test object may be left modified: {cleanup_error}"
                )


@skip_no_sap
@pytest.mark.anyio
async def test_se37_broken_source_is_reverted_and_reactivated(pack, backend):
    """SE37: a syntax error makes the tool restore and re-activate the original source (#862)."""
    await _open_source(pack, backend)
    original = await backend.read_editor_source()
    assert original
    await go_home(backend)

    broken = original.rstrip() + "\nENDFUNCTION."  # a second ENDFUNCTION, like the duplicated ENDFORM of #859
    try:
        result = await _edit_check_activate_fm(backend, TEST_FUNCTION_MODULE, broken, pack)
        assert not result.success, "A syntax error must fail the edit"
        assert "Auto-reverted to original source and re-activated successfully" in (result.error or ""), result.error
        await go_home(backend)

        await _open_source(pack, backend)
        assert _trim(await backend.read_editor_source() or "") == _trim(original)
    finally:
        await go_home(backend)
