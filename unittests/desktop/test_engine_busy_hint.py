"""Issue #905: sap_session_list surfaces a long-running COM engine call."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.sap_results import SessionInfo
from sapguimcp.tools.session_tools import sap_session_list_impl


def _backend_with_engine(state: dict | None) -> DesktopBackend:
    backend = DesktopBackend.__new__(DesktopBackend)
    backend.com = MagicMock()
    if state is None:
        backend.com.engine_state = None  # attribute missing -> getattr returns None
    else:
        backend.com.engine_state = AsyncMock(return_value=state)
    return backend


class TestComEngineState:
    @pytest.mark.anyio
    async def test_none_when_thread_has_no_engine_state(self):
        backend = _backend_with_engine(None)
        assert await backend.com_engine_state() is None

    @pytest.mark.anyio
    async def test_none_when_idle(self):
        backend = _backend_with_engine({"busy": False, "busy_since_s": None})
        assert await backend.com_engine_state() is None

    @pytest.mark.anyio
    async def test_none_below_threshold(self):
        backend = _backend_with_engine({"busy": True, "busy_since_s": 0.4, "connection": "/app/con[1]"})
        assert await backend.com_engine_state() is None

    @pytest.mark.anyio
    async def test_state_when_busy_past_threshold(self):
        state = {"busy": True, "busy_since_s": 12.5, "connection": "/app/con[1]", "queue_depth": 3}
        backend = _backend_with_engine(state)
        assert await backend.com_engine_state() == state

    @pytest.mark.anyio
    async def test_swallows_engine_state_errors(self):
        backend = _backend_with_engine({"busy": True, "busy_since_s": 99})
        backend.com.engine_state = AsyncMock(side_effect=RuntimeError("boom"))
        assert await backend.com_engine_state() is None


class TestSessionListCarriesEngineHint:
    @pytest.mark.anyio
    async def test_hint_populated_when_engine_busy(self, monkeypatch):
        backend = _backend_with_engine({"busy": True, "busy_since_s": 30.0, "connection": "/app/con[1]"})
        backend.registry = MagicMock()
        backend.registry.list_sessions.return_value = ["s1"]
        backend.registry.primary_session = "s1"
        backend.registry.get_bound_agent.return_value = None
        monkeypatch.setattr("sapguimcp.tools.session_tools.get_backend", AsyncMock(return_value=backend))
        monkeypatch.setattr(type(backend), "list_sessions", AsyncMock(return_value=[SessionInfo(session_id="s1")]))
        result = await sap_session_list_impl()
        assert result.success
        assert result.com_engine is not None
        assert result.com_engine["busy"] is True
        assert result.sessions[0].session_id == "s1"

    @pytest.mark.anyio
    async def test_hint_absent_when_idle(self, monkeypatch):
        backend = _backend_with_engine({"busy": False, "busy_since_s": None})
        monkeypatch.setattr("sapguimcp.tools.session_tools.get_backend", AsyncMock(return_value=backend))
        monkeypatch.setattr(type(backend), "list_sessions", AsyncMock(return_value=[SessionInfo(session_id="s1")]))
        result = await sap_session_list_impl()
        assert result.com_engine is None


class TestSessionListWhileEngineBlocked:
    """Regression (Copilot review of #934): the hint must come back WHILE the
    engine is still blocked, and the listing must not queue behind the block."""

    @pytest.mark.anyio
    async def test_returns_while_worker_blocked(self, monkeypatch):
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._mutation_lock = asyncio.Lock()
        backend.registry = MagicMock()
        backend.registry.list_sessions.return_value = ["s1"]
        backend.registry.primary_session = "s1"
        backend.registry.get_bound_agent.return_value = None

        release = threading.Event()
        com_calls: list[str] = []

        class _BusyCom:
            """ComThread stand-in: engine_state is instant, everything else queues."""

            async def engine_state(self):
                return {"busy": True, "busy_since_s": 30.0, "connection": "/app/con[1]", "queue_depth": 1}

            async def run(self, fn):
                com_calls.append(getattr(fn, "__name__", repr(fn)))
                await asyncio.get_running_loop().run_in_executor(None, release.wait, 10)
                return fn()

        backend.com = _BusyCom()

        async def fake_get_backend(*_args, **_kwargs):
            return backend

        monkeypatch.setattr("sapguimcp.tools.session_tools.get_backend", fake_get_backend)
        result = await sap_session_list_impl()
        assert result.success
        assert result.com_engine is not None, "hint must be present while the worker is still blocked"
        assert result.com_engine["busy_since_s"] == 30.0
        # The fast path made NO COM call — the queued listing would only run
        # after the blocking call finished.
        assert com_calls == [], "busy path must not queue COM work"
        assert [s.session_id for s in result.sessions] == ["s1"]
        assert result.sessions[0].tcode is None, "registry-only listing has no live tcode"
        release.set()
