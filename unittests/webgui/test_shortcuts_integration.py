"""Integration tests for shortcut discovery (sap_get_shortcuts)."""

import os

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    LoginResult,
    ShortcutsResult,
)

from .conftest import call_tool_typed
from .integration_helpers import _wait_for_transaction_screen


@pytest.mark.anyio
async def test_sap_get_shortcuts_returns_shortcuts(sap_mcp_client: ClientSession) -> None:
    """Test that sap_get_shortcuts discovers shortcuts from the current screen.

    SAP screens have toolbar buttons with keyboard shortcuts like F5, F8, Strg+S.
    These are exposed in the button's title attribute as "Action (Shortcut)".
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    # Should return list of shortcuts
    shortcuts = data.shortcuts
    assert isinstance(shortcuts, list), f"Expected list of shortcuts: {shortcuts}"

    # SE16 should have at least some common shortcuts (F3=Back, F8=Execute)
    shortcut_keys = [s.shortcut for s in shortcuts]
    assert any(
        "F" in k for k in shortcut_keys
    ), f"Expected at least one F-key shortcut on SE16 screen. Found: {shortcut_keys}"


@pytest.mark.anyio
async def test_sap_get_shortcuts_has_execute_f8(sap_mcp_client: ClientSession) -> None:
    """Test that SE16 screen has F8-related shortcut (Execute).

    Note: Some SAP configurations show "F8" while others show "Strg+F8" (Ctrl+F8).
    This test accepts any shortcut containing "F8".
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")
    if sap_language != "DE":
        pytest.skip("Skipping F8 Execute test in non-DE language environments")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    shortcuts = data.shortcuts
    # Accept any shortcut containing "F8" (plain F8, Strg+F8, Ctrl+F8, etc.)
    print(shortcuts)
    assert any(sc for sc in shortcuts if sc.shortcut == "Strg+F8" and sc.action == "Online Handbuch")
    assert any(sc for sc in shortcuts if sc.shortcut == "Eingabe" and sc.action == "Tabelleninhalt")
    assert any(sc for sc in shortcuts if sc.shortcut == "F7" and sc.action == "Tabelleninhalt")


@pytest.mark.anyio
async def test_sap_get_shortcuts_has_back_f3(sap_mcp_client: ClientSession) -> None:
    """Test that screens have F3 (Back) shortcut."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    shortcuts = data.shortcuts
    f3_shortcuts = [s for s in shortcuts if s.shortcut == "F3"]

    assert (
        len(f3_shortcuts) >= 1
    ), f"Screen should have F3 (Back) shortcut. Found shortcuts: {[s.shortcut for s in shortcuts]}"


@pytest.mark.anyio
async def test_sap_get_shortcuts_no_duplicates(sap_mcp_client: ClientSession) -> None:
    """Test that duplicate shortcuts are not returned."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    shortcuts = data.shortcuts

    # Check for uniqueness
    seen = set()
    for s in shortcuts:
        key = (s.action.lower(), s.shortcut.lower())
        assert key not in seen, f"Duplicate shortcut found: {s}"
        seen.add(key)
