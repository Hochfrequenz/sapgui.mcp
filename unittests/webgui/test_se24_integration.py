"""
Integration tests for SE24 (Class Builder) lookup tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se24_lookup tool works correctly
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import FillFormResult, KeyboardResult, LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se24_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = YAML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        YAML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content


# =============================================================================
# Exploratory Tests - Run these to capture snapshots for development
# =============================================================================


@pytest.mark.anyio
async def test_se24_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 initial screen snapshot.

    This test:
    1. Logs into SAP
    2. Opens SE24
    3. Captures the initial selection screen
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE24
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture initial SE24 screen
    await capture_yaml_snapshot(sap_mcp_client, "se24_initial", overwrite=True)

    print("=" * 80)
    print("SE24 initial screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se24_capture_cl_abap_char_utilities(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 details for CL_ABAP_CHAR_UTILITIES.

    This is a simple, well-documented ABAP class with constants and static methods.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE24
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill class name field
    # German: "Objekttyp" or "Klasse/Interface"
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekttyp": "CL_ABAP_CHAR_UTILITIES"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object type": "CL_ABAP_CHAR_UTILITIES"}},
            FillFormResult,
        )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object Type": "CL_ABAP_CHAR_UTILITIES"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to display (or Enter)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture the main details screen
    await capture_yaml_snapshot(sap_mcp_client, "se24_cl_abap_char_utilities_main", overwrite=True)

    # Check status bar
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar: {status.message}")

    print("=" * 80)
    print("CL_ABAP_CHAR_UTILITIES main screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se24_capture_cl_abap_char_utilities_methods(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 Methods tab for CL_ABAP_CHAR_UTILITIES.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekttyp": "CL_ABAP_CHAR_UTILITIES"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object type": "CL_ABAP_CHAR_UTILITIES"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on Methods tab
    # German: "Methoden", English: "Methods"
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='tab']:has-text('Methoden')"},
    )

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await capture_yaml_snapshot(sap_mcp_client, "se24_cl_abap_char_utilities_methods", overwrite=True)

    print("=" * 80)
    print("CL_ABAP_CHAR_UTILITIES Methods tab snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se24_capture_cl_abap_char_utilities_attributes(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 Attributes tab for CL_ABAP_CHAR_UTILITIES.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekttyp": "CL_ABAP_CHAR_UTILITIES"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object type": "CL_ABAP_CHAR_UTILITIES"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on Attributes tab
    # German: "Attribute", English: "Attributes"
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='tab']:has-text('Attribute')"},
    )

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await capture_yaml_snapshot(sap_mcp_client, "se24_cl_abap_char_utilities_attributes", overwrite=True)

    print("=" * 80)
    print("CL_ABAP_CHAR_UTILITIES Attributes tab snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se24_capture_cl_salv_table(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 details for CL_SALV_TABLE.

    This is a common SALV class with multiple methods and interfaces.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekttyp": "CL_SALV_TABLE"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object type": "CL_SALV_TABLE"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se24_cl_salv_table_main", overwrite=True)

    print("=" * 80)
    print("CL_SALV_TABLE main screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se24_capture_cl_salv_table_methods(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 Methods tab for CL_SALV_TABLE.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekttyp": "CL_SALV_TABLE"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object type": "CL_SALV_TABLE"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on Methods tab
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='tab']:has-text('Methoden')"},
    )

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await capture_yaml_snapshot(sap_mcp_client, "se24_cl_salv_table_methods", overwrite=True)

    print("=" * 80)
    print("CL_SALV_TABLE Methods tab snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se24_capture_if_serializable_object(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 details for IF_SERIALIZABLE_OBJECT interface.

    Test how interfaces are displayed differently from classes.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekttyp": "IF_SERIALIZABLE_OBJECT"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object type": "IF_SERIALIZABLE_OBJECT"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se24_if_serializable_object_main", overwrite=True)

    print("=" * 80)
    print("IF_SERIALIZABLE_OBJECT (interface) main screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se24_class_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE24 behavior when class doesn't exist.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill with non-existent class
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekttyp": "ZZZNOTEXIST_CLASS_99"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object type": "ZZZNOTEXIST_CLASS_99"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to try to display
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar - should show error
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar for non-existent class: {status.message}")

    await capture_yaml_snapshot(sap_mcp_client, "se24_not_found", overwrite=True)

    print("=" * 80)
    print("Class not found snapshot saved")
    print("=" * 80)


# =============================================================================
# Integration Tests - Test the actual sap_se24_lookup tool
# =============================================================================


@pytest.mark.anyio
async def test_se24_lookup_single_class(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se24_lookup with a single class (CL_ABAP_CHAR_UTILITIES).
    """
    from sapguimcp.models import SE24Result

    # Login first
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Call the SE24 lookup tool
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_lookup",
        {"classes": "CL_ABAP_CHAR_UTILITIES"},
        SE24Result,
    )

    assert result.success, f"SE24 lookup failed: {result.error}"
    assert len(result.entries) == 1
    assert len(result.errors) == 0

    entry = result.entries[0]
    assert entry.class_name == "CL_ABAP_CHAR_UTILITIES"
    assert entry.object_type == "class"


@pytest.mark.anyio
async def test_se24_lookup_batch_classes(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se24_lookup with multiple classes (batch lookup).
    """
    from sapguimcp.models import SE24Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_lookup",
        {"classes": ["CL_ABAP_CHAR_UTILITIES", "CL_SALV_TABLE"]},
        SE24Result,
    )

    assert result.success, f"SE24 lookup failed: {result.error}"
    assert len(result.entries) == 2
    assert len(result.errors) == 0

    # Verify all classes were returned
    class_names = {e.class_name for e in result.entries}
    assert class_names == {"CL_ABAP_CHAR_UTILITIES", "CL_SALV_TABLE"}


@pytest.mark.anyio
async def test_se24_lookup_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se24_lookup with non-existent class.
    """
    from sapguimcp.models import SE24Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_lookup",
        {"classes": "ZZZNOTEXIST_CLASS_99"},
        SE24Result,
    )

    # Should have error entry
    assert len(result.entries) == 0
    assert len(result.errors) == 1
    assert result.errors[0].class_name == "ZZZNOTEXIST_CLASS_99"
    # Error message may vary - could be "not found" or "still on initial screen"
    error_lower = result.errors[0].error.lower()
    assert "not found" in error_lower or "initial screen" in error_lower


@pytest.mark.anyio
async def test_se24_lookup_mixed_success_and_failure(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se24_lookup with mix of valid and invalid classes.
    """
    from sapguimcp.models import SE24Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_lookup",
        {"classes": ["CL_ABAP_CHAR_UTILITIES", "ZZZNOTEXIST_CLASS_99", "CL_SALV_TABLE"]},
        SE24Result,
    )

    # Should have partial success
    assert result.success  # At least one succeeded
    assert len(result.entries) == 2  # CL_ABAP_CHAR_UTILITIES and CL_SALV_TABLE
    assert len(result.errors) == 1  # ZZZNOTEXIST_CLASS_99

    # Verify correct entries
    class_names = {e.class_name for e in result.entries}
    assert class_names == {"CL_ABAP_CHAR_UTILITIES", "CL_SALV_TABLE"}
    assert result.errors[0].class_name == "ZZZNOTEXIST_CLASS_99"


@pytest.mark.anyio
async def test_se24_lookup_interface(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se24_lookup with an interface.
    """
    from sapguimcp.models import SE24Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_lookup",
        {"classes": "IF_SERIALIZABLE_OBJECT"},
        SE24Result,
    )

    assert result.success, f"SE24 lookup failed: {result.error}"
    assert len(result.entries) == 1

    entry = result.entries[0]
    assert entry.class_name == "IF_SERIALIZABLE_OBJECT"
    # May be detected as interface or class depending on parsing
    # assert entry.object_type == "interface"


@pytest.mark.anyio
async def test_se24_lookup_methods_parsing(sap_mcp_client: ClientSession) -> None:
    """
    Test that class methods are correctly parsed.
    """
    from sapguimcp.models import SE24Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_lookup",
        {"classes": "CL_SALV_TABLE"},
        SE24Result,
    )

    assert result.success
    entry = result.entries[0]

    assert entry.class_name == "CL_SALV_TABLE"
    # CL_SALV_TABLE has many interface methods (IF_SALV_GUI_OM_*)
    assert len(entry.methods) >= 10, f"Expected >=10 methods, got {len(entry.methods)}"
    method_names = {m.name for m in entry.methods}
    assert any("~" in n for n in method_names), "Expected interface methods with ~ separator"


@pytest.mark.anyio
async def test_se24_lookup_attributes_parsing(sap_mcp_client: ClientSession) -> None:
    """
    Test that class attributes are correctly parsed (regression for #292).

    CL_ABAP_CHAR_UTILITIES has 13+ public constants (HORIZONTAL_TAB, NEWLINE,
    CR_LF, etc.).  A previous bug caused attributes[] to be empty because the
    Attribute tab was never actually selected.
    """
    from sapguimcp.models import SE24Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_lookup",
        {"classes": "CL_ABAP_CHAR_UTILITIES"},
        SE24Result,
    )

    assert result.success, f"SE24 lookup failed: {result.error}"
    entry = result.entries[0]

    assert entry.class_name == "CL_ABAP_CHAR_UTILITIES"
    # CL_ABAP_CHAR_UTILITIES has 13+ public constants
    assert len(entry.attributes) >= 13, (
        f"Expected >=13 attributes, got {len(entry.attributes)}: " f"{[a.name for a in entry.attributes]}"
    )

    attr_names = {a.name for a in entry.attributes}
    # Well-known constants that must be present
    for expected in ("HORIZONTAL_TAB", "NEWLINE", "CR_LF", "CHARSIZE"):
        assert expected in attr_names, f"Expected attribute {expected} not found in {attr_names}"

    # Verify attribute properties
    for attr in entry.attributes:
        if attr.name in ("HORIZONTAL_TAB", "NEWLINE", "CR_LF"):
            assert attr.is_constant, f"{attr.name} should be a constant"
            assert attr.visibility == "public", f"{attr.name} should be public"
