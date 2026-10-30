"""Shared fixtures for desktop backend tests."""

from __future__ import annotations

import faulthandler
import os
import re
from typing import TYPE_CHECKING, AsyncIterator, Collection, Sequence
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
# Non-destructive teardown helpers (#1009)
# ---------------------------------------------------------------------------


def connections_to_close(
    before_guids: Collection[str] | None,
    current: Sequence[frozenset[str] | None],
    owned_indexes: Collection[int] = (),
) -> list[int]:
    """Decide which SAP GUI connections the fixture teardown may close. FAILS CLOSED.

    ``current`` holds, per connection in ``/app/con[N]`` order, the set of ``SystemSessionId`` GUIDs of all
    its sessions, or ``None`` if that set could not be read completely (see ``read_connection_guids``).
    ``before_guids`` is every GUID seen before the fixture logged in, or ``None`` if that snapshot is not
    trustworthy. Returns indexes into ``current``, highest first so closing one cannot renumber the next.

    A connection is closable only if (a) it is in ``owned_indexes`` (it hosts a registry session), or (b)
    its GUID set is non-empty, fully readable and disjoint from ``before_guids``. Anything uncertain is
    left open. Identity is the GUID set, not the positional ``con[N]`` id, which is renumbered when a lower
    connection closes.

    TODO(#1009 PR 1): once session origins exist, restrict ``owned`` to registry sessions with origin
    "opened"; attached sessions live in the user's own connections and must never make them closable.
    """
    to_close: set[int] = {i for i in owned_indexes if 0 <= i < len(current)}
    if before_guids is not None:
        before = set(before_guids)
        for idx, guids in enumerate(current):
            if guids and guids.isdisjoint(before):
                to_close.add(idx)
    return sorted(to_close, reverse=True)


def connection_index_from_session_id(session_id: str) -> int | None:
    """Extract N from ``/app/con[N]/ses[M]`` (or ``/app/con[N]``); ``None`` if it does not match."""
    match = re.match(r"^/app/con\[(\d+)\]", session_id)
    return int(match.group(1)) if match else None


def read_connection_guids(conn) -> frozenset[str] | None:  # type: ignore[no-untyped-def]
    """All ``SystemSessionId`` GUIDs of a connection's sessions, or ``None`` if not fully readable.

    ``None`` on zero sessions, any COM error (busy, popup, disconnected) or an empty GUID: the caller must
    then treat the connection as not closable.
    """
    try:
        count = conn.Children.Count
        if count <= 0:
            return None
        guids: set[str] = set()
        for j in range(count):
            guid = str(conn.Children(j).Info.SystemSessionId or "")
            if not guid:
                return None
            guids.add(guid)
        return frozenset(guids)
    except Exception:  # pylint: disable=broad-except
        return None


def snapshot_connection_guids(app) -> list[frozenset[str] | None]:  # type: ignore[no-untyped-def]
    """GUID set per connection, in ``/app/con[N]`` order. Must run on the COM thread."""
    conns = app.com.Children
    return [read_connection_guids(conns(i)) for i in range(conns.Count)]


def snapshot_before_guids(app) -> frozenset[str] | None:  # type: ignore[no-untyped-def]
    """Union of all GUIDs present before setup, or ``None`` if any connection or the read itself failed.

    A pre-existing connection we cannot read now might become readable at teardown and then look new, so
    one unreadable connection makes the whole snapshot untrustworthy (teardown then closes owned only).
    """
    try:
        snap = snapshot_connection_guids(app)
    except Exception:  # pylint: disable=broad-except
        return None
    if any(g is None for g in snap):
        return None
    return frozenset(guid for g in snap if g for guid in g)


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
    # Record the GUIDs of connections that already exist (e.g. the user's own SAP GUI windows) so teardown
    # leaves them alone. SAP GUI not running means nothing pre-existing; any other failure means "unknown"
    # (None), which makes teardown close owned connections only.
    try:
        app_before = await com.run(lambda: SapGui.connect())
    except Exception:  # pylint: disable=broad-except
        before_guids: frozenset[str] | None = frozenset()
    else:
        before_guids = await com.run(lambda: snapshot_before_guids(app_before))
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
    # Identity is the GUID set (see connections_to_close), not the positional con[N] id; additionally every
    # connection hosting a registry session is treated as ours.
    try:
        app = await com.run(lambda: SapGui.connect())
        current = await com.run(lambda: snapshot_connection_guids(app))
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
        for i in connections_to_close(before_guids, current, owned):
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
