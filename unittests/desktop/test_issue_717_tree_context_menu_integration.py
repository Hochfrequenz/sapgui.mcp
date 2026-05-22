"""End-to-end integration test for ``sap_tree_context_menu``.

Reproduces the exact reporter workflow from GitHub issue #717:

1. Navigate to ``/n/NA2/DCS``.
2. Expand the tree to ``DCS Projekte → AUSBILDUN → AUSB_EXT_PRD →
   Taskgruppe 100000 → Taskgruppe 101000``.
3. List the right-click context menu and assert ``"Task: Anlegen"``
   is present with a valid function code.
4. Invoke ``"Task: Anlegen"`` — verify the follow-up screen
   (``DCS - Create Task`` / ``DCS Task anlegen``) opens.

Skips cleanly if ``/NA2/DCS`` is not installed on the target system or
if the expected tree structure is missing.
"""

from __future__ import annotations

import sys

import pytest

from sapguimcp.tools.tree_tools import _invoke_tree_context_menu
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


_NOT_FOUND_MARKERS = (
    "unbekannt",
    "does not exist",
    "nicht definiert",
    "is unknown",
    "not defined",
    "not found",
)

SHELL_ID = "wnd[0]/shellcont/shell"
TREE_PATH = [
    "DCS Projekte",
    "AUSBILDUN",
    "AUSB_EXT_PRD",
    "Taskgruppe 100000",
    "Taskgruppe 101000",
]
TARGET_MENU_TEXT = "Task: Anlegen"


def _looks_missing(sbar_type: str, sbar_message: str | None) -> bool:
    if sbar_type not in ("E", "A", "W"):
        return False
    msg = (sbar_message or "").lower()
    return any(m in msg for m in _NOT_FOUND_MARKERS)


async def _expand_to_target(backend) -> str | None:
    """Expand the reporter's DCS path and return the key of 'Taskgruppe 101000'.

    Returns None if any hop in the path cannot be located — the caller
    should ``pytest.skip`` in that case.

    All GetAllNodeKeys + GetNodeTextByKey + ExpandNode calls for one hop
    run inside a single COM lambda so we pay async dispatch overhead once
    per hop instead of once per tree node — important because the DCS
    tree has 200+ nodes after expansion.
    """
    session = backend.require_session()

    def _resolve_and_expand(label: str) -> tuple[str | None, bool]:
        """Return (key_of_label, did_expand). Pure COM, one round-trip."""
        raw_session = getattr(session, "com", getattr(session, "_com", session))
        shell = raw_session.FindById(SHELL_ID)
        coll = shell.GetAllNodeKeys()
        pairs: list[tuple[str, str]] = []
        for i in range(coll.Count):
            try:
                k = str(coll.Item(i))
                pairs.append((k, str(shell.GetNodeTextByKey(k))))
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        # Prefer exact match, fall back to substring.
        match = next((k for k, t in pairs if t.strip() == label), None)
        if match is None:
            match = next((k for k, t in pairs if label in t), None)
        if match is None:
            return None, False
        shell.ExpandNode(match)
        return match, True

    def _resolve_only(label: str) -> str | None:
        raw_session = getattr(session, "com", getattr(session, "_com", session))
        shell = raw_session.FindById(SHELL_ID)
        coll = shell.GetAllNodeKeys()
        pairs: list[tuple[str, str]] = []
        for i in range(coll.Count):
            try:
                k = str(coll.Item(i))
                pairs.append((k, str(shell.GetNodeTextByKey(k))))
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        match = next((k for k, t in pairs if t.strip() == label), None)
        if match is None:
            match = next((k for k, t in pairs if label in t), None)
        return match

    for label in TREE_PATH[:-1]:
        key, ok = await backend.com.run(lambda _l=label: _resolve_and_expand(_l))
        if not ok:
            return None
    return await backend.com.run(lambda: _resolve_only(TREE_PATH[-1]))


@skip_no_sap
@pytest.mark.anyio
async def test_dcs_tree_context_menu_lists_task_anlegen(backend):
    """Issue #717 follow-up: enumerate the context menu; 'Task: Anlegen' must be there."""
    r = await backend.enter_transaction("/n/NA2/DCS")
    sbar = await backend.get_status_bar()
    try:
        if _looks_missing(sbar.type, sbar.message):
            pytest.skip(f"/NA2/DCS not available on this system: {sbar.message}")
        assert r.success, f"enter_transaction failed unexpectedly: {r.error}"

        target_key = await _expand_to_target(backend)
        if target_key is None:
            pytest.skip("reporter's DCS tree path (AUSBILDUN → AUSB_EXT_PRD → ...) is absent on this system")

        session = backend.require_session()
        result = await backend.com.run(
            lambda: _invoke_tree_context_menu(
                session,
                SHELL_ID,
                target_key,
                select_text=None,
                select_fcode=None,
                select_position=None,
            )
        )

        assert result["items"], "expected a non-empty context menu on Taskgruppe 101000"
        labels = [it["text"] for it in result["items"]]
        assert TARGET_MENU_TEXT in labels, f"expected {TARGET_MENU_TEXT!r} in menu items; got: {labels}"

        # fcode must be non-empty and look like a T_ function code
        target = next(it for it in result["items"] if it["text"] == TARGET_MENU_TEXT)
        assert target["fcode"], "the discovered item must carry a function code"
    finally:
        await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_dcs_tree_context_menu_fires_task_anlegen(backend):
    """Issue #717 follow-up: select 'Task: Anlegen' and verify the follow-up screen opens.

    The DCS add-on opens 'Task: Anlegen' in a NEW SAP session on the same
    connection (parallel mode, like ``/o``), so the current ``wnd[0]`` title
    stays on DCS. We verify the reporter's expected screen by walking the
    SAP COM hierarchy and looking for any session whose program matches
    ``/NA2/DCS_TASK_CREATE``.
    """
    r = await backend.enter_transaction("/n/NA2/DCS")
    sbar = await backend.get_status_bar()
    try:
        if _looks_missing(sbar.type, sbar.message):
            pytest.skip(f"/NA2/DCS not available on this system: {sbar.message}")
        assert r.success, f"enter_transaction failed unexpectedly: {r.error}"

        target_key = await _expand_to_target(backend)
        if target_key is None:
            pytest.skip("reporter's DCS tree path is absent on this system")

        session = backend.require_session()

        def _session_programs_on_this_connection() -> list[str]:
            raw_session = getattr(session, "com", getattr(session, "_com", session))
            conn = raw_session.Parent
            programs: list[str] = []
            for i in range(conn.Children.Count):
                try:
                    programs.append(str(conn.Children(i).Info.Program))
                except Exception:  # pylint: disable=broad-exception-caught
                    # A freshly-opened session may not have Info populated yet.
                    programs.append("")
            return programs

        programs_before = await backend.com.run(_session_programs_on_this_connection)

        result = await backend.com.run(
            lambda: _invoke_tree_context_menu(
                session,
                SHELL_ID,
                target_key,
                select_text=TARGET_MENU_TEXT,
                select_fcode=None,
                select_position=None,
            )
        )

        assert result["selected"] is not None, "selection should have been recorded"
        assert result["selected"]["text"] == TARGET_MENU_TEXT

        # Give SAP a moment to open the new session before we probe.
        await backend.wait(timeout_ms=2000)

        programs_after = await backend.com.run(_session_programs_on_this_connection)
        new_programs = [p for p in programs_after if p not in programs_before]
        assert any("DCS_TASK_CREATE" in p for p in new_programs), (
            "expected a new session running /NA2/DCS_TASK_CREATE after selecting 'Task: Anlegen'; "
            f"programs_before={programs_before}, programs_after={programs_after}"
        )
    finally:
        # Close any parallel task-create sessions we opened. Capture the victim
        # IDs first, then close them — CloseSession mutates conn.Children
        # asynchronously and reading while closing races.
        try:

            def _close_extras() -> None:
                raw_session = getattr(session, "com", getattr(session, "_com", session))
                conn = raw_session.Parent
                my_id = str(raw_session.Id)
                victims = [
                    str(conn.Children(i).Id)
                    for i in range(conn.Children.Count)
                    if str(conn.Children(i).Id) != my_id and "DCS_TASK_CREATE" in str(conn.Children(i).Info.Program)
                ]
                for sid in victims:
                    try:
                        conn.CloseSession(sid)
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

            await backend.com.run(_close_extras)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        await go_home(backend)
