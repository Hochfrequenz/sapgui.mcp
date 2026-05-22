"""
Integration tests for SPRO (Customizing IMG) search tool.

These tests run against a real SAP system to verify the end-to-end
sap_spro_search tool workflow.
"""

import json
import tempfile
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult
from sapguimcp.models.spro_models import SPROFileSummary, SPROSearchResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_spro_search_with_results(sap_mcp_client: ClientSession) -> None:
    """Search for 'Land' which returns results in DE."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_spro_search",
        {"query": "Land"},
        SPROSearchResult,
    )
    assert result.success, f"Search failed: {result.error}"
    assert result.activity_count > 0
    assert len(result.activities) > 0
    assert result.query == "Land"

    # Verify activities have names
    for activity in result.activities:
        assert activity.activity_name


@pytest.mark.anyio
async def test_spro_search_no_results(sap_mcp_client: ClientSession) -> None:
    """Search for a term unlikely to return results."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_spro_search",
        {"query": "zzznonexistentterm999"},
        SPROSearchResult,
    )
    # Should succeed but with no results
    assert result.success
    assert result.activity_count == 0


@pytest.mark.anyio
async def test_spro_search_output_file(sap_mcp_client: ClientSession) -> None:
    """Search with output_file writes JSON and returns summary."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = str(Path(tmpdir) / "spro_results.json")

        result = await call_tool_typed(
            sap_mcp_client,
            "sap_spro_search",
            {"query": "Land", "output_file": output_path},
            SPROFileSummary,
        )
        assert result.success, f"Search failed: {result.error}"
        assert result.activity_count > 0
        assert result.query == "Land"
        assert len(result.sample_activities) <= 5

        # Verify JSON file was written
        written = Path(output_path)
        assert written.exists()
        data = json.loads(written.read_text(encoding="utf-8"))
        assert data["query"] == "Land"
        assert len(data["activities"]) == result.activity_count


@pytest.mark.anyio
async def test_spro_search_utilities_customizing(sap_mcp_client: ClientSession) -> None:
    """Search for IS-U (Branchenkomponente Versorgungsindustrie) customizing activities.

    Verifies SPRO can find customizing entries related to German Utilities
    (Energieversorger / IS-U). Searching 'Gerätemanagement' should return
    activities from the IS-U Device Management area of the IMG — a core
    sub-module of Branchenkomponente Versorgungsindustrie.

    Key IS-U SPRO areas include:
    - Gerätemanagement / Device Management (installation, meter reading, billing)
    - Vertragskontokorrent / Contract Account (FI-CA subsidiary ledger)
    - Abrechnungsmodul / Billing Module
    - Energy Data Management (IS-U-EDM)
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_spro_search",
        {"query": "Gerätemanagement"},
        SPROSearchResult,
    )
    assert result.success, f"Search failed: {result.error}"

    # IS-U (Gerätemanagement) may not be installed on all SAP systems.
    # If the search succeeds with results, verify they're from the IS-U domain.
    if result.activity_count == 0:
        pytest.skip("IS-U module not installed — 'Gerätemanagement' returned no customizing activities")

    all_names = " ".join(a.activity_name for a in result.activities)
    all_areas = " ".join(a.area for a in result.activities)
    combined = (all_names + " " + all_areas).lower()
    assert any(
        term in combined
        for term in [
            "gerät",
            "versorgung",
            "device",
            "utilities",
            "zähler",
            "meter",
            "ablesung",
        ]
    ), (
        "No IS-U related activity found in results: " f"{[a.activity_name for a in result.activities[:5]]}"
    )
