"""``sap_spro_search``: the scope note of a partial (desktop) search reaches the caller, also with ``output_file``."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.models.spro_models import SPROActivity, SPROSearchResult
from sapguimcp.tools.spro_tools import _DESKTOP_SCOPE_NOTE, register_spro_tools


def _desktop_result() -> SPROSearchResult:
    return SPROSearchResult(
        query="x",
        activities=[SPROActivity(activity_name="A", parent_node="P", area="P")],
        activity_count=1,
        retrieved_at=datetime.now(UTC),
        scope_note=_DESKTOP_SCOPE_NOTE,
    )


async def _call(arguments: dict[str, str]) -> dict[str, object]:
    server = FastMCP("t")
    register_spro_tools(server)
    backend = MagicMock()
    backend.backend_type = "desktop"
    with (
        patch("sapguimcp.tools.spro_tools.get_backend", new=AsyncMock(return_value=backend)),
        patch("sapguimcp.tools.spro_tools._search_img_desktop", new=AsyncMock(return_value=_desktop_result())),
    ):
        async with Client(server) as client:
            raw = await client.call_tool("sap_spro_search", {"query": "x", **arguments})
    return json.loads(raw.content[0].text)  # type: ignore[no-any-return]


@pytest.mark.anyio
async def test_the_inline_result_carries_the_scope_note() -> None:
    data = await _call({})
    assert data["scope_note"] == _DESKTOP_SCOPE_NOTE


@pytest.mark.anyio
async def test_the_file_summary_carries_the_scope_note(tmp_path: Path) -> None:
    out = tmp_path / "spro.json"
    data = await _call({"output_file": str(out)})
    assert data["scope_note"] == _DESKTOP_SCOPE_NOTE
    assert json.loads(out.read_text(encoding="utf-8"))["scope_note"] == _DESKTOP_SCOPE_NOTE
