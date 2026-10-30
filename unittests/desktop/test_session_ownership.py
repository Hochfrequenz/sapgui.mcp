"""Unit tests for session ownership tracking (issue #1009, PR 1)."""

import ast
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry
from sapguimcp.backend.manager import BackendManager


class FakeCom:
    """COM thread double: runs lambdas inline and records shutdown."""

    def __init__(self) -> None:
        self.run_calls = 0
        self.shutdown_called = False
        self.unwatch_connection = MagicMock()
        self.watch_connection = MagicMock()

    async def run(self, fn: Callable[[], Any], **_: Any) -> Any:
        """Run *fn* inline, counting the call."""
        self.run_calls += 1
        return fn()

    def shutdown(self) -> None:
        """Record that the COM thread was shut down."""
        self.shutdown_called = True


def _session(connection: MagicMock, com_id: str) -> MagicMock:
    ses = MagicMock()
    ses.com.Id = com_id
    ses.com.Parent = connection
    return ses


def _backend() -> tuple[DesktopBackend, FakeCom]:
    com = FakeCom()
    return DesktopBackend(com_thread=com), com  # type: ignore[arg-type]


# ---- registry ----


def test_origin_defaults_to_opened() -> None:
    reg = DesktopSessionRegistry()
    sid = reg.register(MagicMock())
    assert reg.origin_of(sid) == "opened"
    assert reg.is_attached(sid) is False
    assert reg.origin_of("s99") is None


def test_origin_attached_and_cleared_everywhere() -> None:
    reg = DesktopSessionRegistry()
    a, b, c = (reg.register(MagicMock(), origin="attached") for _ in range(3))
    assert reg.is_attached(a)
    reg.unregister(a)
    assert reg.origin_of(a) is None
    reg.prune([b])
    assert reg.origin_of(b) is None
    reg.clear()
    assert reg.origin_of(c) is None


def test_ids_never_reused_after_unregister() -> None:
    reg = DesktopSessionRegistry()
    first = reg.register(MagicMock(), origin="attached")
    reg.unregister(first)
    second = reg.register(MagicMock())
    assert second != first
    assert reg.origin_of(second) == "opened"


# ---- backend close paths ----


@pytest.mark.anyio
async def test_close_attached_is_refused_without_com_call() -> None:
    backend, com = _backend()
    conn = MagicMock()
    sid = backend.registry.register(_session(conn, "/app/con[0]/ses[0]"), origin="attached")

    assert await backend.close_session(sid) is False

    conn.CloseSession.assert_not_called()
    assert com.run_calls == 0
    assert backend.registry.has_session(sid)


@pytest.mark.anyio
async def test_close_opened_session_uses_its_own_connection() -> None:
    backend, _ = _backend()
    conn_a, conn_b = MagicMock(), MagicMock()
    backend.registry.register(_session(conn_a, "/app/con[0]/ses[0]"))
    s2 = backend.registry.register(_session(conn_b, "/app/con[1]/ses[0]"))

    assert await backend.close_session(s2) is True

    conn_b.CloseSession.assert_called_once_with("/app/con[1]/ses[0]")
    conn_a.CloseSession.assert_not_called()
    assert not backend.registry.has_session(s2)


@pytest.mark.anyio
async def test_reset_to_primary_skips_and_reports_attached() -> None:
    backend, _ = _backend()
    conn = MagicMock()
    backend.registry.register(_session(conn, "/app/con[0]/ses[0]"))  # s1 primary
    s2 = backend.registry.register(_session(conn, "/app/con[0]/ses[1]"))
    s3 = backend.registry.register(_session(conn, "/app/con[0]/ses[2]"), origin="attached")

    report = await backend.reset_to_primary()

    assert report["closed"] == [s2]
    assert report["skipped_attached"] == [s3]
    assert sorted(report["remaining"]) == ["s1", s3]
    conn.CloseSession.assert_called_once_with("/app/con[0]/ses[1]")


@pytest.mark.anyio
async def test_detach_unregisters_unwatches_unbinds_with_zero_com_calls() -> None:
    backend, com = _backend()
    conn = MagicMock()
    ses = _session(conn, "/app/con[0]/ses[0]")
    sid = backend.registry.register(ses, origin="attached")
    backend.registry.bind(sid, "agent-1")
    backend._record_connection(ses, "/app/con[0]")  # pylint: disable=protected-access
    runs_before = com.run_calls

    prev = await backend.detach_session(sid)

    assert prev == "agent-1"
    assert not backend.registry.has_session(sid)
    assert backend.registry.get_bound_agent(sid) is None
    com.unwatch_connection.assert_called_once_with("/app/con[0]")
    assert com.run_calls == runs_before
    conn.CloseSession.assert_not_called()


@pytest.mark.anyio
async def test_detach_unknown_session_raises() -> None:
    backend, _ = _backend()
    with pytest.raises(ValueError, match="not found"):
        await backend.detach_session("s9")


@pytest.mark.anyio
async def test_reconcile_still_prunes_dead_attached_session() -> None:
    backend, _ = _backend()
    ses = _session(MagicMock(), "/app/con[0]/ses[0]")
    ses.com.FindById.side_effect = OSError("disconnected")
    sid = backend.registry.register(ses, origin="attached")

    report = await backend.reconcile()

    assert sid in report["removed"]
    assert backend.registry.origin_of(sid) is None


@pytest.mark.anyio
async def test_list_sessions_reports_origin() -> None:
    backend, _ = _backend()
    conn = MagicMock()
    backend.registry.register(_session(conn, "/app/con[0]/ses[0]"))
    backend.registry.register(_session(conn, "/app/con[0]/ses[1]"), origin="attached")

    infos = await backend.list_sessions()

    assert [i.origin for i in infos] == ["opened", "attached"]
    assert [i.origin for i in await backend.list_sessions_fast()] == ["opened", "attached"]


@pytest.mark.anyio
async def test_backend_manager_close_never_closes_sap_sessions() -> None:
    backend, com = _backend()
    manager = BackendManager(backend_type="desktop")
    manager._com_thread = com  # type: ignore[assignment]  # pylint: disable=protected-access
    conn = MagicMock()
    backend.registry.register(_session(conn, "/app/con[0]/ses[0]"), origin="attached")
    manager._backends["desktop"] = backend  # type: ignore[assignment]  # pylint: disable=protected-access

    await manager.close()

    assert com.shutdown_called
    conn.CloseSession.assert_not_called()
    conn.CloseConnection.assert_not_called()
    assert com.run_calls == 0


# ---- static guard ----


def test_only_the_ownership_checked_site_closes_sap_sessions() -> None:
    src = Path(__file__).resolve().parents[2] / "src"
    pattern = re.compile(
        r"\.(CloseSession|CloseConnection|close_connections_named|cleanup_ghost_connections)\(|\blogoff\("
    )
    hits = []
    for path in src.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if pattern.search(line) and not line.lstrip().startswith("#"):
                hits.append((path.relative_to(src).as_posix(), line.strip()))
    assert [h[0] for h in hits] == ["sapguimcp/backend/desktop/__init__.py"], (
        f"New SAP close call site(s): {hits}. Add an ownership check (registry.is_attached) and allow-list it here."
    )
    tree = ast.parse((src / "sapguimcp/backend/desktop/__init__.py").read_text(encoding="utf-8"))
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_close_session_locked")
    close_line = min(
        n.lineno
        for n in ast.walk(func)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "CloseSession"
    )
    guards = [
        n.lineno
        for n in ast.walk(func)
        if isinstance(n, ast.If)
        and any(isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "is_attached" for c in ast.walk(n.test))
        and any(isinstance(b, ast.Return) for b in n.body)
    ]
    assert guards, "_close_session_locked needs an early-return is_attached guard"
    assert min(guards) < close_line, "the is_attached guard must precede the CloseSession call"
