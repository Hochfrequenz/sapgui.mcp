"""Shared fixtures for desktop backend tests."""

from __future__ import annotations

import faulthandler
import os
import re
from collections import Counter
from typing import AsyncIterator, Collection, Sequence
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from sapsucker import SapGui

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.models.config import get_settings
from unittests.conftest import has_sap_desktop_creds

# ---------------------------------------------------------------------------
# Test object names — centralized so they can be changed in one place.
# These objects must exist on the SAP test system.
# See docs/SAP_TEST_PREREQUISITES.md for setup instructions.
# abapGit repo: https://github.com/Hochfrequenz/Z_MCP_TEST_EDITABLE_WB_OBJECTS
# ---------------------------------------------------------------------------

TEST_REPORT = "ZTEST_MCP_EDIT"
TEST_CLASS = "ZCL_TEST_MCP_EDIT"
TEST_METHOD = "DO_SOMETHING"
TEST_TABLE = "TSTC"  # Standard SAP table (exists on all systems)

# ---------------------------------------------------------------------------
# Skip marker – importable by per-transaction test modules.
# Skips when SAP desktop credentials are not configured in the environment.
# ---------------------------------------------------------------------------

skip_no_sap = pytest.mark.skipif(not has_sap_desktop_creds(), reason="No SAP desktop credentials")


# ---------------------------------------------------------------------------
# Shared async helpers
# ---------------------------------------------------------------------------


async def go_home(backend) -> None:  # type: ignore[no-untyped-def]
    """Press F3 multiple times to return to Easy Access screen."""
    for _ in range(5):
        await backend.press_key("F3")


async def bp_teardown(backend) -> None:  # type: ignore[no-untyped-def]
    """Guaranteed post-BP cleanup (issue #756).

    Navigate back to Easy Access and then wait for the COM STA to drain
    (``com_call_retry`` storms on an unresponsive BDT screen can otherwise
    bleed into the next test module and fail it at its first COM call).

    Both steps are exception-safe: a teardown must never mask the original
    test failure, and a failed ``go_home`` must not skip the cool-down drain.
    """
    try:
        await go_home(backend)
    except Exception:  # pylint: disable=broad-except
        pass
    try:
        await backend.wait_for_ready()
    except Exception:  # pylint: disable=broad-except
        pass


def _reorder_bp_last(items) -> None:  # type: ignore[no-untyped-def]
    """Sort BP integration items to the end of ``items`` in place (#756).

    BP tests can time out for minutes under ``com_call_retry`` storms; running
    them last keeps a BP failure from poisoning the other desktop tool tests.
    Relative order within the BP group and within the rest is preserved.
    """
    bp = [it for it in items if "test_bp_integration.py" in it.nodeid]
    if not bp:
        return
    rest = [it for it in items if "test_bp_integration.py" not in it.nodeid]
    items[:] = rest + bp


def pytest_collection_modifyitems(items) -> None:  # type: ignore[no-untyped-def]
    """Ensure BP integration tests run after the other desktop tests (#756)."""
    _reorder_bp_last(items)


# ---------------------------------------------------------------------------
# Non-destructive teardown helpers (#1009)
# ---------------------------------------------------------------------------


def connections_to_close(
    before_keys: Sequence[str], current_keys: Sequence[str], owned_indexes: Collection[int] = ()
) -> list[int]:
    """Decide which SAP GUI connections the fixture teardown may close.

    ``before_keys`` are the identity keys of the connections that existed before the fixture logged in,
    ``current_keys`` those present at teardown (position = ``/app/con[N]`` index). Returns indexes into
    ``current_keys``, highest first so closing one cannot renumber the next.

    Identity is a *key*, not the positional ``con[N]`` id: ids are renumbered when a lower connection is
    closed (by the user, mid-run). Keys are matched as a multiset, so identical keys cannot make a
    pre-existing connection look new. ``owned_indexes`` are connections known to hold a session the fixture
    opened (registry); they are closed regardless of their key.
    """
    remaining = Counter(before_keys)
    to_close: list[int] = []
    for idx, key in enumerate(current_keys):
        if idx in owned_indexes:
            to_close.append(idx)
        elif remaining[key] > 0:
            remaining[key] -= 1  # pre-existing: leave it alone
        else:
            to_close.append(idx)
    return sorted(to_close, reverse=True)


def connection_index_from_session_id(session_id: str) -> int | None:
    """Extract N from ``/app/con[N]/ses[M]`` (or ``/app/con[N]``); ``None`` if it does not match."""
    match = re.match(r"^/app/con\[(\d+)\]", session_id)
    return int(match.group(1)) if match else None


def _connection_keys_sync(app) -> list[str]:  # type: ignore[no-untyped-def]
    """Identity key per connection, in ``/app/con[N]`` order. Must run on the COM thread.

    Key = SAP Logon description + SystemSessionId of the first session (a GUID unique per session, stable
    for its lifetime and unaffected by renumbering). A connection without a readable session falls back to
    the description alone.
    """
    conns = app.com.Children
    keys: list[str] = []
    for i in range(conns.Count):
        conn = conns(i)
        try:
            desc = str(conn.Description)
        except Exception:  # pylint: disable=broad-except
            desc = ""
        sess_key = ""
        try:
            if conn.Children.Count > 0:
                sess_key = str(conn.Children(0).Info.SystemSessionId)
        except Exception:  # pylint: disable=broad-except
            pass
        keys.append(f"{desc}|{sess_key}")
    return keys


# ---------------------------------------------------------------------------
# Integration backend fixture (auto-discovered by pytest)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def backend() -> AsyncIterator:  # type: ignore[type-arg]
    """Provide a logged-in DesktopBackend, shared across all tests in a module.

    Teardown closes only the SAP GUI connections opened during the module; connections that existed
    before login (the user's own windows) are left open (#1009).

    Module scope avoids repeated COM ``OpenConnection`` / ``CloseConnection``
    cycles that corrupt the process-wide COM subsystem after table scrolling
    operations (see #399).  Each test is expected to call ``go_home()`` at the
    end to return to the Easy Access screen.
    """
    load_dotenv()
    from sapguimcp.models.config import get_sap_config

    sap_cfg = get_sap_config()
    system = sap_cfg.get_default()
    com = ComThread()
    # Record the connections that already exist (e.g. the user's own SAP GUI windows) so teardown leaves them alone.
    try:
        app_before = await com.run(lambda: SapGui.connect())
        before_keys = await com.run(lambda: _connection_keys_sync(app_before))
    except Exception:  # pylint: disable=broad-except
        before_keys = None  # SAP GUI not running yet: nothing pre-existing
    b = DesktopBackend(com_thread=com)
    r = await b.login(
        "x",
        system.user,
        system.password.get_secret_value(),
        system.client,
        system.language,
        connection_name=system.connection_name,
    )
    assert r.success, f"Login failed: {r.error}"
    yield b
    # Teardown: close only connections the fixture (or tools it ran) opened -- never the user's own.
    # Identity is a key (see connections_to_close), not the positional con[N] id; additionally every
    # connection hosting a registry session is treated as ours.
    try:
        app = await com.run(lambda: SapGui.connect())
        current_keys = await com.run(lambda: _connection_keys_sync(app))
        owned: set[int] = set()
        for sid in list(b.registry.list_sessions()) if hasattr(b, "registry") else []:
            try:
                ses = b.registry.get_session(sid)
                idx = connection_index_from_session_id(await com.run(lambda ses=ses: ses.id))
                if idx is not None:
                    owned.add(idx)
            except Exception:  # pylint: disable=broad-except
                pass
        raw_conns = await com.run(lambda: app.com.Children)
        for i in connections_to_close(before_keys or [], current_keys, owned):
            try:
                await com.run(lambda i=i: raw_conns(i).CloseConnection())
            except Exception:  # pylint: disable=broad-except
                pass
    except Exception:  # pylint: disable=broad-except
        pass
    # Clear registry to avoid stale session references
    if hasattr(b, "registry"):
        for sid in list(b.registry.list_sessions()):
            b.registry.unregister(sid)
    faulthandler.disable()
    com.shutdown()
    faulthandler.enable()


# ---------------------------------------------------------------------------
# Mock helpers (for unit tests)
# ---------------------------------------------------------------------------


def make_mock_session(
    *,
    system_name: str = "XYZ",
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
