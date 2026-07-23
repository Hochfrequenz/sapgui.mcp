"""Unit tests for issue #756: BP test isolation.

When a BP integration test fails mid-run (prolonged ``com_call_retry`` loops on
an unresponsive BDT screen), the trailing ``go_home`` call in the test body is
skipped, leaving the SAP application in a COM-saturated state that poisons
subsequent test modules (e.g. SE16).

The fix moves cleanup into a guaranteed teardown (``bp_teardown``) and sinks BP
tests to the end of the desktop collection (``_reorder_bp_last``). These unit
tests pin the extracted, platform-independent logic so it runs in CI.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import unittests.desktop.conftest as ct


class _RecordingBackend:
    def __init__(self, log: list[str] | None = None) -> None:
        self.calls: list[str] = log if log is not None else []

    async def wait_for_ready(self) -> None:
        self.calls.append("wait_for_ready")


@pytest.mark.anyio
async def test_bp_teardown_navigates_home_then_drains(monkeypatch):
    """bp_teardown returns to Easy Access, then drains the COM STA (cool-down).

    Both steps record into one shared log so the assertion pins their order.
    """
    order: list[str] = []

    async def fake_go_home(_backend):
        order.append("go_home")

    monkeypatch.setattr(ct, "go_home", fake_go_home)
    backend = _RecordingBackend(log=order)

    await ct.bp_teardown(backend)

    assert order == ["go_home", "wait_for_ready"]


@pytest.mark.anyio
async def test_bp_teardown_still_drains_when_go_home_fails(monkeypatch):
    """A navigation failure must not skip the COM cool-down, and must not raise."""

    async def boom(_backend):
        raise RuntimeError("com_call_retry storm")

    monkeypatch.setattr(ct, "go_home", boom)
    backend = _RecordingBackend()

    await ct.bp_teardown(backend)  # must not raise

    assert backend.calls == ["wait_for_ready"]


@pytest.mark.anyio
async def test_bp_teardown_swallows_drain_failure(monkeypatch):
    """A failing drain must not surface an exception from teardown."""

    async def fake_go_home(_backend):
        pass

    monkeypatch.setattr(ct, "go_home", fake_go_home)
    backend = MagicMock()

    async def raising_wait():
        raise RuntimeError("still busy")

    backend.wait_for_ready = raising_wait

    await ct.bp_teardown(backend)  # must not raise


def _make_item(nodeid: str):
    item = MagicMock()
    item.nodeid = nodeid
    return item


def test_reorder_bp_last_sinks_bp_tests_to_end():
    """BP integration items move to the end; every other item keeps its order."""
    items = [
        _make_item("unittests/desktop/test_bp_integration.py::test_a"),
        _make_item("unittests/desktop/test_se16_integration.py::test_b"),
        _make_item("unittests/desktop/test_bp_integration.py::test_c"),
        _make_item("unittests/desktop/test_slg1_integration.py::test_d"),
    ]

    ct._reorder_bp_last(items)

    assert [i.nodeid for i in items] == [
        "unittests/desktop/test_se16_integration.py::test_b",
        "unittests/desktop/test_slg1_integration.py::test_d",
        "unittests/desktop/test_bp_integration.py::test_a",
        "unittests/desktop/test_bp_integration.py::test_c",
    ]


def test_reorder_bp_last_noop_without_bp_tests():
    """Ordering is untouched when there are no BP tests."""
    items = [
        _make_item("unittests/desktop/test_se16_integration.py::test_b"),
        _make_item("unittests/desktop/test_slg1_integration.py::test_d"),
    ]

    ct._reorder_bp_last(items)

    assert [i.nodeid for i in items] == [
        "unittests/desktop/test_se16_integration.py::test_b",
        "unittests/desktop/test_slg1_integration.py::test_d",
    ]
