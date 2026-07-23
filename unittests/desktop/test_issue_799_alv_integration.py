"""Integration tests for issue #799 against a live SAP system.

Regression coverage for two ALV/table-tool crashes:

* ``sap_read_table`` raised a pydantic ``end_row >= 1`` validation error when a
  grid reported zero rows (an internally-computed ``end_row=0``).
* ``sap_click_table_cell`` surfaced a raw ``list index out of range`` when the
  grid reported no columns.

The SM12 (*Enqueue Administration*) result ALV from the original report renders
as a splitter with several nested grids and, when no locks are held, an empty
grid — the exact shape that triggered both crashes. SE16N/TSTC gives a reliably
populated ALV for the positive path.
"""

from __future__ import annotations

import sys
from typing import Any, cast

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_read_table_empty_alv_does_not_crash(backend):
    """SM12 result ALV (empty when no locks) must not raise the end_row>=1 error."""
    await backend.enter_transaction("SM12")
    await backend.press_key("F8")  # execute -> result ALV (possibly empty)

    # Must not raise a pydantic ValidationError from an internal end_row=0.
    result = await backend.read_table(start_row=1, max_rows=10)

    assert result.success is True
    assert isinstance(result.rows, list)
    # The regression: end_row must never be the out-of-range 0. It is either
    # None (nothing read) or a valid 1-indexed row consistent with the rows
    # actually returned.
    if result.rows:
        assert result.end_row == result.start_row + len(result.rows) - 1
    else:
        assert result.end_row is None
    assert isinstance(result.model_dump_json(), str)

    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_click_table_cell_out_of_range_gives_clear_error(backend):
    """Clicking a cell on the empty SM12 grid returns a clear column error,
    not a raw ``list index out of range``."""
    await backend.enter_transaction("SM12")
    await backend.press_key("F8")

    result = await backend.click_table_cell(row=1, column=0)

    # On an empty grid this cannot succeed, but the error must be intelligible.
    if not result.success:
        assert "list index out of range" not in (result.error or "")

    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_read_table_populated_alv_returns_rows(backend):
    """SE16N/TSTC is a reliably populated ALV: read_table returns rows with a
    valid end_row (guards against the fix nulling non-empty results)."""
    await backend.enter_transaction("SE16N")

    def _fill_table_name() -> None:
        session = backend.require_session()
        field = session.find_by_id("wnd[0]/usr/ctxtGD-TAB", raise_error=False)
        if field is not None:
            cast(Any, field).text = "TSTC"
            cast(Any, session.find_by_id("wnd[0]")).send_v_key(0)  # Enter

    await backend.com.run(_fill_table_name)
    await backend.press_key("F8")  # execute

    result = await backend.read_table(start_row=1, max_rows=5)

    assert result.success is True
    assert len(result.rows) > 0
    assert len(result.headers) > 0
    assert result.end_row is not None
    assert result.end_row >= result.start_row

    await go_home(backend)
    # dismiss a possible "leave without saving" popup left by SE16N
    for _ in range(2):
        await backend.press_key("Enter")
