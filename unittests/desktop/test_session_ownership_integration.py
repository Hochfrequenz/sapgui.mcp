"""Live tests for session ownership and the close paths (issue #1009, PR 1). Needs SAP GUI."""

import contextlib
import sys
from typing import Any

import pytest

from sapguimcp.models.config import get_sap_config
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = [skip_no_sap, pytest.mark.skipif(sys.platform != "win32", reason="Windows only")]


async def _login_second(backend: Any) -> str:
    """A second ``login`` opens a NEW connection (and session) next to s1."""
    system = get_sap_config().get_default()
    result = await backend.login(
        "x",
        system.user,
        system.password.get_secret_value(),
        system.client,
        system.language,
        connection_name=system.connection_name,
    )
    assert result.success, result.error
    sid = result.session_id
    assert sid is not None
    assert sid != "s1"
    return sid


async def _ids(backend: Any, sid: str) -> tuple[str, str]:
    """(session com Id, connection com Id) of a registered session."""
    ses = backend.registry.get_session(sid)
    return await backend.com.run(lambda: (str(ses.com.Id), str(ses.com.Parent.Id)))


async def _alive(backend: Any, ses: Any) -> bool:
    try:
        await backend.com.run(lambda: str(ses.com.FindById("wnd[0]").Type), max_retries=0)
    except Exception:  # pylint: disable=broad-exception-caught
        return False
    return True


async def _force_close_connection(backend: Any, ses: Any) -> None:
    """Test cleanup for a session the registry no longer holds."""

    def _close() -> None:
        ses.com.Parent.CloseConnection()

    with contextlib.suppress(Exception):
        await backend.com.run(_close)


@pytest.mark.anyio
async def test_close_second_connection_session_closes_the_right_window(backend: Any) -> None:
    """Regression: CloseSession used the PRIMARY's connection, not the target's own."""
    s2 = await _login_second(backend)
    s1_ses = backend.registry.get_session("s1")
    s2_ses = backend.registry.get_session(s2)
    _, con1 = await _ids(backend, "s1")
    _, con2 = await _ids(backend, s2)
    assert con1 != con2, "the two sessions must live on different connections"

    closed = await backend.close_session(s2)

    assert closed is True
    assert not backend.registry.has_session(s2)
    assert await _alive(backend, s1_ses), "s1 must stay open"
    assert not await _alive(backend, s2_ses), "s2's window must be gone"
    await go_home(backend)


@pytest.mark.anyio
async def test_detach_leaves_the_window_open(backend: Any) -> None:
    s2 = await _login_second(backend)
    s2_ses = backend.registry.get_session(s2)
    try:
        await backend.detach_session(s2)

        assert not backend.registry.has_session(s2)
        assert await _alive(backend, s2_ses), "detach must not close the SAP window"
    finally:
        await _force_close_connection(backend, s2_ses)
    await go_home(backend)


@pytest.mark.anyio
async def test_attached_session_is_never_closed(backend: Any) -> None:
    s2 = await _login_second(backend)
    s2_ses = backend.registry.get_session(s2)
    backend.registry.unregister(s2)
    attached = backend.registry.register(s2_ses, origin="attached")
    try:
        assert await backend.close_session(attached) is False
        report = await backend.reset_to_primary()

        assert attached in report["skipped_attached"]
        assert attached not in report["closed"]
        assert backend.registry.has_session(attached)
        assert await _alive(backend, s2_ses), "an attached window must survive close and reset"
        infos = {i.session_id: i.origin for i in await backend.list_sessions()}
        assert infos[attached] == "attached"
    finally:
        await backend.detach_session(attached)
        await _force_close_connection(backend, s2_ses)
    await go_home(backend)
