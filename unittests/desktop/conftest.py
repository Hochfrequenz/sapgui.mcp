"""Shared fixtures for desktop backend tests."""

from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv

from unittests.conftest import is_sap_integration_test_machine

# ---------------------------------------------------------------------------
# Skip markers – importable by per-transaction test modules
# ---------------------------------------------------------------------------

skip_not_sap = pytest.mark.skipif(not is_sap_integration_test_machine(), reason="Not SAP machine")
skip_no_creds: pytest.MarkDecorator


def _creds_ok() -> bool:
    try:
        load_dotenv()
        from sapwebguimcp.models.config import get_settings

        s = get_settings()
        return bool(s.sap_connection_name and s.sap_user and s.sap_password and s.sap_mandant)
    except Exception:
        return False


skip_no_creds = pytest.mark.skipif(not _creds_ok(), reason="No SAP credentials")


# ---------------------------------------------------------------------------
# Shared async helpers
# ---------------------------------------------------------------------------


async def go_home(backend) -> None:  # type: ignore[no-untyped-def]
    """Press F3 multiple times to return to Easy Access screen."""
    for _ in range(5):
        await backend.press_key("F3")


# ---------------------------------------------------------------------------
# Integration backend fixture (auto-discovered by pytest)
# ---------------------------------------------------------------------------


@pytest.fixture
async def backend() -> AsyncIterator:  # type: ignore[type-arg]
    """Provide a logged-in DesktopBackend. Closes ALL connections on teardown."""
    import os

    load_dotenv()
    from sapwebguimcp.backend.desktop import DesktopBackend
    from sapwebguimcp.backend.desktop._com_thread import ComThread

    com = ComThread()
    b = DesktopBackend(com_thread=com)
    r = await b.login(
        "x",
        os.environ["SAP_USER"],
        os.environ["SAP_PASSWORD"],
        os.environ["SAP_MANDANT"],
        os.environ.get("SAP_LANGUAGE", "DE"),
    )
    assert r.success, f"Login failed: {r.error}"
    yield b
    # Teardown: close ALL connections -- tools may have opened additional ones
    import faulthandler

    try:
        from sapwebguimcp.sapgui import SapGui

        app = await com.run(lambda: SapGui.connect())
        raw_conns = await com.run(lambda: app.com.Children)
        count = await com.run(lambda: raw_conns.Count)
        for i in range(count - 1, -1, -1):
            try:
                await com.run(lambda i=i: raw_conns(i).CloseConnection())
            except Exception:
                pass
    except Exception:
        pass
    b._session = None
    faulthandler.disable()
    com.shutdown()
    faulthandler.enable()


# ---------------------------------------------------------------------------
# Mock helpers (for unit tests)
# ---------------------------------------------------------------------------


def make_mock_session(
    *,
    system_name: str = "S4U",
    client: str = "100",
    user: str = "TESTUSER",
    language: str = "EN",
    transaction: str = "SESSION_MANAGER",
    program: str = "SAPLSMTR_NAVIGATION",
    screen_number: int = 100,
    busy: bool = False,
) -> MagicMock:
    """Create a mock GuiSession with realistic info properties."""
    session = MagicMock()
    session.id = "/app/con[0]/ses[0]"
    session.info.system_name = system_name
    session.info.client = client
    session.info.user = user
    session.info.language = language
    session.info.transaction = transaction
    session.info.program = program
    session.info.screen_number = screen_number
    session.info.application_server = "sapserver01"
    session.info.response_time = 42
    session.info.round_trips = 3
    session.busy = busy

    # Main window mock
    wnd = MagicMock()
    wnd.text = "SAP Easy Access"

    # Statusbar mock
    sbar = MagicMock()
    sbar.text = ""
    sbar.message_type = ""

    # OkCode field mock
    okcd = MagicMock()
    okcd.text = ""

    # find_by_id routing
    def find_by_id(element_id: str, raise_error: bool = True) -> MagicMock | None:
        routes = {
            "wnd[0]": wnd,
            "wnd[0]/sbar": sbar,
            "wnd[0]/tbar[0]/okcd": okcd,
        }
        result = routes.get(element_id)
        if result is None and raise_error:
            raise Exception(f"Element not found: {element_id}")
        return result

    session.find_by_id = find_by_id
    return session


@pytest.fixture
def mock_session():
    """Provide a factory for mock GuiSession objects."""
    return make_mock_session
