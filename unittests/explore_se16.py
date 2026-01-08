"""
Exploratory script for SE16N data browser.

Run with: python -m pytest unittests/explore_se16.py -v -s
"""

import asyncio
from pathlib import Path

import pytest
from mcp import ClientSession

from unittests.conftest import sap_mcp_client  # noqa: F401

SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se16_exploration"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _get_content_text(content_item) -> str:
    """Extract text from MCP content item."""
    if hasattr(content_item, "text"):
        return content_item.text
    return str(content_item)


@pytest.mark.anyio
async def test_explore_se16n_small_table(sap_mcp_client: ClientSession) -> None:
    """Explore SE16N with small table T000."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert result.content, "Login failed"

    # Navigate to SE16N
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16N"})
    text = _get_content_text(result.content[0])
    print(f"\n=== SE16N navigation result ===\n{text[:500]}")

    # Get initial screen snapshot
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot = _get_content_text(result.content[0])
    (SNAPSHOTS_DIR / "se16n_initial.yaml").write_text(snapshot, encoding="utf-8")
    print(f"\nSaved initial snapshot ({len(snapshot)} chars)")

    # Fill table name T000
    result = await sap_mcp_client.call_tool(
        "sap_set_field",
        {"label": "Table", "value": "T000"}
    )
    text = _get_content_text(result.content[0])
    print(f"\nSet field result: {text[:200]}")

    # Execute with F8
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    text = _get_content_text(result.content[0])
    print(f"\nF8 result: {text[:200]}")

    # Wait a bit for results
    await asyncio.sleep(1)

    # Get results snapshot
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot = _get_content_text(result.content[0])
    (SNAPSHOTS_DIR / "se16n_t000_results.yaml").write_text(snapshot, encoding="utf-8")
    print(f"\nSaved T000 results snapshot ({len(snapshot)} chars)")
    print(f"\nFirst 2000 chars of snapshot:\n{snapshot[:2000]}")


@pytest.mark.anyio
async def test_explore_se16n_larger_table(sap_mcp_client: ClientSession) -> None:
    """Explore SE16N with larger table TSTC (transaction codes)."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert result.content, "Login failed"

    # Navigate to SE16N
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16N"})

    # Get initial screen to see available fields
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot = _get_content_text(result.content[0])
    print(f"\n=== SE16N initial screen fields ===")
    # Look for textbox and spinbutton elements
    for line in snapshot.split("\n"):
        if "textbox" in line.lower() or "spinbutton" in line.lower() or "maximum" in line.lower():
            print(line.encode("ascii", "replace").decode("ascii"))

    # Fill table name TSTC
    result = await sap_mcp_client.call_tool(
        "sap_set_field",
        {"label": "Table", "value": "TSTC"}
    )

    # Try to set max rows if field exists
    result = await sap_mcp_client.call_tool(
        "sap_set_field",
        {"label": "Maximum No. of Hits", "value": "100"}
    )
    text = _get_content_text(result.content[0])
    print(f"\nSet max hits result: {text[:200]}")

    # Execute with F8
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})

    await asyncio.sleep(2)

    # Get results snapshot
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot = _get_content_text(result.content[0])
    (SNAPSHOTS_DIR / "se16n_tstc_results.yaml").write_text(snapshot, encoding="utf-8")
    print(f"\nSaved TSTC results snapshot ({len(snapshot)} chars)")

    # Count rows in snapshot
    row_count = snapshot.count("- row ")
    print(f"\nRows found in snapshot: {row_count}")

    # Look for pagination elements
    print("\n=== Looking for pagination elements ===")
    for line in snapshot.split("\n"):
        if any(x in line.lower() for x in ["page", "next", "previous", "seite", ">>", "<<"]):
            print(line)

    # Print a sample of the grid data
    print("\n=== Sample of grid data ===")
    in_grid = False
    line_count = 0
    for line in snapshot.split("\n"):
        if "grid:" in line.lower():
            in_grid = True
        if in_grid:
            print(line)
            line_count += 1
            if line_count > 50:
                print("... (truncated)")
                break


@pytest.mark.anyio
async def test_explore_se16n_clipboard(sap_mcp_client: ClientSession) -> None:
    """Explore clipboard export in SE16N."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert result.content, "Login failed"

    # Navigate to SE16N and query T000
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16N"})
    await sap_mcp_client.call_tool("sap_set_field", {"label": "Table", "value": "T000"})
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await asyncio.sleep(1)

    # Try to select all (Ctrl+A)
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "Control+a"})
    text = _get_content_text(result.content[0])
    print(f"\nCtrl+A result: {text[:200]}")

    await asyncio.sleep(0.5)

    # Get snapshot after select
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot = _get_content_text(result.content[0])
    (SNAPSHOTS_DIR / "se16n_after_select_all.yaml").write_text(snapshot, encoding="utf-8")

    # Try Ctrl+C to copy
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "Control+c"})
    text = _get_content_text(result.content[0])
    print(f"\nCtrl+C result: {text[:200]}")

    await asyncio.sleep(0.5)

    # Check for popup
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot = _get_content_text(result.content[0])
    (SNAPSHOTS_DIR / "se16n_after_copy.yaml").write_text(snapshot, encoding="utf-8")
    print(f"\nSnapshot after copy ({len(snapshot)} chars)")

    # Look for dialogs or popups
    if "dialog" in snapshot.lower() or "popup" in snapshot.lower():
        print("Found dialog/popup after copy!")
        print(snapshot[:1500])


@pytest.mark.anyio
async def test_explore_se16n_export_button(sap_mcp_client: ClientSession) -> None:
    """Explore Export button functionality in SE16N."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert result.content, "Login failed"

    # Navigate to SE16N and query T000
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16N"})
    await sap_mcp_client.call_tool("sap_set_field", {"label": "Table", "value": "T000"})
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await asyncio.sleep(1)

    # Click Export button
    result = await sap_mcp_client.call_tool("sap_click", {"label": "Export"})
    text = _get_content_text(result.content[0])
    print(f"\nExport button result: {text[:300]}")

    await asyncio.sleep(0.5)

    # Get snapshot to see export options/dialog
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot = _get_content_text(result.content[0])
    (SNAPSHOTS_DIR / "se16n_export_menu.yaml").write_text(snapshot, encoding="utf-8")
    print(f"\nSaved export menu snapshot ({len(snapshot)} chars)")

    # Look for menu items
    print("\n=== Export menu options ===")
    for line in snapshot.split("\n"):
        if "menuitem" in line.lower() or "menu" in line.lower() or "spreadsheet" in line.lower() or "clipboard" in line.lower() or "local" in line.lower():
            print(line.encode("ascii", "replace").decode("ascii"))


@pytest.mark.anyio
async def test_explore_se16n_scroll(sap_mcp_client: ClientSession) -> None:
    """Explore scrolling/pagination in SE16N with larger result set."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert result.content, "Login failed"

    # Navigate to SE16N and query TSTC without limit
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16N"})
    await sap_mcp_client.call_tool("sap_set_field", {"label": "Table", "value": "TSTC"})

    # Execute
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await asyncio.sleep(2)

    # Get initial results
    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot1 = _get_content_text(result.content[0])
    row_count1 = snapshot1.count("- row ")
    print(f"\nInitial rows in snapshot: {row_count1}")

    # Try Page Down
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "PageDown"})
    await asyncio.sleep(1)

    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot2 = _get_content_text(result.content[0])
    row_count2 = snapshot2.count("- row ")
    print(f"Rows after PageDown: {row_count2}")

    # Check if content changed
    if snapshot1 != snapshot2:
        print("Content changed after PageDown - pagination works!")
        (SNAPSHOTS_DIR / "se16n_tstc_page2.yaml").write_text(snapshot2, encoding="utf-8")
    else:
        print("Content same after PageDown - may be showing all data or pagination different")

    # Try Ctrl+End to go to last page
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "Control+End"})
    await asyncio.sleep(1)

    result = await sap_mcp_client.call_tool("browser_snapshot", {})
    snapshot3 = _get_content_text(result.content[0])
    (SNAPSHOTS_DIR / "se16n_tstc_last_page.yaml").write_text(snapshot3, encoding="utf-8")
    row_count3 = snapshot3.count("- row ")
    print(f"Rows after Ctrl+End: {row_count3}")

    # Look for total row count indicator
    print("\n=== Looking for total count ===")
    for line in snapshot3.split("\n"):
        if any(x in line.lower() for x in ["entries", "einträge", "rows", "zeilen", "total"]):
            print(line)
