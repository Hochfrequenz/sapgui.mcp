"""Tests for browser manager singleton initialization."""

import asyncio

import pytest

import sapguimcp.backend.webgui.browser as browser_module


@pytest.mark.anyio
async def test_get_browser_manager_waits_for_initialization(monkeypatch) -> None:
    """Concurrent callers must wait for the singleton to finish initializing."""
    original_manager = browser_module._browser_manager
    browser_module._browser_manager = None
    initialize_started = asyncio.Event()
    allow_initialize_to_finish = asyncio.Event()
    initialize_calls = 0

    async def fake_initialize(self) -> None:
        nonlocal initialize_calls
        initialize_calls += 1
        initialize_started.set()
        await allow_initialize_to_finish.wait()
        self._initialized = True

    monkeypatch.setattr(browser_module.BrowserManager, "initialize", fake_initialize)

    try:
        first_task = asyncio.create_task(browser_module.get_browser_manager())
        await initialize_started.wait()

        second_task = asyncio.create_task(browser_module.get_browser_manager())
        await asyncio.sleep(0)
        assert not second_task.done(), "second caller should wait for initialization to finish"

        allow_initialize_to_finish.set()
        first_manager, second_manager = await asyncio.gather(first_task, second_task)

        assert initialize_calls == 1
        assert first_manager is second_manager
        assert second_manager.is_initialized is True
    finally:
        browser_module._browser_manager = original_manager
