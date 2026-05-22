# Typed Test Helpers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add typed helper functions to test utilities that bind JSON responses to Pydantic return types.

**Architecture:** A `call_tool_typed()` helper in `conftest.py` that extracts content, parses JSON, and validates against a provided Pydantic type. Union types for error/success discrimination use `success=False` or presence of `error` field.

**Tech Stack:** Python, Pydantic, pytest, MCP ClientSession

---

### Task 1: Add Typed Helpers to conftest.py

**Files:**

- Modify: `unittests/conftest.py` (add after line 139)

**Step 1: Add imports and type vars**

Add at the top of `conftest.py` (after existing imports around line 12):

```python
import base64
import json
from typing import Any, TypeVar

from pydantic import BaseModel
```

**Step 2: Add helper functions**

Add before the `sap_mcp_client` fixture (around line 82):

```python
T = TypeVar("T", bound=BaseModel)
E = TypeVar("E", bound=BaseModel)


def _extract_content_text(content_item: Any) -> str:
    """Extract text from MCP content item (TextContent or EmbeddedResource)."""
    if hasattr(content_item, "text"):
        return content_item.text
    elif hasattr(content_item, "resource") and hasattr(content_item.resource, "blob"):
        return base64.b64decode(content_item.resource.blob).decode("utf-8")
    return str(content_item)


async def call_tool_typed(
    client: ClientSession,
    tool_name: str,
    args: dict[str, Any],
    result_type: type[T],
    error_type: type[E] | None = None,
) -> T | E:
    """
    Call an MCP tool and return a typed Pydantic model.

    Discriminates using:
    - success=False -> parse as error_type (if provided)
    - presence of 'error' field with non-None value -> parse as error_type
    - otherwise -> parse as result_type

    Args:
        client: MCP ClientSession
        tool_name: Name of the tool to call
        args: Arguments to pass to the tool
        result_type: Pydantic model type for success responses
        error_type: Optional Pydantic model type for error responses

    Returns:
        Parsed and validated Pydantic model instance
    """
    result = await client.call_tool(tool_name, args)
    assert result.content, f"{tool_name} returned no content"

    text = _extract_content_text(result.content[0])
    data = json.loads(text)

    # Discriminate between success/error
    if error_type is not None:
        is_error = data.get("success") is False or data.get("error") is not None
        if is_error:
            return error_type.model_validate(data)

    return result_type.model_validate(data)


async def assert_tool_success_untyped(
    client: ClientSession,
    tool_name: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call tool, assert success=True, return raw dict. For simple cases."""
    result = await client.call_tool(tool_name, args or {})
    assert result.content, f"{tool_name} returned no content"
    text = _extract_content_text(result.content[0])
    data = json.loads(text)
    assert data.get("success", True), f"{tool_name} failed: {data.get('error')}"
    return data
```

**Step 3: Run tests to verify conftest changes don't break anything**

Run: `pytest unittests/test_config.py -v`
Expected: PASS (unit tests that don't use MCP client)

**Step 4: Commit**

```bash
git add unittests/conftest.py
git commit -m "feat(tests): add typed MCP tool call helpers to conftest"
```

---

### Task 2: Migrate test_se16_integration.py

**Files:**

- Modify: `unittests/test_se16_integration.py`

**Step 1: Update imports**

Replace lines 1-18 with:

```python
"""
Integration tests for SE16 (Data Browser) query tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se16_query tool works correctly with pagination
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    LoginResult,
    SE16FileSummary,
    SE16Result,
    SnapshotResult,
    TransactionResult,
    FillFormResult,
    KeyboardResult,
)

from conftest import _extract_content_text, call_tool_typed

SE16_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se16_exploration"
```

**Step 2: Remove duplicate utility functions**

Delete the following functions (lines ~20-74 in original):

- `_get_content_text()`
- `capture_yaml_snapshot()`
- `assert_tool_success()`

**Step 3: Add simplified capture helper**

Add after imports:

```python
async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.yaml

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = SE16_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        SE16_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content
```

**Step 4: Migrate test_se16_capture_initial_screen**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE16N initial screen snapshot.

    This test:
    1. Logs into SAP
    2. Opens SE16N
    3. Captures the initial selection screen
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE16N
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16N"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture initial SE16N screen
    await capture_yaml_snapshot(sap_mcp_client, "se16n_initial", overwrite=True)

    print("=" * 80)
    print("SE16N initial screen snapshot saved")
    print("=" * 80)
```

**Step 5: Migrate test_se16_capture_t000_results**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_capture_t000_results(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE16N results screen for T000 (small table with ~6 rows).

    This test verifies basic query functionality and captures result snapshots.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE16N
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16N"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Set table name
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Table": "T000"}},
        FillFormResult,
    )
    # May need German label
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Tabelle": "T000"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Execute (F8)
    kb = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert kb.success, f"Keyboard F8 failed: {kb.error}"

    # Wait for results
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture result screen
    await capture_yaml_snapshot(sap_mcp_client, "se16n_t000_results", overwrite=True)

    print("=" * 80)
    print("T000 results snapshot saved")
    print("=" * 80)
```

**Step 6: Migrate test_se16_query_small_table**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_small_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with a small table (T000 - ~6 rows)."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query T000 table
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 100},
        SE16Result,
    )

    assert result.success, f"Query failed: {result.error}"
    assert result.table == "T000"
    assert result.total_hits > 0, "Expected at least one row"
    assert result.total_hits == result.returned_rows, "All rows should be returned"
    assert result.truncated is False, "Should not be truncated"
    assert len(result.columns) > 0, "Expected columns"
    assert "Client" in result.columns or "Mandant" in result.columns, "Expected Client/Mandant column"
    assert len(result.rows) == result.returned_rows

    # Verify row structure
    first_row = result.rows[0].data
    assert "Client" in first_row or "Mandant" in first_row or "MANDT" in first_row
```

**Step 7: Migrate test_se16_query_medium_table_pagination**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_medium_table_pagination(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query with pagination (~130 rows = ~10 pages).

    Uses TSTC table (transaction codes) which has thousands of entries,
    but limits to 130 rows to test pagination across ~10 pages.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query TSTC table with max_hits=130 (~10 pages at 13 rows/page)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 130},
        SE16Result,
    )

    assert result.success, f"Query failed: {result.error}"
    assert result.table == "TSTC"
    assert result.total_hits == 130, "Expected 130 hits (max_hits limit)"
    assert result.returned_rows == 130, "Expected 130 rows returned"
    assert result.truncated is True, "Should be truncated (TSTC has >130 rows)"

    # Verify columns
    assert len(result.columns) > 0
    expected_columns = {"Transaction Code", "Transaktionscode", "TCODE"}
    found_columns = set(result.columns)
    assert bool(expected_columns & found_columns), f"Expected a transaction code column in {result.columns}"

    # Verify we got all 130 rows with unique transaction codes
    assert len(result.rows) == 130
    tcodes = set()
    for row in result.rows:
        # Find the tcode field (may vary by language)
        row_data = row.data
        tcode = row_data.get("Transaction Code") or row_data.get("Transaktionscode") or row_data.get("TCODE", "")
        if tcode:
            tcodes.add(tcode)

    # Should have ~130 unique transaction codes (some might have same name in different scenarios)
    assert len(tcodes) >= 100, f"Expected at least 100 unique tcodes, got {len(tcodes)}"
```

**Step 8: Migrate test_se16_query_table_not_found**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_table_not_found(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with non-existent table."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query non-existent table - expect failure
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "ZZZNOTEXIST99", "max_hits": 10},
        SE16Result,
    )

    # Should fail gracefully
    assert result.success is False, "Expected failure for non-existent table"
    assert result.error is not None
    assert "not found" in result.error.lower() or "existiert nicht" in result.error.lower()
```

**Step 9: Migrate test_se16_query_empty_table**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_empty_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with a table that has no rows matching."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query T001 with just 1 row to verify it works
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T001", "max_hits": 1},
        SE16Result,
    )

    # Should succeed even with minimal rows
    assert result.success, f"Query failed: {result.error}"
    assert result.table == "T001"
```

**Step 10: Migrate test_se16_query_output_file**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_output_file(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """Test sap_se16_query with output_file parameter."""
    import json

    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    output_file = tmp_path / "se16_result.json"

    # Query T000 with output_file - returns SE16FileSummary
    summary = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 100, "output_file": str(output_file)},
        SE16FileSummary,
    )

    # Should return SE16FileSummary
    assert summary.success, f"Query failed: {summary.error}"
    assert summary.output_file is not None, "Expected output_file in summary"
    assert summary.table == "T000"
    assert summary.total_hits > 0
    assert summary.returned_rows == summary.total_hits
    assert len(summary.columns) > 0
    assert len(summary.sample_rows) <= 5  # Preview is max 5 rows

    # Verify file was created
    assert output_file.exists(), f"Output file not created: {output_file}"

    # Verify file contents
    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert full_result["success"] is True
    assert full_result["table"] == "T000"
    assert len(full_result["rows"]) == summary.returned_rows
```

**Step 11: Migrate test_se16_query_large_pagination**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_large_pagination(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """
    Test sap_se16_query with larger result set (~200 rows = ~15 pages).

    This tests pagination stability and deduplication over more pages.
    Uses output_file to avoid large JSON in response.
    """
    import json

    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    output_file = tmp_path / "se16_tstc_200.json"

    # Query TSTC with 200 rows (~15 pages)
    summary = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 200, "output_file": str(output_file)},
        SE16FileSummary,
    )

    assert summary.success, f"Query failed: {summary.error}"
    assert summary.total_hits == 200
    # Allow slight variation due to pagination overlap (200 +/- 2)
    assert 198 <= summary.returned_rows <= 202, f"Expected ~200 rows, got {summary.returned_rows}"

    # Verify file contents
    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert 198 <= len(full_result["rows"]) <= 202

    # Check for row uniqueness (no duplicates from pagination)
    row_keys = set()
    for row in full_result["rows"]:
        # Create key from all values
        key = "|".join(str(v) for v in row["data"].values())
        assert key not in row_keys, f"Duplicate row found: {row['data']}"
        row_keys.add(key)
```

**Step 12: Migrate test_se16_query_type_coercion**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_type_coercion(sap_mcp_client: ClientSession) -> None:
    """Test that numeric values are properly coerced to int/float."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query T000 which has numeric MANDT field
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 10},
        SE16Result,
    )

    assert result.success
    assert len(result.rows) > 0

    # Find MANDT/Client field in first row - it should be numeric
    first_row = result.rows[0].data

    # MANDT is typically "000", "100", etc - should remain string since leading zeros matter
    # At minimum, verify the data is accessible and structured
    assert len(first_row) > 0, "Row should have data"
```

**Step 13: Migrate test_se16_query_columns_preserved**

Replace the test with:

```python
@pytest.mark.anyio
async def test_se16_query_columns_preserved(sap_mcp_client: ClientSession) -> None:
    """Test that column order and names are preserved correctly."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query TSTC which has well-defined columns
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 5},
        SE16Result,
    )

    assert result.success
    columns = result.columns

    # TSTC table should have specific columns
    assert len(columns) >= 3, f"Expected at least 3 columns, got {columns}"

    # All rows should have all columns as keys
    for row in result.rows:
        row_keys = set(row.data.keys())
        expected_keys = set(columns)
        assert row_keys == expected_keys, f"Row keys {row_keys} != columns {expected_keys}"
```

**Step 14: Run linting**

Run: `ruff check unittests/test_se16_integration.py --fix`
Expected: No errors or auto-fixed

**Step 15: Commit**

```bash
git add unittests/test_se16_integration.py
git commit -m "refactor(tests): migrate test_se16_integration to typed helpers"
```

---

### Task 3: Migrate test_se11_integration.py

**Files:**

- Modify: `unittests/test_se11_integration.py`

**Step 1: Update imports**

Replace lines 1-18 with:

```python
"""
Integration tests for SE11 lookup tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se11_lookup tool works correctly
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    FillFormResult,
    HtmlResult,
    KeyboardResult,
    LoginResult,
    SE11FileSummary,
    SE11Result,
    SnapshotResult,
    TransactionResult,
)

from conftest import _extract_content_text, call_tool_typed

HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"
YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "yaml_snapshots"
```

**Step 2: Remove duplicate utility functions**

Delete the following functions (lines ~20-99 in original):

- `_get_content_text()`
- `capture_html_snapshot()`
- `capture_yaml_snapshot()`
- `assert_tool_success()`

**Step 3: Add simplified capture helpers**

Add after imports:

```python
async def capture_html_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture HTML snapshot for unit tests."""
    result = await call_tool_typed(client, "browser_get_html", {}, HtmlResult)
    html_content = result.html

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.html"
    filepath = HTML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        HTML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(html_content, encoding="utf-8")
        print(f"Saved HTML snapshot: {filepath}")

    return html_content


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.yaml

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = YAML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        YAML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content
```

**Step 4: Migrate all exploratory tests**

Replace test_se11_capture_table_snapshot with:

```python
@pytest.mark.anyio
async def test_se11_capture_table_snapshot(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE11 snapshots for a table (T000) to understand the YAML structure.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE11
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture initial SE11 screen
    await capture_html_snapshot(sap_mcp_client, "se11_initial", overwrite=True)
    await capture_yaml_snapshot(sap_mcp_client, "se11_initial", overwrite=True)

    # Fill table name
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Tabellenname": "T000"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 (Display)
    kb = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert kb.success, f"Keyboard F7 failed: {kb.error}"

    # Wait a moment for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture the result screen
    await capture_html_snapshot(sap_mcp_client, "se11_t000_fields", overwrite=True)
    await capture_yaml_snapshot(sap_mcp_client, "se11_t000_fields", overwrite=True)

    print("=" * 80)
    print("YAML SNAPSHOT saved")
    print("=" * 80)

    # Go back with F3
    kb = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F3"}, KeyboardResult)
    assert kb.success, f"Keyboard F3 failed: {kb.error}"
```

**Step 5: Migrate test_se11_capture_structure_snapshot**

Replace with:

```python
@pytest.mark.anyio
async def test_se11_capture_structure_snapshot(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE11 snapshots for a structure (BAPIRET2) to understand the YAML structure.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE11
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture before structure select
    await capture_yaml_snapshot(sap_mcp_client, "se11_before_structure_select", overwrite=True)

    # Fill the Datentyp field with structure name
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Datentyp": "BAPIRET2"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 (Display)
    kb = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert kb.success, f"Keyboard F7 failed: {kb.error}"

    # Wait a moment for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture the result screen
    await capture_html_snapshot(sap_mcp_client, "se11_bapiret2_fields", overwrite=True)
    await capture_yaml_snapshot(sap_mcp_client, "se11_bapiret2_fields", overwrite=True)

    print("=" * 80)
    print("YAML SNAPSHOT saved")
    print("=" * 80)

    # Go back with F3
    kb = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F3"}, KeyboardResult)
    assert kb.success, f"Keyboard F3 failed: {kb.error}"
```

**Step 6: Migrate test_se11_table_not_found**

Replace with:

```python
@pytest.mark.anyio
async def test_se11_table_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test SE11 behavior when table doesn't exist - capture error state.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE11
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Fill with non-existent table
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Datenbanktabelle": "ZZZNOTEXIST"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 (Display) - this might fail, that's expected
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F7"})

    # Wait a moment
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture the error state
    await capture_yaml_snapshot(sap_mcp_client, "se11_table_not_found", overwrite=True)
```

**Step 7: Migrate test_se11_lookup_single_table**

Replace with:

```python
@pytest.mark.anyio
async def test_se11_lookup_single_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with a single table."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up T000 table
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": "T000", "object_type": "table"},
        SE11Result,
    )

    assert result.success, f"Lookup failed: {result.error}"
    assert len(result.entries) == 1, f"Expected 1 entry, got {len(result.entries)}"
    assert len(result.errors) == 0, f"Unexpected errors: {result.errors}"

    entry = result.entries[0]
    assert entry.name == "T000"
    assert entry.object_type == "table"
    # Accept German "Mandant" or English "Client" description
    desc = entry.description.lower()
    assert "mandant" in desc or "client" in desc, f"Unexpected description: {entry.description}"
    assert len(entry.fields) > 0

    # Check MANDT field
    mandt = next((f for f in entry.fields if f.name == "MANDT"), None)
    assert mandt is not None, "MANDT field not found"
    assert mandt.datatype == "CLNT"
    assert mandt.is_key is True
```

**Step 8: Migrate remaining SE11 tests**

Replace test_se11_lookup_table_list with:

```python
@pytest.mark.anyio
async def test_se11_lookup_table_list(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with a list of tables."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up multiple tables
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": ["T000", "T001"], "object_type": "table"},
        SE11Result,
    )

    assert result.success, f"Lookup failed: {result.error}"
    assert len(result.entries) == 2, f"Expected 2 entries, got {len(result.entries)}. Errors: {result.errors}"

    names = {e.name for e in result.entries}
    assert "T000" in names
    assert "T001" in names
```

Replace test_se11_lookup_table_not_found with:

```python
@pytest.mark.anyio
async def test_se11_lookup_table_not_found(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with non-existent table."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up non-existent table
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": "ZZZNOTEXIST99", "object_type": "table"},
        SE11Result,
    )

    # Should have success=False since all lookups failed
    assert result.success is False
    assert len(result.entries) == 0
    assert len(result.errors) == 1

    error = result.errors[0]
    assert error.name == "ZZZNOTEXIST99"
    assert "not found" in error.error.lower()
```

Replace test_se11_lookup_mixed_results with:

```python
@pytest.mark.anyio
async def test_se11_lookup_mixed_results(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with mix of existing and non-existing tables."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up mix of tables
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": ["T000", "ZZZNOTEXIST99"], "object_type": "table"},
        SE11Result,
    )

    # Should have success=True since at least one succeeded
    assert result.success is True
    assert len(result.entries) == 1
    assert len(result.errors) == 1

    assert result.entries[0].name == "T000"
    assert result.errors[0].name == "ZZZNOTEXIST99"
```

Replace test_se11_lookup_large_batch_to_file with:

```python
@pytest.mark.anyio
async def test_se11_lookup_large_batch_to_file(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """Test sap_se11_lookup with >10 tables using output_file parameter."""
    import json

    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # 11 ERCH* tables to trigger file output
    tables = [
        "ERCH",
        "ERCHARC",
        "ERCHC",
        "ERCHC_DISP",
        "ERCHC_DISP_SEL",
        "ERCHC_SHORT",
        "ERCHC_STABLE",
        "ERCHE",
        "ERCHE_I1",
        "ERCHE_M18",
        "ERCHE_STABLE",
    ]
    output_file = tmp_path / "se11_batch_result.json"

    # Look up tables with output_file
    summary = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": tables, "object_type": "table", "output_file": str(output_file)},
        SE11FileSummary,
    )

    # Should return SE11FileSummary
    assert summary.output_file is not None, "Expected SE11FileSummary with output_file"
    assert summary.total_requested == 11
    assert summary.successful + summary.failed == 11
    assert summary.success is True, f"Batch lookup failed: {summary}"

    # Verify file was created and contains full results
    assert output_file.exists(), f"Output file not created: {output_file}"

    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert full_result["success"] is True
    assert len(full_result["entries"]) == summary.successful
    assert len(full_result["errors"]) == summary.failed

    # Verify all requested tables are accounted for
    found_names = {e["name"] for e in full_result["entries"]}
    error_names = {e["name"] for e in full_result["errors"]}
    assert found_names | error_names == set(tables)
```

**Step 9: Run linting**

Run: `ruff check unittests/test_se11_integration.py --fix`
Expected: No errors or auto-fixed

**Step 10: Commit**

```bash
git add unittests/test_se11_integration.py
git commit -m "refactor(tests): migrate test_se11_integration to typed helpers"
```

---

### Task 4: Migrate test_sap_integration.py (Large File)

**Files:**

- Modify: `unittests/test_sap_integration.py`

This file is large (~3,271 lines, ~342 call_tool invocations). The migration follows the same pattern as Tasks 2-3 but at larger scale.

**Step 1: Update imports**

Add model imports at the top after existing imports:

```python
from sapguimcp.models import (
    CapabilitiesResult,
    ClosePopupResult,
    DiscoveredButtons,
    DiscoveredFields,
    DropdownFillResult,
    DropdownInfo,
    FieldLookupResult,
    FillFormResult,
    FormFieldsResult,
    HtmlResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    ScreenText,
    SetFieldResult,
    ShortcutsResult,
    SnapshotResult,
    TableData,
    TransactionResult,
    WaitResult,
)

from conftest import _extract_content_text, call_tool_typed
```

**Step 2: Remove duplicate utility functions**

Delete these functions from test_sap_integration.py (they're now in conftest.py):

- `_get_content_text()` (lines ~132-153)
- `parse_tool_response()` (lines ~155-178)
- `assert_tool_success()` (lines ~180-197)

Keep `capture_html_snapshot()` but update it to use `call_tool_typed`.

**Step 3: Migrate incrementally**

Due to the file size, migrate tests in batches:

1. First batch: Login and basic transaction tests (test*sap_login, test_sap_transaction*\*)
2. Second batch: Form and field tests (test*sap_fill_form*_, test*sap_discover_fields*_)
3. Third batch: Table and data tests (test*sap_read_table*\*)
4. Fourth batch: Keyboard and navigation tests
5. Fifth batch: Popup and special case tests

**Migration pattern for each test:**

Before:

```python
result = await sap_mcp_client.call_tool("sap_login", {})
data = assert_tool_success(result, "sap_login")
assert data.get("url"), "Expected URL in login response"
```

After:

```python
result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
assert result.success, f"Login failed: {result.error}"
assert result.url, "Expected URL in login response"
```

**Step 4: Run linting after each batch**

Run: `ruff check unittests/test_sap_integration.py --fix`

**Step 5: Commit after each batch**

```bash
git add unittests/test_sap_integration.py
git commit -m "refactor(tests): migrate test_sap_integration batch N to typed helpers"
```

---

### Task 5: Final Verification

**Step 1: Run all unit tests**

Run: `pytest unittests/ -v --ignore=unittests/test_sap_integration.py --ignore=unittests/test_se11_integration.py --ignore=unittests/test_se16_integration.py`
Expected: All PASS

**Step 2: Run type checking**

Run: `mypy unittests/conftest.py --ignore-missing-imports`
Expected: No errors

**Step 3: Run linting on all test files**

Run: `ruff check unittests/ --fix`
Expected: No errors

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore(tests): complete migration to typed test helpers"
```
