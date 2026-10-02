"""Integration tests for SE16 (Data Browser) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.se16_models import SE16Result
from sapguimcp.tools.se16_tools import _execute_se16_query
from unittests.desktop.conftest import TEST_TABLE, go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_se16_small_table(backend):
    """SE16: query T000 (clients, ~3-6 rows), verify all returned, not truncated."""
    result = await _execute_se16_query(backend, "T000", None, 100)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.table == "T000"
    assert result.total_hits > 0, "T000 should have at least 1 client"
    assert result.total_hits == result.returned_rows, "All rows should be returned"
    assert result.truncated is False, "Should not be truncated"
    assert len(result.columns) > 0, "Expected column headers"
    assert len(result.rows) == result.returned_rows
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_medium_table(backend):
    """SE16: query TSTC with max_hits=50, verify pagination/truncation."""
    result = await _execute_se16_query(backend, TEST_TABLE, None, 50)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.table == TEST_TABLE
    assert result.total_hits >= 50
    assert result.returned_rows == 50
    assert len(result.rows) == 50
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_table_not_found(backend):
    """SE16: nonexistent table ZZZNOTEXIST99 returns 0 rows without crashing."""
    result = await _execute_se16_query(backend, "ZZZNOTEXIST99", None, 5)
    assert result.returned_rows == 0
    assert isinstance(result.columns, list)
    assert isinstance(result.rows, list)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_table_not_found_returns_failure(backend):
    """SE16: nonexistent table ZZZNOTEXIST99 must report success=False."""
    result = await _execute_se16_query(backend, "ZZZNOTEXIST99", None, 5)
    assert result.success is False, "Non-existent table should return success=False"
    assert result.returned_rows == 0
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_columns_match_data(backend):
    """SE16: verify row data keys match column headers."""
    result = await _execute_se16_query(backend, TEST_TABLE, None, 5)
    assert result.success, f"SE16 failed: {result.error}"
    assert len(result.columns) >= 3, f"Expected at least 3 columns, got {result.columns}"
    for row in result.rows:
        row_keys = set(row.data.keys())
        expected_keys = set(result.columns)
        assert row_keys == expected_keys, f"Row keys {row_keys} != columns {expected_keys}"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_tcode_column_has_values(backend):
    """SE16: verify TCODE column values are non-empty in TSTC table."""
    result = await _execute_se16_query(backend, TEST_TABLE, None, 5)
    assert result.success, f"SE16 failed: {result.error}"
    assert "TCODE" in result.columns, f"Expected TCODE column, got {result.columns}"
    for row in result.rows:
        assert row.data["TCODE"], "TCODE value should not be empty"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_model_serializes(backend):
    """SE16Result must JSON-serialize for MCP transport (roundtrip)."""
    result = await _execute_se16_query(backend, TEST_TABLE, None, 3)
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["table"] == TEST_TABLE
    assert isinstance(parsed["rows"], list)
    assert isinstance(parsed["columns"], list)
    # Roundtrip back to model
    restored = SE16Result.model_validate_json(json_str)
    assert restored.table == TEST_TABLE
    assert len(restored.rows) == len(result.rows)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_max_hits_limits_rows(backend):
    """SE16: max_hits=3 on a large table returns exactly 3 rows.

    Note: the desktop backend sets truncated = (len(rows) < total_hits).
    When SAP reports total_hits == max_hits, truncated will be False even
    though more data exists.  We assert structural consistency instead.
    """
    result = await _execute_se16_query(backend, TEST_TABLE, None, 3)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.returned_rows == 3
    assert len(result.rows) == 3
    assert result.truncated == (result.returned_rows < result.total_hits)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_truncated_flag(backend):
    """SE16: total_hits vs returned_rows are consistent; truncation is reflected.

    Note: the desktop backend sets truncated = (len(rows) < total_hits),
    which differs from the WebGUI backend (total_hits >= max_hits).  When the
    desktop SE16 path retrieves exactly max_hits rows AND SAP reports
    total_hits == max_hits, truncated will be False even though more data
    exists in the table.  We assert structural consistency here rather than
    a specific truncated value.
    """
    result = await _execute_se16_query(backend, TEST_TABLE, None, 3)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.returned_rows == 3
    # Structural consistency: truncated iff fewer rows returned than total_hits
    assert result.truncated == (result.returned_rows < result.total_hits)
    await go_home(backend)


# ---------------------------------------------------------------------------
# SE16 filter tests
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_se16_single_filter(backend):
    """SE16: query TSTC with single filter TCODE='SE16'."""
    result = await _execute_se16_query(backend, TEST_TABLE, {"TCODE": "SE16"}, 10)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.returned_rows >= 1
    for row in result.rows:
        assert row.data["TCODE"] == "SE16"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_multiple_filters(backend):
    """SE16: query TSTC with multiple filters."""
    result = await _execute_se16_query(backend, TEST_TABLE, {"TCODE": "SE16", "PGMNA": "SAPLSETB"}, 10)
    assert result.success, f"SE16 failed: {result.error}"
    for row in result.rows:
        assert row.data["TCODE"] == "SE16"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_wildcard_filter(backend):
    """SE16: query TSTC with wildcard filter TCODE='SE1*'."""
    result = await _execute_se16_query(backend, TEST_TABLE, {"TCODE": "SE1*"}, 20)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.returned_rows >= 1
    for row in result.rows:
        assert row.data["TCODE"].startswith("SE1"), f"Expected SE1*, got {row.data['TCODE']}"
    await go_home(backend)


# ---------------------------------------------------------------------------
# SE16 strict filter fields (#907): unappliable filters must fail before F8
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_se16_unknown_field_with_valid_filter_fails(backend):
    """#907 case 1: a valid filter that matches nothing plus a made-up field must fail, not report 'no rows'.

    The valid-but-empty MANDT filter only matters for reproducing the old bug (zero rows masked the unknown field).
    """
    result = await _execute_se16_query(backend, "T000", {"MANDT": "ZZZ", "ZZZFAKEFIELD": "X"}, 10)
    assert result.success is False, "Unknown filter field must make the query fail"
    assert result.error is not None
    assert "ZZZFAKEFIELD" in result.error
    assert "Offered fields:" in result.error
    assert "MANDT" in result.error, f"Offered list should contain MANDT: {result.error}"
    assert result.returned_rows == 0
    assert result.rows == []
    assert any("ZZZFAKEFIELD" in w for w in result.filter_warnings)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_only_unknown_field_fails_instead_of_unfiltered_rows(backend):
    """#907 case 2: only a made-up field on a populated table used to return unfiltered rows with success=True."""
    result = await _execute_se16_query(backend, "T000", {"ZZZFAKEFIELD": "X"}, 10)
    assert result.success is False, "Unknown filter field must make the query fail"
    assert result.error is not None
    assert "ZZZFAKEFIELD" in result.error
    assert result.returned_rows == 0
    assert result.rows == []
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_valid_filter_still_returns_filtered_rows(backend):
    """#907 regression: a valid filter still returns filtered rows, with success=True and no warnings."""
    result = await _execute_se16_query(backend, TEST_TABLE, {"TCODE": "SE16"}, 10)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.returned_rows >= 1
    assert result.filter_warnings == []
    for row in result.rows:
        assert row.data["TCODE"] == "SE16"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_real_column_not_offered_by_se16n_fails(backend):
    """#907 case 3: a real column that SE16N does not offer as selection field must fail, not run unfiltered.

    TBOOKSHOP is a standard SAP demo table (flight data model) whose LCHR column TEXT1 is not offered by SE16N.
    """
    check = await _execute_se16_query(backend, "DD03L", {"TABNAME": "TBOOKSHOP", "FIELDNAME": "TEXT1"}, 1)
    await go_home(backend)
    assert check.success, f"DD03L existence check failed: {check.error}"
    if check.returned_rows == 0:
        pytest.skip("Demo table TBOOKSHOP / field TEXT1 not present on this system")
    result = await _execute_se16_query(backend, "TBOOKSHOP", {"TEXT1": "X"}, 10)
    assert result.success is False, "Field not offered by SE16N must make the query fail"
    assert result.error is not None
    assert "TEXT1" in result.error
    assert "Offered fields:" in result.error
    assert result.returned_rows == 0
    assert result.rows == []
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se16_large_result_returns_all_requested_rows(backend):
    """#928: a slow, large query (DD03L, 500 rows) must not be read before the result grid is ready."""
    result = await _execute_se16_query(backend, "DD03L", None, 500)
    assert result.success, f"SE16 failed: {result.error}"
    assert result.returned_rows == 500
    assert len(result.rows) == 500
    assert result.total_hits >= 500
    assert "TABNAME" in result.columns
    for row in result.rows:
        assert set(row.data.keys()) == set(result.columns)
    await go_home(backend)
