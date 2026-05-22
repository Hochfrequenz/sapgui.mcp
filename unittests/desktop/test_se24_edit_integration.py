"""Integration tests for SE24 (Class Builder) edit on desktop backend."""

import sys

import pytest

from sapguimcp.tools.se24_edit_tools import (
    _edit_check_activate_method,
    _navigate_to_method_editor_desktop,
)
from unittests.desktop.conftest import TEST_CLASS, TEST_METHOD, go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_TEST_CLASS = TEST_CLASS
_TEST_METHOD = TEST_METHOD


@skip_no_sap
@pytest.mark.anyio
async def test_se24_navigate_and_read_method_source(backend):
    """SE24: navigate to class method and read source code via desktop backend."""
    nav_error = await _navigate_to_method_editor_desktop(backend, _TEST_CLASS, _TEST_METHOD)
    assert nav_error is None, f"Navigation failed: {nav_error}"

    source = await backend.read_editor_source()
    assert source is not None, "read_editor_source returned None"
    assert len(source) > 0, "Source should not be empty"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se24_replace_and_revert_method(backend):
    """SE24: replace method source, verify, then revert to original."""
    nav_error = await _navigate_to_method_editor_desktop(backend, _TEST_CLASS, _TEST_METHOD)
    assert nav_error is None, f"Navigation failed: {nav_error}"

    # Read original source
    original = await backend.read_editor_source()
    assert original is not None, "Could not read original source"

    # Replace with modified source
    modified = "    \" Desktop edit test comment\n    WRITE: / 'DESKTOP SE24 TEST'.\n"
    replaced = await backend.replace_editor_source(modified)
    assert replaced, "replace_editor_source failed"

    # Verify the replacement took effect
    after_replace = await backend.read_editor_source()
    assert after_replace is not None
    assert "DESKTOP SE24 TEST" in after_replace

    # Revert to original
    reverted = await backend.replace_editor_source(original)
    assert reverted, "Could not revert to original source"

    # Check and activate the reverted source
    result = await backend.check_and_activate()
    assert result.success, f"Check/activate failed: {result.messages}"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se24_full_edit_check_activate(backend):
    """SE24: full _edit_check_activate_method workflow preserves working code."""
    # Read current source for reference
    nav_error = await _navigate_to_method_editor_desktop(backend, _TEST_CLASS, _TEST_METHOD)
    assert nav_error is None
    original = await backend.read_editor_source()
    assert original is not None
    await go_home(backend)

    # Run the full workflow with the SAME source (no-op edit)
    result = await _edit_check_activate_method(backend, _TEST_CLASS, _TEST_METHOD, original)
    assert result.success, f"Edit workflow failed: {result.error}"
    assert result.class_name == _TEST_CLASS
    assert result.method_name == _TEST_METHOD
    assert result.backup_source, "Should have saved a backup"
    assert result.activated
    await go_home(backend)
