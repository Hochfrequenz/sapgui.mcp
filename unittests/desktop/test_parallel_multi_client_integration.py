"""Live test: two parallel logins to different clients over the same SAP Logon entry coexist (#674, #671).

The second client comes from systems.json: any entry that shares the default system's ``connection_name`` and has a
different client. Without one, the test skips.
"""

import sys
from typing import Any

import pytest
from sap_mcp_config.models import SAPSystem

from sapguimcp.models.config import get_sap_config
from unittests.desktop.conftest import close_owned_connections, skip_no_sap

pytestmark = [skip_no_sap, pytest.mark.skipif(sys.platform != "win32", reason="Windows only")]


def _second_client() -> SAPSystem | None:
    cfg = get_sap_config()
    default = cfg.get_default()
    return next(
        (
            s
            for s in cfg.systems.values()
            if s.connection_name == default.connection_name and s.client != default.client
        ),
        None,
    )


@pytest.mark.anyio
async def test_two_clients_on_one_logon_entry_coexist(backend: Any) -> None:
    other = _second_client()
    if other is None:
        pytest.skip("systems.json has no second client for the default system's SAP Logon entry")
    # Expected values come from the live session, not the config: the fixture logged on before per-test config resets.
    [first] = await backend.list_sessions()
    first_client = first.client
    owned = [backend.registry.get_session("s1")]  # closed in finally even if a regression unregisters it

    try:
        result = await backend.login(
            "x",
            other.user,
            other.password.get_secret_value(),
            other.client,
            other.language,
            connection_name=other.connection_name,
        )
        assert result.success, result.error
        owned.append(backend.registry.get_session(result.session_id))
        assert result.session_id == "s2"

        # The first login survives the second (the regression of #671 dropped it).
        sessions = {s.session_id: s for s in await backend.list_sessions()}
        assert set(sessions) == {"s1", "s2"}
        assert sessions["s1"].client == first_client
        assert sessions["s2"].client == other.client != first_client
        assert (sessions["s1"].is_primary, sessions["s2"].is_primary) == (True, False)
        for sid in ("s1", "s2"):
            assert (await backend.get_session_status(session_id=sid)).status == "active"

        # Closing the primary s1 leaves s2 alive, and s2 becomes the primary.
        assert await backend.close_session("s1")
        remaining = await backend.list_sessions()
        assert [(r.session_id, r.is_primary) for r in remaining] == [("s2", True)]
        assert (await backend.get_session_status(session_id="s2")).status == "active"

        assert await backend.close_session("s2")
        assert backend.registry.list_sessions() == []
        assert await backend.list_sessions() == []
    finally:
        await backend.com.run(lambda: close_owned_connections(owned))
