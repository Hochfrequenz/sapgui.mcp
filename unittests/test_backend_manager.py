"""Tests for BackendManager."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import sapguimcp.backend.manager as manager_module
from sapguimcp.backend.desktop import _current_session_id
from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.backend.manager import (
    BackendManager,
    close_backend,
    get_backend_manager,
    reset_backend_manager,
)


def test_backend_manager_default_type() -> None:
    """Default backend type should be 'webgui'."""
    manager = BackendManager()
    assert manager.backend_type == "webgui"


def test_backend_manager_unknown_type_raises() -> None:
    """Unknown backend type should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown backend type"):
        BackendManager(backend_type="unknown")  # type: ignore[arg-type]


def test_get_backend_manager_reads_settings() -> None:
    """get_backend_manager should read backend_type from settings."""
    reset_backend_manager()
    manager = get_backend_manager()
    assert manager.backend_type == "webgui"
    reset_backend_manager()


def test_close_backend_no_manager() -> None:
    """close_backend should be a no-op when no manager exists."""
    reset_backend_manager()
    asyncio.run(close_backend())  # Should not raise
    reset_backend_manager()


def test_backend_manager_close_clears_caches() -> None:
    """BackendManager.close() should clear internal caches and call close_browser_manager."""
    manager = BackendManager()
    # Simulate cached state
    manager._backends["s1"] = "fake_backend"  # type: ignore[assignment]
    manager._page_ids["s1"] = 12345

    with patch(
        "sapguimcp.backend.manager.close_browser_manager",
        new_callable=AsyncMock,
    ) as mock_close:
        asyncio.run(manager.close())
        mock_close.assert_called_once()

    assert manager._backends == {}
    assert manager._page_ids == {}


# ---------------------------------------------------------------------------
# Desktop dead-thread recovery (issue #628)
#
# These tests exercise BackendManager._recover_desktop_if_dead on Linux by
# building the manager via __new__ (bypassing the Windows platform check)
# and injecting the desktop symbols (`ComThread`, `_current_session_id`) into
# the manager module's namespace — they're normally only imported on Windows.
# ---------------------------------------------------------------------------

# pylint: disable=protected-access,redefined-outer-name,unused-argument


#: Field set BackendManager.__init__ produces, captured from a real (webgui)
#: instance at import time. Used by ``_make_desktop_manager`` to detect when
#: ``__init__`` gains a new field that the test helper has forgotten.
_BACKEND_MANAGER_INIT_FIELDS = set(vars(BackendManager(backend_type="webgui")).keys())


def _make_desktop_manager() -> BackendManager:
    """Build a BackendManager in 'desktop' mode without the platform check.

    Bypasses ``__init__`` so the desktop branch can be tested on Linux. If
    ``BackendManager.__init__`` gains a new field this helper will assert,
    forcing the maintainer to update both places together.
    """
    manager = BackendManager.__new__(BackendManager)
    manager.backend_type = "desktop"
    manager._backends = {}
    manager._page_ids = {}
    manager._com_thread = None
    manager._desktop_recovery_lock = asyncio.Lock()
    actual = set(vars(manager).keys())
    assert actual == _BACKEND_MANAGER_INIT_FIELDS, (
        f"Test helper out of sync with BackendManager.__init__. "
        f"Missing in helper: {_BACKEND_MANAGER_INIT_FIELDS - actual}, "
        f"Extra in helper: {actual - _BACKEND_MANAGER_INIT_FIELDS}"
    )
    return manager


@pytest.fixture
def desktop_symbols(monkeypatch):
    """Inject desktop symbols into the manager module (Linux-safe)."""
    monkeypatch.setattr(manager_module, "ComThread", ComThread, raising=False)
    monkeypatch.setattr(
        manager_module,
        "_current_session_id",
        _current_session_id,
        raising=False,
    )
    yield


@pytest.mark.anyio
async def test_recover_desktop_if_dead_no_op_when_thread_alive(desktop_symbols) -> None:
    """If the cached ComThread is still alive, recovery is a no-op."""
    manager = _make_desktop_manager()
    alive_thread = ComThread(init_com=False, min_interval_ms=0)
    try:
        manager._com_thread = alive_thread
        manager._backends["desktop"] = "sentinel-backend"  # type: ignore[assignment]

        await manager._recover_desktop_if_dead()

        assert manager._com_thread is alive_thread
        assert manager._backends["desktop"] == "sentinel-backend"
    finally:
        alive_thread.shutdown()


@pytest.mark.anyio
async def test_recover_desktop_if_dead_no_op_when_no_thread(desktop_symbols) -> None:
    """If no ComThread was ever created, recovery is a no-op (first-call path)."""
    manager = _make_desktop_manager()
    await manager._recover_desktop_if_dead()
    assert manager._com_thread is None
    assert "desktop" not in manager._backends


@pytest.mark.anyio
async def test_recover_desktop_if_dead_clears_caches_when_dead(desktop_symbols) -> None:
    """When the worker died, recovery drops the ComThread and the backend."""
    manager = _make_desktop_manager()
    dead_thread = ComThread(init_com=False, min_interval_ms=0)
    dead_thread.shutdown()
    assert not dead_thread.is_alive

    manager._com_thread = dead_thread
    manager._backends["desktop"] = "stale-backend"  # type: ignore[assignment]
    # Simulate a stale ContextVar value left behind from before the crash.
    token = _current_session_id.set("s7")
    try:
        await manager._recover_desktop_if_dead()

        assert manager._com_thread is None
        assert "desktop" not in manager._backends
        assert _current_session_id.get() is None  # ContextVar reset
    finally:
        _current_session_id.reset(token)


@pytest.mark.anyio
async def test_recover_desktop_if_dead_concurrent_only_clears_once(desktop_symbols) -> None:
    """Concurrent recovery attempts must serialize and clear caches once.

    Two coroutines hit a dead worker simultaneously. The second one waits
    on the lock; by the time it acquires, the first has already cleared
    `_com_thread` to None, so the re-check inside the lock makes the
    second a no-op. We assert the warning log fires only once.
    """
    manager = _make_desktop_manager()
    dead_thread = ComThread(init_com=False, min_interval_ms=0)
    dead_thread.shutdown()
    assert not dead_thread.is_alive

    manager._com_thread = dead_thread
    manager._backends["desktop"] = "stale-backend"  # type: ignore[assignment]

    with patch.object(manager_module.logger, "warning") as mock_warning:
        await asyncio.gather(
            manager._recover_desktop_if_dead(),
            manager._recover_desktop_if_dead(),
        )

    # Only one rebuild — the second coroutine sees None on the re-check
    # and exits before logging.
    rebuild_logs = [
        call
        for call in mock_warning.call_args_list
        if call.args and call.args[0] == "desktop_com_thread_dead_rebuilding"
    ]
    assert len(rebuild_logs) == 1
    assert manager._com_thread is None
    assert "desktop" not in manager._backends


@pytest.mark.anyio
async def test_recover_desktop_if_dead_blocks_when_lock_held(desktop_symbols) -> None:
    """The recovery lock blocks a second caller while the first holds it.

    Stronger version of the concurrent test above. The previous test passes
    even without the lock because the first coroutine runs the (await-free)
    recovery body to completion before the second one is scheduled. Here we
    pre-acquire the lock externally to simulate "first call is mid-recovery"
    and verify the second call genuinely waits.
    """
    manager = _make_desktop_manager()
    dead_thread = ComThread(init_com=False, min_interval_ms=0)
    dead_thread.shutdown()
    manager._com_thread = dead_thread

    # Pretend "the first caller" is inside the recovery body by holding the lock.
    await manager._desktop_recovery_lock.acquire()
    try:
        recovery_task = asyncio.create_task(manager._recover_desktop_if_dead())
        # Yield control a few times so the task definitely reaches `async with`.
        for _ in range(5):
            await asyncio.sleep(0)
        assert not recovery_task.done(), "recovery should be blocked on the lock"
        # Worker is still dead and caches still populated — the second caller
        # has not yet entered the body.
        assert manager._com_thread is dead_thread
    finally:
        manager._desktop_recovery_lock.release()

    await recovery_task
    # Now the second caller has run: it sees the still-dead thread (the first
    # "caller" we simulated never actually cleared anything), so it clears.
    assert manager._com_thread is None
    assert "desktop" not in manager._backends
