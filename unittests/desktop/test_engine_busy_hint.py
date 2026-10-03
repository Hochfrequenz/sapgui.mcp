"""Issue #905: sap_session_list surfaces a long-running COM engine call."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend


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
        from sapguimcp.models.sap_results import SessionInfo
        from sapguimcp.tools.session_tools import sap_session_list_impl

        backend = _backend_with_engine({"busy": True, "busy_since_s": 30.0, "connection": "/app/con[1]"})
        monkeypatch.setattr("sapguimcp.tools.session_tools.get_backend", AsyncMock(return_value=backend))
        monkeypatch.setattr(type(backend), "list_sessions", AsyncMock(return_value=[SessionInfo(session_id="s1")]))
        result = await sap_session_list_impl()
        assert result.success
        assert result.com_engine is not None and result.com_engine["busy"] is True
        assert result.sessions[0].session_id == "s1"

    @pytest.mark.anyio
    async def test_hint_absent_when_idle(self, monkeypatch):
        from sapguimcp.models.sap_results import SessionInfo
        from sapguimcp.tools.session_tools import sap_session_list_impl

        backend = _backend_with_engine({"busy": False, "busy_since_s": None})
        monkeypatch.setattr("sapguimcp.tools.session_tools.get_backend", AsyncMock(return_value=backend))
        monkeypatch.setattr(type(backend), "list_sessions", AsyncMock(return_value=[SessionInfo(session_id="s1")]))
        result = await sap_session_list_impl()
        assert result.com_engine is None
