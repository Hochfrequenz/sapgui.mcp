"""Unit tests for ContextVar-based session routing in DesktopBackend."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from sapguimcp.backend.desktop import _current_session_id
from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry


def _make_mock_session(name: str = "s") -> MagicMock:
    """Create a mock GuiSession with a working COM info probe."""
    session = MagicMock()
    session.com.Info.Transaction = "SE00"
    session.id = f"/app/con[0]/ses[{name}]"
    session._name = name  # for test identification
    return session


class TestContextVarRouting:
    def test_default_returns_s1(self) -> None:
        """With no ContextVar set, require_session returns s1."""
        from sapguimcp.backend.desktop import DesktopBackend

        b = DesktopBackend.__new__(DesktopBackend)
        b.registry = DesktopSessionRegistry()
        b.com = MagicMock()
        mock_s1 = _make_mock_session("1")
        b.registry.register(mock_s1)

        token = _current_session_id.set(None)
        try:
            result = b.require_session()
            assert result is mock_s1
        finally:
            _current_session_id.reset(token)

    def test_contextvar_routes_to_s2(self) -> None:
        """With ContextVar set to 's2', require_session returns s2."""
        from sapguimcp.backend.desktop import DesktopBackend

        b = DesktopBackend.__new__(DesktopBackend)
        b.registry = DesktopSessionRegistry()
        b.com = MagicMock()
        b.registry.register(_make_mock_session("1"))
        mock_s2 = _make_mock_session("2")
        b.registry.register(mock_s2)

        token = _current_session_id.set("s2")
        try:
            result = b.require_session()
            assert result is mock_s2
        finally:
            _current_session_id.reset(token)

    def test_contextvar_unknown_session_raises(self) -> None:
        """ContextVar pointing to nonexistent session raises ValueError."""
        from sapguimcp.backend.desktop import DesktopBackend

        b = DesktopBackend.__new__(DesktopBackend)
        b.registry = DesktopSessionRegistry()
        b.com = MagicMock()
        b.registry.register(_make_mock_session("1"))

        token = _current_session_id.set("s99")
        try:
            with pytest.raises(ValueError, match="not found"):
                b.require_session()
        finally:
            _current_session_id.reset(token)

    @pytest.mark.anyio
    async def test_contextvar_isolation_across_tasks(self) -> None:
        """Parallel async tasks with different ContextVar values get correct sessions."""
        from sapguimcp.backend.desktop import DesktopBackend

        b = DesktopBackend.__new__(DesktopBackend)
        b.registry = DesktopSessionRegistry()
        b.com = MagicMock()
        mock_s1 = _make_mock_session("1")
        mock_s2 = _make_mock_session("2")
        b.registry.register(mock_s1)
        b.registry.register(mock_s2)

        results: dict[str, MagicMock] = {}

        async def task_s1() -> None:
            _current_session_id.set("s1")
            await asyncio.sleep(0.01)  # yield to let s2 run
            results["s1"] = b.require_session()

        async def task_s2() -> None:
            _current_session_id.set("s2")
            await asyncio.sleep(0.01)
            results["s2"] = b.require_session()

        await asyncio.gather(task_s1(), task_s2())

        assert results["s1"] is mock_s1
        assert results["s2"] is mock_s2
