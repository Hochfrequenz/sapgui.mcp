"""Tests for browser manager singleton initialization."""

import asyncio

import pytest

import sapguimcp.backend.webgui.browser as browser_module


def test_get_browser_manager_init_lock_is_per_event_loop() -> None:
    """The singleton init lock must be recreated when the event loop changes."""

    async def get_lock() -> asyncio.Lock:
        return browser_module._get_browser_manager_init_lock()

    original_lock = browser_module._browser_manager_init_lock
    original_lock_loop = browser_module._browser_manager_init_lock_loop
    try:
        with asyncio.Runner() as first_runner:
            first_lock = first_runner.run(get_lock())
        with asyncio.Runner() as second_runner:
            second_lock = second_runner.run(get_lock())

        assert first_lock is not second_lock
    finally:
        browser_module._browser_manager_init_lock = original_lock
        browser_module._browser_manager_init_lock_loop = original_lock_loop


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
