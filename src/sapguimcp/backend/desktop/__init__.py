"""Desktop backend — SAP GUI Scripting (COM) automation.

Bridges the async MCP protocol to synchronous COM calls via a dedicated
ComThread.
"""

# pylint: disable=broad-exception-caught,too-many-public-methods,too-many-lines

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

from sapsucker.login import login as _sapsucker_login

try:
    from sapsucker.components.grid import GuiGridView
except ImportError:
    GuiGridView = None  # type: ignore[misc,assignment]

from sapguimcp.backend.desktop._com_thread import ComThread, is_transient_busy_error
from sapguimcp.backend.desktop._landscape import _find_landscape_path, _parse_landscape_xml
from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry

#: Per-async-task session ID — set by BackendManager before each tool call.
#: MUST be read on the async side (in require_session), NEVER inside a ComThread lambda.
_current_session_id: ContextVar[str | None] = ContextVar("_current_session_id", default=None)
from sapguimcp.backend.desktop._element_finder import (
    _dump_flat_tree,
    _flatten,
    find_button_by_label,
    find_checkbox_by_label,
    find_combobox_by_label,
    find_field_by_label,
    find_radio_by_label,
    find_tab_by_label,
)
from sapguimcp.backend.desktop._key_mapping import key_to_vkey
from sapguimcp.backend.desktop.types import ComTreeSnapshot
from sapguimcp.models.alv_models import TableCellClickResult
from sapguimcp.models.base import CheckActivateResult, PopupButton, PopupInfo, PopupType
from sapguimcp.models.sap_results import (
    ButtonInfo,
    ClosePopupResult,
    DropdownFillResult,
    FieldFillError,
    FieldInfo,
    FillFormResult,
    FormField,
    FormFieldsResult,
    KeyboardResult,
    LoginResult,
    SapFieldType,
    ScreenInfo,
    ScreenText,
    SessionInfo,
    SessionStatus,
    StatusBarInfo,
    StatusBarType,
    TableData,
    TableRow,
    TransactionResult,
)

if TYPE_CHECKING:
    from sapsucker.components.session import GuiSession

logger = logging.getLogger(__name__)


def _unwrap_com(field: Any) -> Any:
    """Get the raw COM dispatch object from a sapsucker wrapper."""
    return getattr(field, "com", getattr(field, "_com", field))


def _set_field_value(raw_com: Any, value: str) -> None:
    """Set a field value, handling GuiComboBox dropdown fields automatically.

    For GuiComboBox: searches the Entries collection for a matching display
    value and sets the Key property. Accepts display text ("Herr"), key ("0002"),
    or partial match.

    For other field types: sets the Text property directly.
    """
    field_type = str(getattr(raw_com, "Type", ""))
    if field_type == "GuiComboBox":
        try:
            entries = raw_com.Entries
            if entries.Count == 0:
                raise ValueError("Dropdown has no entries to select from")
            # Try exact key match first
            for i in range(entries.Count):
                entry = entries.Item(i)
                if str(entry.Key).strip() == value.strip():
                    raw_com.Key = entry.Key
                    return
            # Try display value match (case-insensitive)
            needle = value.strip().lower()
            for i in range(entries.Count):
                entry = entries.Item(i)
                if str(entry.Value).strip().lower() == needle:
                    raw_com.Key = entry.Key
                    return
            # Try substring match
            for i in range(entries.Count):
                entry = entries.Item(i)
                if needle in str(entry.Value).strip().lower():
                    raw_com.Key = entry.Key
                    return
            available = [f"{entries.Item(i).Key}={entries.Item(i).Value}" for i in range(entries.Count)]
            raise ValueError(f"Dropdown value '{value}' not found. Available: {', '.join(available)}")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Failed to set dropdown: {exc}") from exc
    else:
        raw_com.Text = value


def _discover_fields_from_tree(flat: list[Any]) -> list[dict[str, Any]]:
    """Extract field info from a flattened element tree.

    Pure function — no COM access. Used by discover_fields() and testable independently.
    """
    # Build label map: name -> label text
    label_map: dict[str, str] = {}
    for elem in flat:
        if elem.type_as_number == 30 and elem.text.strip():  # GuiLabel
            label_map[elem.name] = elem.text.strip()

    fields = []
    discover_types = {31, 32, 33, 34, 40, 41, 42}
    for elem in flat:
        if elem.type_as_number not in discover_types:
            continue
        # For buttons, skip those with empty text (toolbar icons)
        if elem.type_as_number == 40 and not elem.text.strip():
            continue
        # Radios, checkboxes, and buttons carry their own label in elem.text;
        # input fields (31-34) look up their label from adjacent GuiLabel elements.
        if elem.type_as_number in {40, 41, 42}:
            label = elem.text.strip() if elem.text.strip() else elem.name
        else:
            label = label_map.get(elem.name, elem.name)
        fields.append(
            {
                "id": elem.id,
                "name": elem.name,
                "label": label,
                "type": elem.type,
                "selector": elem.id,
                "value": elem.text,
            }
        )
    return fields


def _active_window_id(session: Any) -> str:
    """Return the element ID of the topmost open window.

    SAP GUI enforces strict modal stacking: wnd[2] cannot exist without wnd[1].
    We scan top-down to find the highest existing window.
    """
    for i in (3, 2, 1):
        if session.find_by_id(f"wnd[{i}]", raise_error=False) is not None:
            return f"wnd[{i}]"
    return "wnd[0]"


class DesktopBackend:
    """SAP GUI Scripting (COM) backend.

    Manages multiple GuiSession objects via ``DesktopSessionRegistry``.
    A ``ContextVar`` (set by ``BackendManager``) determines which session
    is used for each async task.  All COM calls are dispatched to a shared
    ``ComThread`` for apartment-threading safety.
    """

    def __init__(self, com_thread: ComThread | None = None) -> None:
        self.com = com_thread or ComThread()
        self.registry = DesktopSessionRegistry()
        # Mutation lock — serialises high-level operations that read or modify
        # the session set: list_sessions (reconciles), open_new_session (resolves
        # the new COM child by sibling index, must not race), close_session,
        # reset_to_primary, and login (#671: holds the lock for the entire
        # login flow so two parallel sap_login calls don't race on the
        # registry counter or each other's reconcile output). Without this,
        # parallel agents racing through these paths can pre-resolve stale
        # COM IDs or close newly-spawned sessions mid-iteration. See issue
        # #637 for the original failure mode.
        self._mutation_lock: asyncio.Lock = asyncio.Lock()

    @property
    def backend_type(self) -> str:
        """Return backend identifier."""
        return "desktop"

    @property
    def _session(self) -> GuiSession | None:
        """Backward compat: return primary session."""
        try:
            return self.registry.get_session(None)
        except ValueError:
            return None

    @_session.setter
    def _session(self, value: GuiSession | None) -> None:
        """Backward compat setter: register as s1 or clear registry.

        Handles the case where ``__init__`` was skipped (e.g. tests
        using ``DesktopBackend.__new__``).
        """
        if not hasattr(self, "registry"):
            self.registry = DesktopSessionRegistry()
        if value is None:
            for sid in list(self.registry.list_sessions()):
                self.registry.unregister(sid)
        elif not self.registry.has_session("s1"):
            self.registry.register(value)

    def require_session(self) -> GuiSession:
        """Return the session for the current async context.

        Reads ``_current_session_id`` ContextVar to determine which session.
        Defaults to ``'s1'`` if no ContextVar is set (backward compat).
        """
        session_id = _current_session_id.get()
        return self.registry.get_session(session_id)  # None → "s1"

    # ---- SapNavigation ----

    async def login(  # pylint: disable=unused-argument,too-many-arguments,too-many-positional-arguments
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
        session_id: str | None = None,
        connection_name: str | None = None,
    ) -> LoginResult:
        """Log into SAP GUI desktop, opening a NEW parallel session each call.

        ``url`` is ignored — desktop uses ``connection_name`` from system config.

        **Parallel-multi-mandant contract** (issue #671): each successful
        ``login()`` adds a fresh session to the registry **without dropping any
        existing live sessions**. Re-login is no longer a "reset". The LLM can
        be logged into the same SAP Logon entry as multiple distinct
        ``(client, user)`` tuples concurrently — they all coexist in the
        registry as ``s1``, ``s2``, ``s3``, ... and tools address them via
        the ``session_id`` parameter. Use :meth:`list_sessions` to discover
        them.

        Stale sessions (e.g. after an external SAP GUI death) are still
        cleaned up: every login first runs :meth:`_reconcile_locked` which
        probes every tracked session and prunes only the dead ones. This
        preserves the issue #633 recovery contract — the dead pre-existing
        ``s1`` is pruned before the new session is registered, so the new
        login isn't shadowed by a dead proxy.
        """

        if not connection_name:
            return LoginResult(success=False, error="No connection_name configured for this system in systems.json")

        # Hold the mutation lock for the entire login flow so two parallel
        # ``sap_login`` calls don't race on the registry counter or stomp
        # each other's reconcile output. Login is rare and expensive — the
        # serialization cost is negligible.
        async with self._mutation_lock:
            try:
                # sapsucker.login.login() (>=0.5.1) opens a NEW parallel COM
                # connection per call without disturbing any existing
                # connection on the same connection_name, and verifies
                # session.info.client / .user against the requested values,
                # raising SapConnectionError on mismatch — see
                # Hochfrequenz/sapsucker#24 / #27 for the history. The except
                # block below catches that and surfaces it as
                # LoginResult.failure.
                session = await self.com.run(
                    lambda: _sapsucker_login(
                        connection_name=connection_name,
                        client=client,
                        user=username,
                        password=password,
                        language=language,
                    )
                )

                # Reconcile: prune any sessions whose underlying COM proxy
                # has died (e.g. external SAP GUI close, network drop). Live
                # sessions survive — that's what enables the parallel-multi-
                # mandant topology this PR unlocks. The previous behaviour
                # called ``self.registry.clear()`` here, which dropped *every*
                # session indiscriminately and broke parallel logins (#671).
                await self._reconcile_locked()

                new_session_id = self.registry.register(session)
                user_name = await self.com.run(lambda: str(session.info.user))
                logger.info(
                    "login",
                    extra={
                        "connection": connection_name,
                        "user": user_name,
                        "session_id": new_session_id,
                        "success": True,
                    },
                )
                return LoginResult(success=True, user=user_name, session_id=new_session_id)
            except Exception as e:
                logger.warning(
                    "login",
                    extra={"connection": connection_name, "user": username, "success": False, "error": str(e)},
                )
                return LoginResult(success=False, error=str(e))

    async def list_connections(self) -> list[Any]:
        """List available SAP Logon connections from the landscape file."""
        path = _find_landscape_path()
        if path is None:
            return []
        return _parse_landscape_xml(path.read_text(encoding="utf-8"))

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        """Navigate to a transaction code.

        Supports parameterised transactions (e.g. ``/nZ_ABAPGIT_PULL P_REPO=...``).
        The ``TransactionResult.tcode`` field stores only the base tcode.
        """
        # Extract base tcode for the result model (strip /n prefix and parameters)
        base_tcode = tcode.split()[0] if " " in tcode else tcode
        if base_tcode.startswith("/n") or base_tcode.startswith("/o"):
            stripped = base_tcode[2:]
            if stripped:
                base_tcode = stripped
            # else: bare navigation command (/n or /o alone) — keep as-is

        session = self.require_session()

        def _enter() -> str:
            okcd = session.find_by_id("wnd[0]/tbar[0]/okcd")
            if tcode.startswith("/n") or tcode.startswith("/o"):
                transaction_input = tcode
            else:
                transaction_input = f"/n{tcode}"
            cast(Any, okcd).text = transaction_input
            wnd = session.find_by_id("wnd[0]")
            cast(Any, wnd).send_v_key(0)
            return str(cast(Any, session.find_by_id("wnd[0]")).text)

        try:
            title = await self.com.run(_enter)
            logger.info("transaction", extra={"tcode": base_tcode, "title": title, "success": True})
            return TransactionResult(
                success=True,
                tcode=base_tcode,
                page_title=title,
            )
        except Exception as e:
            logger.warning("transaction", extra={"tcode": base_tcode, "success": False, "error": str(e)})
            return TransactionResult(success=False, tcode=base_tcode, error=str(e))

    async def get_session_status(self, session_id: str | None = None) -> SessionStatus:
        """Check whether the SAP session is logged in and responsive.

        Args:
            session_id: Explicit registry session ID (e.g. ``"s2"``) to probe.
                If ``None``, falls back to ``require_session()`` which reads
                the per-call ``_current_session_id`` ContextVar set by
                ``BackendManager.get_backend(session=...)``. Pass an explicit
                ID to bypass the ContextVar (useful in tests).

        Fixes #640: previously this method only ever probed ``self._session``
        (the primary session via the property), so calls like
        ``sap_session_status(session="s2")`` silently reported on s1.
        """
        try:
            if session_id is not None:
                session = self.registry.get_session(session_id)
            else:
                session = self.require_session()
        except ValueError:
            return SessionStatus(success=True, status="logged_off", message="Not logged in")
        try:
            user = await self.com.run(lambda: str(session.info.user))
            return SessionStatus(success=True, status="active", message=f"Logged in as {user}")
        except Exception:
            return SessionStatus(success=True, status="unknown", message="Session not responsive")

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        """Wait until the session is no longer busy."""
        session = self.require_session()
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while asyncio.get_running_loop().time() < deadline:
            busy = await self.com.run(lambda: bool(session.busy))
            if not busy:
                return
            await asyncio.sleep(0.2)

    async def wait_for_sap_ready(self, timeout_ms: int = 5000) -> None:
        """Desktop backend: COM calls are synchronous, so this is a no-op."""

    async def bring_to_front(self) -> None:
        """Bring the SAP GUI window to the foreground."""
        session = self.require_session()
        await self.com.run(
            lambda: (
                cast(Any, session.find_by_id("wnd[0]")).iconify(),
                cast(Any, session.find_by_id("wnd[0]")).restore(),
            )
        )

    async def wait(self, timeout_ms: int = 200) -> None:
        """Wait for a fixed duration."""
        await asyncio.sleep(timeout_ms / 1000)

    async def start_keepalive(self, interval_seconds: int = 300) -> None:
        """No-op — desktop sessions don't time out like WebGUI."""

    async def stop_keepalive(self) -> bool:
        """No-op. Returns False (no keepalive was running)."""
        return False

    async def open_new_session(self, tcode: str) -> tuple[str | None, int, str | None]:
        """Open a transaction in a new session/mode (/o).

        Returns ``(registry_session_id, session_count, page_title)``.
        The session ID is a registry ID like ``'s2'``, not a COM path.

        Reconciles the registry first so that any dead sessions left over
        from prior failures don't inflate the count or hold session IDs.
        Serialised through ``_mutation_lock`` so concurrent agents can't
        race against ``Children.Count`` / ``Children(count - 1)``.
        """
        async with self._mutation_lock:
            await self._reconcile_locked()
            return await self._open_new_session_locked(tcode)

    async def _open_new_session_locked(self, tcode: str) -> tuple[str | None, int, str | None]:
        """``open_new_session`` body — caller must hold ``_mutation_lock``."""
        session = self.require_session()

        try:
            await self.com.run(session.create_session)
            await asyncio.sleep(1)

            def _navigate() -> tuple[Any, int, str | None]:
                from sapsucker._factory import wrap_com_object  # pylint: disable=import-outside-toplevel

                conn_com = session.com.Parent
                count = conn_com.Children.Count
                if count < 2:
                    return None, count, None
                new_ses_com = conn_com.Children(count - 1)
                new_gui_session = wrap_com_object(new_ses_com)
                # Enter transaction in new session
                new_ses_com.FindById("wnd[0]/tbar[0]/okcd").Text = f"/n{tcode}"
                new_ses_com.FindById("wnd[0]").SendVKey(0)
                title = str(new_ses_com.FindById("wnd[0]").Text)
                return new_gui_session, count, title

            result_session, count, title = await self.com.run(_navigate)
            if result_session is None:
                return None, count, None
            session_id = self.registry.register(result_session)
            logger.info("open_session", extra={"tcode": tcode, "session_id": session_id, "count": count})
            return session_id, count, title
        except Exception:
            logger.exception("open_session")
            return None, 1, None

    async def list_sessions(self) -> list[SessionInfo]:
        """List all sessions from the registry with their COM properties.

        Reconciles the registry first so the returned list reflects reality
        — dead sessions are pruned, never silently included or silently
        skipped. Serialised through ``_mutation_lock`` so concurrent
        ``open_new_session`` / ``close_session`` cannot leave the snapshot
        and the underlying COM tree out of sync.
        """
        async with self._mutation_lock:
            await self._reconcile_locked()
            return await self._list_sessions_locked()

    async def _list_sessions_locked(self) -> list[SessionInfo]:
        """``list_sessions`` body — caller must hold ``_mutation_lock``."""
        result: list[SessionInfo] = []
        for sid in self.registry.list_sessions():
            try:
                ses = self.registry.get_session(sid)

                def _info(s: Any = ses) -> dict[str, str]:
                    info = s.com.Info
                    return {
                        "tcode": str(info.Transaction),
                        "title": str(s.com.FindById("wnd[0]").Text),
                        "system_name": str(info.SystemName),
                        "client": str(info.Client),
                        "user": str(info.User),
                    }

                info = await self.com.run(_info)
                result.append(
                    SessionInfo(
                        session_id=sid,
                        is_primary=(sid == self.registry.primary_session),
                        agent_id=self.registry.get_bound_agent(sid),
                        **info,
                    )
                )
            except Exception:  # pylint: disable=broad-exception-caught
                # Reconcile already ran above, so a COM error here is a
                # transient hiccup; skip the row but keep the session in
                # the registry. The next list_sessions call will reconcile
                # again and prune it if it really is gone.
                logger.warning("Skipping session %s in listing (COM error)", sid)
        return result

    async def close_session(self, session_id: str) -> bool:
        """Close a session by registry ID (e.g. 's2')."""
        async with self._mutation_lock:
            return await self._close_session_locked(session_id)

    async def _close_session_locked(self, session_id: str) -> bool:
        """``close_session`` body — caller must hold ``_mutation_lock``.

        Resolves the target's COM ``.Id`` *inside* the same COM lambda that
        calls ``CloseSession`` so the index is fresh: closing a session
        causes SAP to renumber the remaining ``ses[N]`` indices, so any
        pre-resolved IDs would point at the wrong window after the first
        close. The Python registry is updated regardless of the COM result
        — even on failure we drop the dead reference to avoid drift.

        Exception: a "busy" COM error (``is_transient_busy_error``) — e.g. a
        modal ABAP debugger blocking the message loop — does NOT drop the
        reference. The session is very much alive, just not accepting the
        close command right now; unregistering it here would silently orphan
        a live, in-use session from the registry's point of view, which is
        exactly the collapse issue #791 was about. The caller sees
        ``success=False`` and the session stays put for a retry.
        """
        if not self.registry.has_session(session_id):
            return False
        try:
            target = self.registry.get_session(session_id)
            primary = self.registry.get_session(None)  # primary session

            def _close(t: Any = target, p: Any = primary) -> bool:
                # Get COM ID on the COM thread (Id property requires COM context)
                com_id = str(t.com.Id)
                conn = p.com.Parent
                conn.CloseSession(com_id)
                return True

            result = await self.com.run(_close)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if is_transient_busy_error(exc):
                logger.info(
                    "close_session_busy",
                    extra={"session_id": session_id, "error": repr(exc)[:200]},
                )
                return False
            result = False
        self.registry.unregister(session_id)
        logger.info("close_session", extra={"session_id": session_id, "success": result})
        return result

    # ---- Reconciliation & bulk cleanup (issue #637) ----

    async def reconcile(self) -> dict[str, list[str]]:
        """Probe every tracked session and prune dead ones from the registry.

        Returns ``{"alive": [...], "removed": [...]}``. ``alive`` lists the
        registry IDs that successfully responded to a liveness probe;
        ``removed`` lists the IDs that were pruned because the probe raised.

        The probe touches the live UI tree (``FindById('wnd[0]').Type``)
        instead of the cached ``Info`` sub-object — ``Info`` is a fast-path
        cache that returns the *last known* values for a dead window, so
        a dead session can probe as alive. ``FindById`` forces a real COM
        round-trip and surfaces stale-proxy errors immediately.

        The probe call uses ``max_retries=0`` so the COM thread does NOT
        retry on ``RPC_S_UNKNOWN_IF`` — a stale-interface error on a probe
        means "this session is dead", not "transient — try again".

        A "server busy" error (``RPC_E_SERVERCALL_RETRYLATER`` /
        ``RPC_E_CALL_REJECTED``) is **not** treated as dead: it means the SAP
        GUI process's message loop is currently blocked and rejected the
        call outright — most commonly because a modal dialog (e.g. an ABAP
        debugger stopped at a breakpoint) is running its own nested message
        loop. That is a different failure mode than a stale/dead interface,
        and pruning the session for it destroyed the registry the moment a
        breakpoint fired (issue #791). Busy sessions are kept in ``alive``
        so the caller can retry once the dialog is dismissed.
        """
        async with self._mutation_lock:
            return await self._reconcile_locked()

    #: Per-probe timeout, in seconds. Reconciliation must not block forever
    #: on a wedged COM thread — that would deadlock the very recovery path
    #: agents reach for when COM is misbehaving.  ``asyncio.wait_for`` raises
    #: ``TimeoutError`` past this point and the session is treated as dead.
    _RECONCILE_PROBE_TIMEOUT_S: float = 2.0

    #: How long a session may stay classified "busy" (see
    #: ``is_transient_busy_error``) before reconcile gives up and prunes it
    #: like any other dead session. A modal ABAP debugger is expected to
    #: clear within minutes; without this cap a genuinely wedged/corrupted
    #: COM proxy that happens to raise the same busy-flavoured error on every
    #: probe would stay "alive" forever — never pruned, its binding never
    #: freed, with no recovery path (issue #791 follow-up).
    _RECONCILE_BUSY_DEAD_TIMEOUT_S: float = 900.0

    async def _reconcile_locked(self) -> dict[str, list[str]]:
        """``reconcile`` body — caller must hold ``_mutation_lock``."""
        snapshot = list(self.registry.list_sessions())
        alive: list[str] = []
        dead: list[str] = []
        for sid in snapshot:
            try:
                ses = self.registry.get_session(sid)
            except ValueError:
                # Vanished between snapshot and lookup — already gone.
                dead.append(sid)
                continue

            def _probe(s: Any = ses) -> str:
                # FindById on wnd[0] forces a real COM round-trip — Info
                # would happily return cached values for a dead window.
                return str(s.com.FindById("wnd[0]").Type)

            try:
                await asyncio.wait_for(
                    self.com.run(_probe, max_retries=0),
                    timeout=self._RECONCILE_PROBE_TIMEOUT_S,
                )
                self.registry.mark_alive(sid)
                alive.append(sid)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                # Wedged COM thread → can't prove the session is alive,
                # treat it as dead so recovery can proceed.
                logger.warning(
                    "reconcile_probe_timeout",
                    extra={
                        "session_id": sid,
                        "bound_to": self.registry.get_bound_agent(sid),
                        "timeout_s": self._RECONCILE_PROBE_TIMEOUT_S,
                        "error": repr(exc)[:200],
                    },
                )
                dead.append(sid)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if is_transient_busy_error(exc):
                    # The process is there, it just rejected the call while
                    # busy (e.g. a modal ABAP debugger). Not proof of death —
                    # keep the session, but only for as long as
                    # _RECONCILE_BUSY_DEAD_TIMEOUT_S: a session that never
                    # recovers from "busy" is indistinguishable from a truly
                    # wedged one and must eventually be reclaimable.
                    now = time.monotonic()
                    busy_since = self.registry.mark_busy(sid, now)
                    busy_for_s = now - busy_since
                    if busy_for_s <= self._RECONCILE_BUSY_DEAD_TIMEOUT_S:
                        logger.info(
                            "reconcile_session_busy",
                            extra={
                                "session_id": sid,
                                "bound_to": self.registry.get_bound_agent(sid),
                                "busy_for_s": round(busy_for_s, 1),
                                "error": repr(exc)[:200],
                            },
                        )
                        alive.append(sid)
                        continue
                    logger.warning(
                        "reconcile_busy_timeout_exceeded",
                        extra={
                            "session_id": sid,
                            "bound_to": self.registry.get_bound_agent(sid),
                            "busy_for_s": round(busy_for_s, 1),
                            "timeout_s": self._RECONCILE_BUSY_DEAD_TIMEOUT_S,
                            "error": repr(exc)[:200],
                        },
                    )
                    dead.append(sid)
                    continue
                logger.info(
                    "reconcile_dead_session",
                    extra={
                        "session_id": sid,
                        "bound_to": self.registry.get_bound_agent(sid),
                        "error": repr(exc)[:200],
                    },
                )
                dead.append(sid)

        removed = self.registry.prune(dead)
        if removed:
            logger.info(
                "reconcile_complete",
                extra={"alive": alive, "removed": removed},
            )
        return {"alive": alive, "removed": removed}

    async def reset_to_primary(self) -> dict[str, list[str]]:
        """Close every session except the primary one.

        Reconciles first so we don't try to close already-dead sessions,
        then iterates the surviving non-primary sessions and closes them
        one at a time (each ``CloseSession`` may renumber sibling indices,
        so we resolve+close inside a single COM lambda per victim).

        Returns a dict with:
          - ``closed``        — registry IDs successfully closed
          - ``remaining``     — registry IDs still active afterwards
          - ``killed_agents`` — agent IDs that had been bound to closed
                                sessions; their next call will fail and
                                they should re-bind to a new session
          - ``errors``        — human-readable error strings, one per
                                failed close attempt
        """
        async with self._mutation_lock:
            await self._reconcile_locked()
            # Busy-agnostic on purpose (issue #791 follow-up): the responsive-
            # preferring `registry.primary_session` would make a busy primary
            # (e.g. mid-breakpoint-debug) look like a victim while an idle
            # stray session looks "primary" — exactly inverting this sweep's
            # contract. `canonical_primary_session` always keeps 's1' (or the
            # lowest id) regardless of busy state.
            primary = self.registry.canonical_primary_session()
            victims = [sid for sid in self.registry.list_sessions() if sid != primary]
            closed: list[str] = []
            errors: list[str] = []
            killed_agents: list[str] = []
            for sid in victims:
                bound = self.registry.get_bound_agent(sid)
                try:
                    ok = await self._close_session_locked(sid)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    errors.append(f"{sid}: {exc}")
                    # _close_session_locked unregisters even on exception,
                    # but a raise here means we never reached that line —
                    # double-check and prune if needed.
                    if self.registry.has_session(sid):
                        self.registry.prune([sid])
                    continue
                # ``_close_session_locked`` unregisters before returning in
                # almost every case — even when CloseSession raised
                # internally — so "registry slot freed" is normally the
                # right success signal, not the COM-level boolean. The one
                # exception is a "busy" COM error (issue #791: e.g. a modal
                # debugger), where it deliberately leaves the session
                # registered rather than orphaning a live session — that
                # case falls into the ``else`` branch below as a real error.
                # ``ok=False`` with a freed slot just means COM complained on
                # the way out; we still mark it as closed AND record the COM
                # warning so the agent can see the backend chatter without
                # misreading "still pending".
                slot_freed = not self.registry.has_session(sid)
                if slot_freed:
                    closed.append(sid)
                    if bound:
                        killed_agents.append(bound)
                    if not ok:
                        errors.append(f"{sid}: closed but COM CloseSession returned False")
                else:
                    # The slot survived — that's a real failure. The
                    # session is still in the registry and a follow-up
                    # call may try to use it.
                    errors.append(f"{sid}: close failed and registry slot is still occupied")
            # Final reconcile in case CloseSession left anything behind.
            await self._reconcile_locked()
            remaining = list(self.registry.list_sessions())
            logger.info(
                "reset_to_primary",
                extra={
                    "primary": primary,
                    "closed": closed,
                    "remaining": remaining,
                    "killed_agents": killed_agents,
                    "errors": errors,
                },
            )
            return {
                "closed": closed,
                "remaining": remaining,
                "killed_agents": killed_agents,
                "errors": errors,
            }

    async def bind_session(self, session_id: str, agent_id: str, *, force: bool = False) -> str | None:
        """Bind an agent to a session.

        Strict by default (#643): raises ``SessionBindConflictError`` if the
        session is bound to a different agent. Pass ``force=True`` to take
        over.
        """
        prev = self.registry.get_bound_agent(session_id)
        self.registry.bind(session_id, agent_id, force=force)
        return prev

    async def release_session(self, session_id: str) -> str | None:
        """Release agent binding from a session."""
        prev = self.registry.get_bound_agent(session_id)
        self.registry.release(session_id)
        return prev

    async def has_session(self, session_id: str) -> bool:
        """Check whether a session exists in the registry."""
        return self.registry.has_session(session_id)

    # ---- SapUiInspection ----

    async def get_status_bar(self) -> StatusBarInfo:
        """Read the SAP status bar."""
        session = self.require_session()

        def _read() -> tuple[str, str]:
            wnd_id = _active_window_id(session)
            sbar = session.find_by_id(f"{wnd_id}/sbar", raise_error=False)
            if sbar is None:
                return "", ""
            return str(cast(Any, sbar).text), str(cast(Any, sbar).message_type)

        text, msg_type = await self.com.run(_read)
        bar_type: StatusBarType = cast(StatusBarType, msg_type) if msg_type in ("S", "E", "W", "I", "A") else "none"
        logger.debug("status_bar", extra={"type": bar_type, "message": text})
        return StatusBarInfo(success=True, type=bar_type, message=text)

    async def get_screen_info(self) -> ScreenInfo:
        """Get technical screen information."""
        session = self.require_session()

        def _read() -> dict[str, Any]:
            wnd_id = _active_window_id(session)
            info = session.info
            wnd = session.find_by_id(wnd_id)
            return {
                "transaction": str(info.transaction),
                "title": str(cast(Any, wnd).text),
                "program": str(info.program),
                "dynpro": str(info.screen_number),
                "system_name": str(info.system_name),
                "client": str(info.client),
                "user": str(info.user),
            }

        data = await self.com.run(_read)
        return ScreenInfo(success=True, url="desktop://sap", **data)

    async def get_screen_text(  # pylint: disable=unused-argument
        self, include_dropdown_options: bool = False
    ) -> ScreenText:
        """Get readable text from the current screen via dump_tree."""
        session = self.require_session()

        def _read() -> dict[str, Any]:
            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            title = str(cast(Any, wnd).text)
            sbar = session.find_by_id(f"{wnd_id}/sbar", raise_error=False)
            sbar_text = str(cast(Any, sbar).text) if sbar is not None else ""
            tree = cast(Any, wnd).dump_tree()

            labels, buttons, tabs, content = [], [], [], []
            for elem in _flatten(tree):
                t = elem.type_as_number
                txt = elem.text.strip()
                if not txt:
                    continue
                if t == 30:  # GuiLabel
                    labels.append(txt)
                elif t == 40:  # GuiButton
                    buttons.append(txt)
                elif t == 91:  # GuiTab
                    tabs.append(txt)
                else:
                    content.append(txt)

            return {
                "title": title,
                "status_bar": sbar_text or None,
                "tabs": tabs,
                "labels": list(dict.fromkeys(labels)),
                "buttons": list(dict.fromkeys(buttons)),
                "table_headers": [],
                "main_content": content,
            }

        data = await self.com.run(_read)
        return ScreenText(success=True, **data)

    async def discover_fields(self) -> list[FieldInfo]:
        """Discover input fields, radio buttons, checkboxes, and pushbuttons on screen."""
        session = self.require_session()

        def _discover() -> list[dict[str, Any]]:
            wnd_id = _active_window_id(session)
            usr = session.find_by_id(f"{wnd_id}/usr")
            tree = cast(Any, usr).dump_tree()
            flat = _flatten(tree)
            return _discover_fields_from_tree(flat)

        items = await self.com.run(_discover)
        logger.debug("discover_fields", extra={"count": len(items)})
        return [FieldInfo(**item) for item in items]

    async def get_form_fields(self, *, include_dropdown_options: bool = False) -> FormFieldsResult:
        """Detect form fields with their current values and associated labels."""

        session = self.require_session()

        def _discover() -> tuple[list[dict[str, Any]], str]:
            wnd_id = _active_window_id(session)
            usr = session.find_by_id(f"{wnd_id}/usr")
            tree = cast(Any, usr).dump_tree()
            flat = _flatten(tree)

            # Build label map: name -> label text
            label_map: dict[str, str] = {}
            for elem in flat:
                if elem.type_as_number == 30 and elem.text.strip():  # GuiLabel
                    label_map[elem.name] = elem.text.strip()

            # Type number to SapFieldType mapping
            type_map = {
                31: "text",  # GuiTextField
                32: "text",  # GuiCTextField
                33: "text",  # GuiPasswordField
                34: "dropdown",  # GuiComboBox
                42: "checkbox",  # GuiCheckBox
                41: "radio",  # GuiRadioButton
            }

            fields: list[dict[str, Any]] = []
            for elem in flat:
                if elem.type_as_number not in type_map:
                    continue
                field_type = type_map[elem.type_as_number]
                label_text = label_map.get(elem.name, elem.name)
                field_dict: dict[str, Any] = {
                    "id": elem.id,
                    "label": label_text,
                    "field_type": field_type,
                    "current_value": elem.text if elem.text else None,
                }
                if field_type in ("checkbox", "radio"):
                    field_dict["checked"] = bool(elem.text)
                fields.append(field_dict)
            return fields, wnd_id

        items, active_wnd = await self.com.run(_discover)
        logger.debug("get_form_fields", extra={"count": len(items)})

        fields = [FormField(**item) for item in items]
        if include_dropdown_options:
            for field in fields:
                if field.field_type == SapFieldType.DROPDOWN:
                    field.options = await self.get_dropdown_options(field.label)

        return FormFieldsResult(
            success=True,
            fields=fields,
            active_window=active_wnd,
        )

    async def discover_buttons(self) -> list[ButtonInfo]:
        """Discover clickable buttons on the current screen."""
        session = self.require_session()

        def _discover() -> list[dict[str, Any]]:
            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            tree = cast(Any, wnd).dump_tree()
            buttons: list[dict[str, Any]] = []
            for elem in _flatten(tree):
                if elem.type_as_number != 40:  # GuiButton
                    continue
                label = elem.text.strip()
                if not label:
                    label = elem.tooltip.strip()
                if label:
                    buttons.append({"label": label, "id": elem.id, "selector": elem.id})
            return buttons

        items = await self.com.run(_discover)
        logger.debug("discover_buttons", extra={"count": len(items)})
        return [ButtonInfo(**item) for item in items]

    async def get_snapshot(self) -> ComTreeSnapshot:
        """Get a text dump of the SAP GUI element tree.

        Returns ComTreeSnapshot — an indented tree of element types, names,
        and text values from dump_tree(). This is NOT an ARIA snapshot.
        Used for LLM context, not structured parsing.
        """
        snapshot, _, _ = await self.get_snapshot_with_depth()
        return snapshot

    async def get_snapshot_with_depth(self, depth: int | None = None) -> tuple[ComTreeSnapshot, int, int]:
        """Get a text dump with optional truncation and metadata.

        Args:
            depth: If given, truncate the tree to this many levels.

        Returns:
            (snapshot, max_depth_found, elements_hidden)
        """
        from sapguimcp.backend.desktop._snapshot_render import (  # pylint: disable=import-outside-toplevel
            render_snapshot_lines,
        )
        from sapguimcp.backend.desktop._truncation import (  # pylint: disable=import-outside-toplevel
            truncate_tree,
        )

        session = self.require_session()

        def _dump() -> tuple[str, int, int]:
            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            tree = cast(Any, wnd).dump_tree()

            max_depth_found = 0
            elements_hidden = 0

            if depth is not None:
                tree, max_depth_found, elements_hidden = truncate_tree(tree, depth)

            lines = render_snapshot_lines(tree)

            if elements_hidden > 0:
                lines.append(
                    f"\n[Truncated at depth {depth}: "
                    f"{elements_hidden} elements hidden. "
                    f"Full tree depth is {max_depth_found}. "
                    f"Use depth={max_depth_found} to see everything.]"
                )

            return "\n".join(lines), max_depth_found, elements_hidden

        text, max_depth_found, elements_hidden = await self.com.run(_dump)
        return ComTreeSnapshot(text), max_depth_found, elements_hidden

    async def take_screenshot(self) -> bytes:
        """Take a screenshot of the SAP GUI window."""
        session = self.require_session()

        def _screenshot() -> bytes:
            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            tmp = os.path.join(tempfile.gettempdir(), "sapgui_screenshot.png")
            cast(Any, wnd).hard_copy(tmp, 2)  # 2 = PNG
            with open(tmp, "rb") as f:
                data = f.read()
            os.unlink(tmp)
            return data

        try:
            result = await self.com.run(_screenshot)
            logger.debug("screenshot", extra={"bytes": len(result)})
            return result
        except Exception:
            logger.exception("screenshot")
            raise

    async def read_table(
        self,
        start_row: int = 1,
        end_row: int | None = None,
        max_rows: int = 100,
    ) -> TableData:
        """Read data from an ALV grid or table control."""
        session = self.require_session()

        def _read() -> dict[str, Any]:  # pylint: disable=too-many-locals

            # Find grid or table in the full window tree (not just usr).
            # SE16N places ALV grids in wnd[0]/shellcont, not wnd[0]/usr.
            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            tree = cast(Any, wnd).dump_tree()
            grid_id = None
            for elem in _flatten(tree):
                if elem.type_as_number in (122, 80):
                    grid_id = elem.id
                    break

            if grid_id is None:
                return {"headers": [], "rows": [], "total_rows": 0, "start_row": 1}

            grid = session.find_by_id(grid_id)
            if isinstance(grid, GuiGridView):
                row_count = cast(Any, grid).row_count
                col_order = cast(Any, grid).column_order
                # col_order may be a Python list (sapsucker) or COM collection
                headers = (
                    list(col_order)
                    if isinstance(col_order, list)
                    else [str(col_order(ci)) for ci in range(col_order.Count)]
                )

                actual_end = min(end_row or (start_row + max_rows - 1), row_count)
                rows = []
                for ri in range(start_row - 1, actual_end):
                    data = {}
                    for col_name in headers:
                        data[col_name] = str(cast(Any, grid).get_cell_value(ri, col_name))
                    rows.append({"row": ri + 1, "data": data})

                return {
                    "headers": headers,
                    "rows": rows,
                    "total_rows": row_count,
                    "start_row": start_row,
                    "end_row": actual_end,
                }

            return {"headers": [], "rows": [], "total_rows": 0, "start_row": 1}

        try:
            data = await self.com.run(_read)
        except Exception:
            logger.exception("read_table")
            raise
        rows = [TableRow(**r) for r in data.pop("rows", [])]
        logger.debug(
            "read_table",
            extra={"rows": len(rows), "start": data.get("start_row"), "end": data.get("end_row")},
        )
        return TableData(success=True, rows=rows, **data)

    async def click_table_cell(self, row: int, column: int | str, action: str = "click") -> TableCellClickResult:
        """Click a cell in an ALV grid table."""
        session = self.require_session()

        def _click() -> None:

            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            tree = cast(Any, wnd).dump_tree()
            for elem in _flatten(tree):
                if elem.type_as_number == 122:
                    grid = session.find_by_id(elem.id)
                    if isinstance(grid, GuiGridView):
                        col_name = str(column)
                        if isinstance(column, int):
                            col_order = cast(Any, grid).column_order
                            col_name = str(col_order[column]) if isinstance(col_order, list) else str(col_order(column))
                        if action in ("dblclick", "double_click"):
                            cast(Any, grid).double_click(row - 1, col_name)
                        else:
                            cast(Any, grid).click(row - 1, col_name)
                        return
            raise ValueError("No ALV grid found on screen")

        try:
            await self.com.run(_click)
            return TableCellClickResult(success=True, row=row, column=str(column), selector_used="com")
        except Exception as e:
            return TableCellClickResult(success=False, row=row, column=str(column), selector_used="com", error=str(e))

    async def get_dropdown_options(self, label: str) -> list[str]:
        """Get options from a GuiComboBox dropdown found by label.

        Returns a list of ``"KEY - Display Value"`` strings (matching
        the webgui backend format) or an empty list if the field is not
        found or is not a combobox.
        """
        session = self.require_session()

        def _read_options() -> list[str]:
            try:
                wnd_id = _active_window_id(session)
                cmb = find_combobox_by_label(session, label, wnd_id=wnd_id)
                if cmb is None:
                    return []
                return [f"{e.key} - {e.value}" for e in cmb.entries]
            except Exception:
                logger.warning("Failed to read dropdown options", extra={"label": label})
                return []

        return await self.com.run(_read_options)

    async def get_page_title(self) -> str:
        """Get the current window title."""
        session = self.require_session()

        def _title() -> str:
            wnd_id = _active_window_id(session)
            return str(cast(Any, session.find_by_id(wnd_id)).text)

        return await self.com.run(_title)

    # ---- SapUiPrimitives (only press_key in Phase 1) ----

    async def press_key(self, key: str) -> KeyboardResult:
        """Send a keyboard shortcut via SAP VKey."""
        session = self.require_session()
        try:
            vkey = key_to_vkey(key)
        except KeyError:
            return KeyboardResult(success=False, key=key, error=f"Unknown key: {key}")

        def _press() -> tuple[str, str, str, str]:
            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            cast(Any, wnd).send_v_key(vkey)
            # Re-detect active window after the key press (may have opened/closed a popup)
            post_wnd = _active_window_id(session)
            title = str(cast(Any, session.find_by_id(post_wnd)).text)
            sbar = session.find_by_id(f"{post_wnd}/sbar", raise_error=False)
            if sbar is None:
                return title, "", "", post_wnd
            return title, str(cast(Any, sbar).text), str(cast(Any, sbar).message_type), post_wnd

        try:
            title, sbar_text, sbar_type, active_wnd = await self.com.run(_press)
            resolved_type: StatusBarType = (
                cast(StatusBarType, sbar_type) if sbar_type in ("S", "E", "W", "I", "A") else "none"
            )
            logger.debug("press_key", extra={"key": key, "vkey": vkey, "title": title})
            return KeyboardResult(
                success=True,
                key=key,
                page_title=title,
                status_bar_read=True,
                status_bar_type=resolved_type,
                status_bar_message=sbar_text,
                active_window=active_wnd,
            )
        except Exception as e:
            return KeyboardResult(success=False, key=key, error=str(e))

    # ---- Stub methods (Phase 2 + 3) ----

    async def fill_field(self, label: str, value: str) -> None:
        """Fill a labelled input field.

        Detects GuiComboBox fields and sets them by matching the display text
        against the dropdown entries, setting the Key property instead of Text.
        """
        session = self.require_session()

        def _fill() -> None:
            wnd_id = _active_window_id(session)
            flat_tree = _dump_flat_tree(session, wnd_id)
            field = find_field_by_label(session, label, flat_tree, wnd_id=wnd_id)
            if field is None:
                raise ValueError(f"Field not found: {label}")
            _set_field_value(_unwrap_com(field), value)

        await self.com.run(_fill)
        logger.info("fill_field", extra={"label": label, "value": value})

    async def fill_main_input(self, value: str, labels: list[str]) -> bool:
        """Fill the main form input — try each label, fill first match."""
        session = self.require_session()

        def _fill() -> bool:
            wnd_id = _active_window_id(session)
            flat_tree = _dump_flat_tree(session, wnd_id)
            for lbl in labels:
                field = find_field_by_label(session, lbl, flat_tree, wnd_id=wnd_id)
                if field is not None:
                    _set_field_value(_unwrap_com(field), value)
                    return True
            return False

        result = await self.com.run(_fill)
        logger.info("fill_main_input", extra={"value": value, "found": result})
        return result

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult:
        """Fill multiple form fields."""

        session = self.require_session()

        def _fill() -> dict[str, Any]:
            wnd_id = _active_window_id(session)
            flat_tree = _dump_flat_tree(session, wnd_id)
            filled: list[str] = []
            not_found: list[str] = []
            errors: list[dict[str, str]] = []
            for label, value in fields.items():
                try:
                    field = find_field_by_label(session, label, flat_tree, wnd_id=wnd_id)
                    if field is None:
                        not_found.append(label)
                        continue
                    _set_field_value(_unwrap_com(field), value)
                    filled.append(label)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    errors.append({"field": label, "error": str(exc)})
            return {"filled": filled, "not_found": not_found, "errors": errors, "wnd_id": wnd_id}

        data = await self.com.run(_fill)
        logger.info(
            "fill_form",
            extra={"filled": len(data["filled"]), "not_found": len(data["not_found"]), "errors": len(data["errors"])},
        )
        has_failures = len(data["not_found"]) > 0 or len(data["errors"]) > 0
        error_msg = None
        if has_failures:
            parts = []
            if data["not_found"]:
                parts.append(f"Fields not found: {', '.join(data['not_found'])}")
            if data["errors"]:
                parts.append(f"Errors: {', '.join(e['field'] for e in data['errors'])}")
            error_msg = "; ".join(parts)
        return FillFormResult(
            success=not has_failures,
            error=error_msg,
            filled=data["filled"],
            not_found=data["not_found"],
            errors=[FieldFillError(**e) for e in data["errors"]],
            active_window=data["wnd_id"],
        )

    async def click_button(self, label: str) -> None:
        """Click a button by label."""
        session = self.require_session()

        def _click() -> None:
            wnd_id = _active_window_id(session)
            btn = find_button_by_label(session, label, wnd_id=wnd_id)
            if btn is None:
                raise ValueError(f"Button not found: {label}")
            cast(Any, btn).press()

        await self.com.run(_click)
        logger.info("click_button", extra={"label": label})

    async def click_tab(self, label: str) -> None:
        """Click a tab by label."""
        session = self.require_session()

        def _click() -> None:
            wnd_id = _active_window_id(session)
            tab = find_tab_by_label(session, label, wnd_id=wnd_id)
            if tab is None:
                raise ValueError(f"Tab not found: {label}")
            cast(Any, tab).select()

        await self.com.run(_click)
        logger.info("click_tab", extra={"label": label})

    async def type_text(self, text: str) -> None:
        """Type text into the focused element."""
        session = self.require_session()

        def _type() -> None:
            wnd_id = _active_window_id(session)
            wnd = session.find_by_id(wnd_id)
            focus_elem = cast(Any, wnd).focused_element
            if focus_elem is not None:
                focus_elem.text = text
            else:
                raise ValueError("No focused element found")

        await self.com.run(_type)
        logger.info("type_text", extra={"length": len(text)})

    async def set_checkbox(self, label: str, checked: bool) -> None:
        """Set a checkbox by label."""
        session = self.require_session()

        def _set() -> None:
            wnd_id = _active_window_id(session)
            chk = find_checkbox_by_label(session, label, wnd_id=wnd_id)
            if chk is None:
                raise ValueError(f"Checkbox not found: {label}")
            cast(Any, chk).selected = checked

        await self.com.run(_set)
        logger.info("set_checkbox", extra={"label": label, "checked": checked})

    async def set_radio_button(self, label: str) -> None:
        """Select a radio button by label."""
        session = self.require_session()

        def _set() -> None:
            wnd_id = _active_window_id(session)
            rad = find_radio_by_label(session, label, wnd_id=wnd_id)
            if rad is None:
                raise ValueError(f"Radio button not found: {label}")
            cast(Any, rad).selected = True

        await self.com.run(_set)
        logger.info("set_radio_button", extra={"label": label})

    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult:
        """Select a dropdown option."""

        session = self.require_session()

        def _select() -> dict[str, Any]:
            wnd_id = _active_window_id(session)
            cmb = find_combobox_by_label(session, label, wnd_id=wnd_id)
            if cmb is None:
                # Also try find_field_by_label as fallback
                flat_tree = _dump_flat_tree(session, wnd_id)
                cmb = find_field_by_label(session, label, flat_tree, wnd_id=wnd_id)
            if cmb is None:
                return {"success": False, "error_message": f"Dropdown not found: {label}"}
            try:
                cast(Any, cmb).value = option
                return {"success": True}
            except Exception as exc:  # pylint: disable=broad-exception-caught
                return {"success": False, "error_message": str(exc)}

        data = await self.com.run(_select)
        logger.info("select_dropdown", extra={"label": label, "option": option, "success": data["success"]})
        return DropdownFillResult(**data)

    async def focus_and_type(  # pylint: disable=unused-argument
        self, accessible_name: str, text: str, delay_ms: int = 0
    ) -> bool:
        """Focus and type into an element by accessible name or field name.

        Tries multiple strategies:
        1. Direct find_by_id with common prefixes (fast, works for field names like GD-TAB)
        2. find_field_by_label (label text matching, slower)
        """
        session = self.require_session()

        def _type() -> bool:
            wnd_id = _active_window_id(session)
            # Strategy 1: try direct find_by_id with common prefixes (fast)
            for prefix in ("txt", "ctxt", "pwd", "cmb"):
                try:
                    field = session.find_by_id(f"{wnd_id}/usr/{prefix}{accessible_name}", raise_error=False)
                    if field is not None:
                        _set_field_value(_unwrap_com(field), text)
                        logger.debug(
                            "focus_and_type_found",
                            extra={"field_name": accessible_name, "strategy": "direct", "prefix": prefix},
                        )
                        return True
                except Exception as exc:
                    logger.debug(
                        "focus_and_type_error",
                        extra={"field_name": accessible_name, "prefix": prefix, "error": str(exc)},
                    )
            # Strategy 2: label-based search (slower)
            flat_tree = _dump_flat_tree(session, wnd_id)
            field = find_field_by_label(session, accessible_name, flat_tree, wnd_id=wnd_id)
            if field is None:
                return False
            _set_field_value(_unwrap_com(field), text)
            return True

        result = await self.com.run(_type)
        logger.info("focus_and_type", extra={"field_name": accessible_name, "found": result})
        return result

    # ---- SapEditor ----

    @staticmethod
    def _find_editor_shell_raw(session: Any) -> tuple[Any, str] | None:
        """Find an AbapEditor or TextEdit shell via raw COM.

        Returns ``(raw_com_shell, sub_type)`` or ``None``.
        Uses raw COM ``FindById`` to avoid sapsucker wrapper issues
        with ``GuiAbapEditor`` property access.
        """
        wnd_id = _active_window_id(session)
        raw_session: Any = getattr(session, "com", getattr(session, "_com", session))
        usr = session.find_by_id(f"{wnd_id}/usr")
        tree = cast(Any, usr).dump_tree()
        for elem in _flatten(tree):
            if elem.type_as_number == 122:  # GuiShell
                shell = session.find_by_id(elem.id)
                sub_type = getattr(cast(Any, shell), "sub_type", "")
                if sub_type in ("AbapEditor", "TextEdit"):
                    # Extract relative ID (wnd[0]/...) from full path (/app/con[N]/ses[N]/wnd[0]/...)
                    full_id = elem.id
                    wnd_idx = full_id.find("wnd[")
                    relative_id = full_id[wnd_idx:] if wnd_idx >= 0 else full_id
                    raw_shell = raw_session.FindById(relative_id, False)
                    if raw_shell is None:
                        raw_shell = getattr(shell, "com", getattr(shell, "_com", shell))
                    return raw_shell, sub_type
        return None

    async def read_editor_source(self) -> str | None:
        """Read the current source code from an open ABAP editor.

        Walks the element tree to find a ``GuiAbapEditor`` or ``GuiTextedit``
        and reads all lines via the raw COM ``GetLineCount`` / ``GetLineText``
        interface.
        """
        session = self.require_session()

        def _read() -> str | None:
            result = DesktopBackend._find_editor_shell_raw(session)
            if result is None:
                return None
            raw_shell, sub_type = result

            # Strategy 1: Text property (works for TextEdit, also fallback for AbapEditor)
            # TextEdit uses \r as line separator; normalize to \n.
            if sub_type == "TextEdit":
                try:
                    text = raw_shell.Text
                    if text and not str(text).startswith("SAPGUI."):
                        return str(text).replace("\r\n", "\n").replace("\r", "\n")
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("read_editor_source: Text property failed", extra={"sub_type": sub_type})

            # Strategy 2: GetLineCount + GetLineText (AbapEditor on S/4)
            try:
                num_lines = raw_shell.GetLineCount()
                lines = [str(raw_shell.GetLineText(i)) for i in range(num_lines)]
                return "\n".join(lines)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("read_editor_source: GetLineCount/GetLineText failed", extra={"sub_type": sub_type})

            # Strategy 3: Text property as last resort (any subtype)
            try:
                text = raw_shell.Text
                if text and not str(text).startswith("SAPGUI."):
                    return str(text).replace("\r\n", "\n").replace("\r", "\n")
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "read_editor_source",
                    extra={"sub_type": sub_type, "error": "All read strategies failed"},
                )
            return None

        source = await self.com.run(_read)
        logger.info("read_editor_source", extra={"found": source is not None})
        return source

    async def replace_editor_source(self, code: str) -> bool:
        """Replace the entire source code in an open ABAP editor.

        For ``GuiAbapEditor``: SelectRange + Delete + InsertText.
        For ``GuiTextedit``: sets the ``Text`` property directly.
        """
        session = self.require_session()

        def _replace() -> bool:

            result = DesktopBackend._find_editor_shell_raw(session)
            if result is None:
                return False
            raw_shell, sub_type = result
            # GuiAbapEditor: SelectRange + Delete + InsertText(text, line, col).
            # SelectRange(startLine, startCol, endLine, endCol) creates a proper
            # selection that Delete() respects (unlike SelectAll which doesn't).
            # InsertText signature: (text: str, line: int, col: int) — undocumented.
            # InsertText drops the last segment after \n, so append \n to the code.
            max_col = 9999  # SAP clamps to actual line length
            if sub_type == "AbapEditor":
                try:
                    # Clear: SelectRange all + Delete, repeated because the first
                    # pass may leave a residual empty line that still has content
                    # in the editor buffer.
                    for _ in range(2):
                        cnt = raw_shell.GetLineCount()
                        raw_shell.SelectRange(0, 0, cnt - 1, max_col)
                        time.sleep(0.1)
                        raw_shell.Delete()
                        time.sleep(0.1)
                    # Insert new code (trailing \n ensures last line is included)
                    insert_code = code if code.endswith("\n") else code + "\n"
                    raw_shell.InsertText(insert_code, 0, 0)
                    time.sleep(0.2)
                    return True
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.warning("replace_editor_source AbapEditor failed: %s", exc)
                    return False
            # GuiTextedit: set Text property
            try:
                raw_shell.Text = code
                return True
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "replace_editor_source",
                    extra={"sub_type": sub_type, "error": "Text property unavailable"},
                )
            return False

        replaced = await self.com.run(_replace)
        logger.info("replace_editor_source", extra={"success": replaced, "length": len(code)})
        return replaced

    async def check_and_activate(self) -> CheckActivateResult:
        """Run syntax check (Ctrl+F2) and activate (Ctrl+F3).

        Sends VKey 26 (check), reads status bar, handles "Inactive Objects"
        popup, then sends VKey 27 (activate) and reads status bar again.
        """

        session = self.require_session()

        def _check_activate() -> tuple[list[str], bool]:
            wnd = session.find_by_id("wnd[0]")
            messages: list[str] = []

            # Check (Ctrl+F2 = VKey 26)
            cast(Any, wnd).send_v_key(26)
            sbar = session.find_by_id("wnd[0]/sbar")
            msg = str(cast(Any, sbar).text)
            check_type = str(cast(Any, sbar).message_type)
            if msg:
                messages.append(f"Check: {msg}")

            # If check failed, return early without activating
            if check_type == "E":
                return messages, False

            # Handle "Inactive Objects" popup if it appears
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is not None:
                cast(Any, popup).send_v_key(0)  # Confirm with Enter

            # Activate (Ctrl+F3 = VKey 27)
            cast(Any, wnd).send_v_key(27)
            sbar = session.find_by_id("wnd[0]/sbar")
            msg = str(cast(Any, sbar).text)
            msg_type = str(cast(Any, sbar).message_type)
            if msg:
                messages.append(f"Activate: {msg}")

            # Handle "Inactive Objects" popup again
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is not None:
                cast(Any, popup).send_v_key(0)

            activated = msg_type != "E"
            return messages, activated

        try:
            messages, activated = await self.com.run(_check_activate)
            logger.info(
                "check_and_activate",
                extra={"activated": activated, "message_count": len(messages)},
            )
            return CheckActivateResult(success=True, messages=messages, activated=activated)
        except Exception as e:
            logger.warning("check_and_activate", extra={"error": str(e)})
            return CheckActivateResult(success=False, error=str(e), messages=[], activated=False)

    async def dismiss_language_dialog(self) -> None:
        """Dismiss the 'Different original and logon languages' dialog if present.

        Checks for modal wnd[1] containing "originalsprache" or "original"/"language"
        text, and presses Enter to confirm.
        """
        session = self.require_session()

        def _dismiss() -> bool:
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is None:
                return False
            text = str(cast(Any, popup).text).lower()
            if "originalsprache" in text or ("original" in text and "language" in text):
                cast(Any, popup).send_v_key(0)  # Enter to confirm
                return True
            return False

        dismissed = await self.com.run(_dismiss)
        logger.info("dismiss_language_dialog", extra={"dismissed": dismissed})

    # ---- SapPopup ----

    async def check_popup(self) -> PopupInfo | None:
        """Detect whether a popup/dialog is currently visible.

        Checks if wnd[1] exists, then reads its title, text content,
        and button labels to build a PopupInfo.
        """

        session = self.require_session()

        def _check() -> dict[str, Any] | None:
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is None:
                return None
            title = str(cast(Any, popup).text)
            # Collect elements from the popup
            tree = cast(Any, popup).dump_tree()
            flat = _flatten(tree)
            buttons: list[dict[str, str | None]] = []
            for elem in flat:
                if elem.type_as_number != 40:  # GuiButton
                    continue
                label = elem.text.strip()
                if not label:
                    label = elem.tooltip.strip()
                if label:
                    buttons.append({"label": label, "id": elem.id})
            # Collect text content (labels and text fields)
            texts: list[str] = []
            for elem in flat:
                if elem.type_as_number in (30, 31) and elem.text.strip():
                    texts.append(elem.text.strip())
            message = " ".join(texts) if texts else title
            return {"title": title, "message": message, "buttons": buttons}

        data = await self.com.run(_check)
        if data is None:
            logger.debug("check_popup", extra={"found": False})
            return None

        # Determine popup type from title/message heuristics
        popup_type = PopupType.UNKNOWN
        msg_lower = (data["message"] or "").lower()
        title_lower = (data["title"] or "").lower()
        combined = msg_lower + " " + title_lower
        if any(kw in combined for kw in ("error", "fehler")):
            popup_type = PopupType.ERROR
        elif any(kw in combined for kw in ("information", "hinweis")):
            popup_type = PopupType.INFO
        elif any(kw in combined for kw in ("confirm", "bestätigung", "ja", "nein", "yes", "no")):
            popup_type = PopupType.CONFIRM

        popup_buttons = [PopupButton(label=b["label"], id=b.get("id")) for b in data["buttons"]]
        logger.info(
            "check_popup",
            extra={"found": True, "type": popup_type, "button_count": len(popup_buttons)},
        )
        return PopupInfo(
            popup_type=popup_type,
            message=data["message"],
            buttons=popup_buttons,
        )

    async def dismiss_popup(self, button_label: str | None = None, use_close_button: bool = False) -> ClosePopupResult:
        """Dismiss a popup by clicking a button or the close control.

        If use_close_button is True, closes the popup window directly.
        If button_label is given, finds and clicks the matching button.
        Otherwise, presses Enter (VKey 0) as default.
        """

        session = self.require_session()

        def _dismiss() -> dict[str, Any]:
            popup = session.find_by_id("wnd[1]", raise_error=False)
            if popup is None:
                return {"dismissed": False, "button_clicked": None}

            if use_close_button:
                cast(Any, popup).close()
                return {"dismissed": True, "button_clicked": None}

            if button_label:
                # Find button by label in popup
                tree = cast(Any, popup).dump_tree()
                for elem in _flatten(tree):
                    if elem.type_as_number == 40 and (
                        button_label.lower() in elem.text.lower() or button_label.lower() in elem.tooltip.lower()
                    ):
                        btn = session.find_by_id(elem.id)
                        cast(Any, btn).press()
                        return {"dismissed": True, "button_clicked": elem.text.strip()}

            # Default: press Enter
            cast(Any, popup).send_v_key(0)
            return {"dismissed": True, "button_clicked": None}

        try:
            data = await self.com.run(_dismiss)
            # Read status bar after dismissal
            sbar_text = ""
            sbar_type: StatusBarType = "none"
            if data["dismissed"]:
                try:

                    def _read_sbar() -> tuple[str, str]:
                        sbar = session.find_by_id("wnd[0]/sbar")
                        return str(cast(Any, sbar).text), str(cast(Any, sbar).message_type)

                    sbar_text, raw_type = await self.com.run(_read_sbar)
                    if raw_type == "A":
                        raw_type = "E"  # map Abort to Error
                    if raw_type in ("S", "E", "W", "I"):
                        sbar_type = cast(StatusBarType, raw_type)
                except Exception:
                    pass

            logger.info(
                "dismiss_popup",
                extra={
                    "dismissed": data["dismissed"],
                    "button": data["button_clicked"],
                    "use_close": use_close_button,
                },
            )
            return ClosePopupResult(
                success=data["dismissed"],
                error=None if data["dismissed"] else "No popup found",
                button_clicked=data["button_clicked"],
                popup_closed=data["dismissed"],
                status_bar_type=sbar_type,
                status_bar_message=sbar_text,
            )
        except Exception as e:
            logger.warning("dismiss_popup", extra={"error": str(e)})
            return ClosePopupResult(
                success=False,
                error=str(e),
                popup_closed=False,
            )
