"""Integration tests for SPRO (IMG Customizing) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.spro_models import SPROSearchResult
from sapguimcp.tools.spro_tools import _search_img_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_spro_search_finanzwesen(backend):
    """SPRO: search for 'Finanzwesen' returns results from the IMG tree."""
    result = await _search_img_desktop(backend, "Finanzwesen")
    assert isinstance(result, SPROSearchResult)
    assert result.success, f"SPRO search failed: {result.error}"
    assert result.activity_count >= 1, "Should find at least one match for 'Finanzwesen'"
    assert result.query == "Finanzwesen"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_spro_search_no_results(backend):
    """SPRO: search for nonsense returns 0 results."""
    result = await _search_img_desktop(backend, "ZZZXYZNONEXISTENT999")
    assert isinstance(result, SPROSearchResult)
    assert result.success, f"Search should succeed even with 0 results: {result.error}"
    assert result.activity_count == 0
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_spro_model_serializes(backend):
    """SPROSearchResult must JSON-serialize (roundtrip)."""
    result = await _search_img_desktop(backend, "Controlling")
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "query" in parsed
    assert "activities" in parsed
    restored = SPROSearchResult.model_validate_json(json_str)
    assert restored.activity_count == result.activity_count
    await go_home(backend)
