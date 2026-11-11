"""WebGuiBackend.get_snapshot exposes read-only grid cell text in the ARIA tree (headless Chromium)."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from playwright.async_api import async_playwright

from sapguimcp.backend.webgui.backend import WebGuiBackend

_HTML = """
<div role="grid"><table><tbody>
  <tr role="row"><th role="columnheader" aria-labelledby="h1-ROOTCNT h1-selectionlabel"><span id="h1-ROOTCNT">Parameter</span></th>
    
    <th role="columnheader" aria-labelledby="h2-ROOTCNT h2-selectionlabel"><span id="h2-ROOTCNT">Typing</span></th>
    </tr>
  
  <span hidden id="h1-selectionlabel">Press space to select the column.</span>
  <span hidden id="h2-selectionlabel">Press space to select the column.</span>
  <tr role="row">
    <td role="gridcell"><span role="textbox" aria-label="Parameter">IV_NAME</span></td>
    <td role="gridcell"><span role="textbox" aria-label="Typing">TYPE</span></td>
  </tr>
  <tr role="row">
    <td role="gridcell"><span role="textbox" aria-label="Parameter">   </span></td>
    <td role="gridcell">PLAIN</td>
  </tr>
</tbody></table></div>
<div role="textbox" aria-label="Outside">not in a grid</div>
"""  # noqa: E501, W293


async def _snapshot_text(html: str) -> str:
    async def snapshot(page: Any) -> str:
        result = await WebGuiBackend(page).get_snapshot()
        return str(result.raw if hasattr(result, "raw") else result)

    return await _on_page(html, snapshot)


async def _on_page(html: str, action: Callable[[Any], Awaitable[str]]) -> str:
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE"))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            reason = f"Chromium cannot be launched here: {str(exc).splitlines()[0]}"
            if os.environ.get("CI"):
                pytest.fail(reason)
            pytest.skip(reason)
        try:
            page = await browser.new_page()
            await page.set_content(html)
            return await action(page)
        finally:
            await browser.close()


@pytest.mark.anyio
async def test_readonly_cell_text_becomes_gridcell_name():
    text = await _snapshot_text(_HTML)
    assert 'gridcell "IV_NAME"' in text
    assert 'gridcell "TYPE"' in text


@pytest.mark.anyio
async def test_blank_and_plain_cells_and_non_grid_textbox_untouched():
    text = await _snapshot_text(_HTML)
    assert "- gridcell:" + chr(10) in text  # blank textbox text leaves the cell unnamed
    assert 'gridcell "PLAIN"' in text
    assert 'textbox "Outside"' in text


@pytest.mark.anyio
async def test_column_header_names_lose_the_selection_hint():
    text = await _snapshot_text(_HTML)
    assert 'columnheader "Parameter"' in text
    assert "Press space" not in text


@pytest.mark.anyio
async def test_overlapping_snapshots_restore_the_dom():
    async def overlapping(page: Any) -> str:
        before = await page.content()
        await asyncio.gather(WebGuiBackend(page).get_snapshot(), WebGuiBackend(page).get_snapshot())
        return "same" if await page.content() == before else "changed"

    assert await _on_page(_HTML, overlapping) == "same"
