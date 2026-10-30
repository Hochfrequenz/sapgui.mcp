"""Shared fixtures for desktop backend tests."""

from __future__ import annotations

import faulthandler
import os
from typing import TYPE_CHECKING, AsyncIterator
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv
from sapsucker import SapGui

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._com_thread import ComThread
from sapguimcp.models.config import get_settings
from sapguimcp.tools.abapgit_tools import _abapgit_list_repos
from unittests.conftest import has_sap_desktop_creds

if TYPE_CHECKING:
    from sapguimcp.models.abapgit_models import AbapGitRepoInfo

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


# Successful, non-empty abapGit repo lists, cached to spare repeated SAP round trips.
# Assumes one SAP system per pytest process.
_REPO_LIST_CACHE: list[AbapGitRepoInfo] = []


def repo_registered(repos: list[AbapGitRepoInfo], name: str) -> bool:
    """Return whether ``name`` is among ``repos``. Exact match (abapGit names are upper-case)."""
    return any(r.name == name for r in repos)


async def require_repo_registered(backend, name: str) -> None:  # type: ignore[no-untyped-def]
    """Skip the calling test if abapGit repo ``name`` is not registered on the SAP system.

    Skips only if listing succeeded, returned at least one repo, and ``name`` is not among them.
    A failed or empty listing (possibly a parser regression) never skips, so the test fails visibly.
    """
    repos = _REPO_LIST_CACHE
    if not repos:
        result = await _abapgit_list_repos(backend)
        await go_home(backend)
        if not result.success or not result.repos:
            return
        _REPO_LIST_CACHE[:] = result.repos
        repos = _REPO_LIST_CACHE
    if not repo_registered(repos, name):
        pytest.skip(f"abapGit repo {name} is not registered on this SAP system (see docs/SAP_TEST_PREREQUISITES.md)")


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
# Non-destructive teardown helper (#1009)
# ---------------------------------------------------------------------------


def close_owned_connections(sessions) -> int:  # type: ignore[no-untyped-def]
    """Close the SAP GUI connection of every given session, once per connection. Must run on the COM thread.

    STRICT FAIL-CLOSED: the fixture closes only connections that host a session from its own registry, never
    anything it merely finds in SAP GUI -- connections the user opens while the tests run are
    indistinguishable from the fixture's by any snapshot. Trade-off: a fixture connection whose session was
    never registered or was already unregistered (e.g. after a failed login) can leak; that is accepted.
    Connections are resolved to COM parent objects first and closed afterwards, so the positional
    ``con[N]`` renumbering that closing causes cannot make us close the wrong one. Errors are swallowed
    (best effort). Returns the number of connections a close was attempted on.

    TODO(#1009 PR 1): once session origins exist, pass only sessions with origin "opened"; attached
    sessions live in the user's own connections.
    """
    parents: list[object] = []
    seen: set[str] = set()
    for ses in sessions:
        conn_id = None
        try:
            conn = ses.com.Parent
            conn_id = str(conn.Id)
        except Exception:  # pylint: disable=broad-except
            pass
        if conn_id is not None and conn_id not in seen:
            seen.add(conn_id)
            parents.append(conn)
    attempted = 0
    for conn in parents:
        attempted += 1
        try:
            conn.CloseConnection()  # type: ignore[attr-defined]
        except Exception:  # pylint: disable=broad-except
            pass
    return attempted


# ---------------------------------------------------------------------------
# Integration backend fixture (auto-discovered by pytest)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def backend() -> AsyncIterator:  # type: ignore[type-arg]
    """Provide a logged-in DesktopBackend, shared across all tests in a module.

    Teardown closes only the SAP GUI connections hosting a session of this fixture's registry; the user's
    own windows are left open (#1009).

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
    # Teardown: close only connections hosting a session this fixture's registry holds (see
    # close_owned_connections); the user's own windows are never touched.
    try:
        owned_sessions = [b.registry.get_session(sid) for sid in list(b.registry.list_sessions())]
        await com.run(lambda: close_owned_connections(owned_sessions))
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
