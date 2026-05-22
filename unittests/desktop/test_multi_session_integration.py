"""Integration tests for desktop multi-session support."""

import asyncio
import logging
import sys

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_open_second_session(backend):
    """Open a second SAP session and verify it gets a new ID."""
    sid, count, title = await backend.open_new_session("SE00")
    assert sid is not None and sid != "s1", f"Expected new session ID, got '{sid}'"
    assert count >= 2
    assert backend.registry.has_session("s1")
    assert backend.registry.has_session(sid)
    # Cleanup
    await backend.close_session(sid)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_parallel_navigation(backend):
    """Two sessions navigate to different transactions concurrently."""
    from sapguimcp.backend.desktop import _current_session_id

    sid2, _, _ = await backend.open_new_session("SE00")
    assert sid2 is not None and sid2 != "s1"

    async def navigate_s1():
        _current_session_id.set("s1")
        await backend.enter_transaction("SE37")
        return await backend.get_screen_info()

    async def navigate_s2():
        _current_session_id.set(sid2)
        await backend.enter_transaction("SE16")
        return await backend.get_screen_info()

    info1, info2 = await asyncio.gather(navigate_s1(), navigate_s2())

    assert info1.transaction == "SE37", f"s1 should be on SE37, got {info1.transaction}"
    assert info2.transaction == "SE16", f"{sid2} should be on SE16, got {info2.transaction}"

    # Cleanup
    _current_session_id.set(sid2)
    await backend.enter_transaction("/n")
    await backend.close_session(sid2)
    _current_session_id.set("s1")
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_close_session(backend):
    """Close second session and verify s1 still works."""
    sid2, _, _ = await backend.open_new_session("SE00")
    assert sid2 is not None and sid2 != "s1"
    closed = await backend.close_session(sid2)
    assert closed
    assert not backend.registry.has_session(sid2)
    assert backend.registry.has_session("s1")
    info = await backend.get_screen_info()
    assert info.success
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_bind_and_check(backend, caplog):
    """Bind s1 to an agent and verify check_binding warns on mismatch."""
    backend.registry.bind("s1", "agent_a")
    # Matching agent — no warning
    with caplog.at_level(logging.WARNING):
        backend.registry.check_binding("s1", "agent_a", "test_tool")
    assert "Cross-agent" not in caplog.text
    caplog.clear()
    # Mismatching agent — should warn
    with caplog.at_level(logging.WARNING):
        backend.registry.check_binding("s1", "agent_b", "test_tool")
    assert "Cross-agent" in caplog.text
    backend.registry.release("s1")
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_list_sessions(backend):
    """list_sessions returns all registered sessions."""
    sid2, _, _ = await backend.open_new_session("SE00")
    assert sid2 is not None and sid2 != "s1"
    sessions = await backend.list_sessions()
    session_ids = [s.session_id for s in sessions]
    assert "s1" in session_ids
    assert sid2 in session_ids
    # Cleanup
    await backend.close_session(sid2)
    await go_home(backend)
